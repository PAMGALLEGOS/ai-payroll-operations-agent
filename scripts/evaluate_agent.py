"""Evaluate the Agent against the approved CP3 targets.

    python scripts/evaluate_agent.py --provider gemini          # REAL evaluation (needs GEMINI_API_KEY,
                                                                  GEMINI_MODEL and the Gemini index)
    python scripts/evaluate_agent.py --provider fake            # harness check, offline
    python scripts/evaluate_agent.py --provider gemini --json --out eval_report.json

Metrics and approved targets:
  routing_accuracy                >= 90 %   all cases in routing_cases.yaml
  clarify_missing_employee        =  100 %  CLARIFY with reason missing_employee
  out_of_scope                    >= 90 %   OUT_OF_SCOPE
  agent_engine_consistency        =  100 %  results identical to the Validation Tool AND no
                                            ungrounded amount in the answer
  seeded_auditor_detection        =  100 %  seeded_responses.yaml (deterministic, no LLM)
  allow_without_rewrite_rate      reported  generated answers ALLOWed on the first attempt
  latency_by_route                reported  mean / p95 / max in ms
Also reported: language match (answer language = question language), control
false positives of the Auditor, and every failed case.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.contracts import AgentRequest  # noqa: E402
from app.agent.factory import build_agent  # noqa: E402
from app.agent.orchestrator import Agent  # noqa: E402
from app.audit.auditor import Auditor  # noqa: E402
from app.audit.checks import AuditContext, check_numeric_grounding  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.paths import REPO_ROOT  # noqa: E402
from app.llm.client import LLMError  # noqa: E402
from app.rag.chunking import chunk_documents  # noqa: E402
from app.rag.documents import load_documents  # noqa: E402
from app.rag.embeddings import EmbeddingsError  # noqa: E402
from app.validation.tool import ValidationTool  # noqa: E402

EVAL_DIR = REPO_ROOT / "tests" / "evaluation"
TARGETS = {
    "routing_accuracy": 0.90,
    "clarify_missing_employee": 1.00,
    "out_of_scope": 0.90,
    "agent_engine_consistency": 1.00,
    "seeded_auditor_detection": 1.00,
}


def _rate(ok: int, total: int) -> float:
    return round(ok / total, 4) if total else 1.0


def _consistency(agent: Agent, response) -> tuple[bool, str]:
    """Results identical to a fresh Tool query, and every amount in the answer grounded."""
    validation = response.validation
    if not validation:
        return True, ""
    filters = {k: v for k, v in validation["filters"].items() if v is not None}
    fresh = agent.tool.query(validation["run"]["period"], **filters)
    if fresh.results != validation["results"]:
        return False, "results differ from the Validation Tool"
    ctx = AuditContext(route=response.route, language=response.language, question="",
                       facts=validation["results"], summary=validation["summary"],
                       chunks=[{"chunk_id": e["chunk_id"], "content": e["content"]} for e in response.evidence])
    check = check_numeric_grounding(response.answer, ctx)
    return check.passed, check.details


def run_routing(agent: Agent, cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    by_language: dict[str, list[bool]] = defaultdict(list)
    latency: dict[str, list[int]] = defaultdict(list)
    failures, consistency_failures = [], []
    consistent = checked = generated = allowed_first = language_ok = 0

    for case in cases:
        session = f"eval-{case['id']}"
        for message in case.get("setup", []):
            agent.handle(AgentRequest(session, message))
        r = agent.handle(AgentRequest(session, case["message"]))

        ok = r.route == case["expected_route"]
        reason = (r.clarification or r.out_of_scope or {}).get("reason")
        if ok and "expected_reason" in case and case["category"] == "clarify_missing_employee":
            ok = reason == case["expected_reason"]
        by_category[case["category"]].append(ok)
        by_language[case["lang"]].append(ok)
        latency[r.route].append(r.latency_ms)
        language_ok += r.language == case["lang"]
        if not ok:
            failures.append({"id": case["id"], "message": case["message"], "expected": case["expected_route"],
                             "got": r.route, "reason": reason, "intent": r.intent, "source": r.route_source})

        if r.validation:
            checked += 1
            good, detail = _consistency(agent, r)
            consistent += good
            if not good:
                consistency_failures.append({"id": case["id"], "detail": detail})
        if r.answer_mode in ("llm", "template+llm", "safe_fallback") and r.audit:
            generated += 1
            allowed_first += r.audit.get("verdict") == "ALLOW" and not r.audit.get("revised")

    all_results = [ok for values in by_category.values() for ok in values]
    return {
        "cases": len(cases),
        "routing_accuracy": _rate(sum(all_results), len(all_results)),
        "routing_accuracy_by_language": {k: _rate(sum(v), len(v)) for k, v in by_language.items()},
        "accuracy_by_category": {k: _rate(sum(v), len(v)) for k, v in by_category.items()},
        "clarify_missing_employee": _rate(sum(by_category["clarify_missing_employee"]),
                                          len(by_category["clarify_missing_employee"])),
        "out_of_scope": _rate(sum(by_category["out_of_scope"]), len(by_category["out_of_scope"])),
        "agent_engine_consistency": _rate(consistent, checked),
        "agent_engine_responses_checked": checked,
        "allow_without_rewrite_rate": _rate(allowed_first, generated),
        "generated_answers": generated,
        "language_match": _rate(language_ok, len(cases)),
        "latency_ms_by_route": {
            route: {"n": len(v), "mean": round(statistics.mean(v)), "p95": sorted(v)[max(0, int(len(v) * 0.95) - 1)],
                    "max": max(v)}
            for route, v in sorted(latency.items())
        },
        "routing_failures": failures,
        "consistency_failures": consistency_failures,
    }


def run_seeded(results_dir: Path) -> dict[str, Any]:
    data = yaml.safe_load((EVAL_DIR / "seeded_responses.yaml").read_text(encoding="utf-8"))
    chunks = {c.chunk_id: c.content for c in chunk_documents(load_documents())}
    tool, auditor = ValidationTool(results_dir), Auditor()
    period = tool.available_periods()[0]

    def review(case):
        result = tool.query(period, employee_id=case["employee"])
        ctx = AuditContext(route="TOOL_RAG", language=case["language"], question="",
                           facts=result.results, summary=result.summary,
                           chunks=[{"chunk_id": c, "content": chunks[c]} for c in case["chunks"]],
                           allowed_employee_ids={case["employee"]}, requires_citation=True)
        return auditor.review(case["text"], ctx)

    detected, missed = 0, []
    for case in data["seeded"]:
        report = review(case)
        hit = report.verdict == case["expected_verdict"] and case["expected_check"] in {c.name for c in report.failed}
        detected += hit
        if not hit:
            missed.append({"id": case["id"], "verdict": report.verdict, "failed": [c.name for c in report.failed]})
    false_positives = [c["id"] for c in data["control"] if review(c).verdict != "ALLOW"]
    return {
        "seeded_auditor_detection": _rate(detected, len(data["seeded"])),
        "seeded_cases": len(data["seeded"]),
        "seeded_missed": missed,
        "control_cases": len(data["control"]),
        "control_false_positives": false_positives,
    }


def evaluate(agent: Agent, results_dir: Path) -> dict[str, Any]:
    cases = yaml.safe_load((EVAL_DIR / "routing_cases.yaml").read_text(encoding="utf-8"))["cases"]
    report = {"llm": f"{agent.llm.name}/{agent.llm.model}",
              "embeddings": (f"{agent.retriever.provider.name}/{agent.retriever.provider.model}"
                             if agent.retriever else None)}
    report.update(run_routing(agent, cases))
    report.update(run_seeded(results_dir))
    report["targets"] = {
        name: {"target": target, "actual": report[name], "met": report[name] >= target}
        for name, target in TARGETS.items()
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Agent against the CP3 targets.")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="LLM and embeddings provider")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", help="Also write the JSON report to this file")
    args = parser.parse_args()

    settings = get_settings()
    try:
        agent = build_agent(settings, llm_provider=args.provider, embeddings_provider=args.provider)
    except (LLMError, EmbeddingsError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if agent.retriever is None:
        print("ERROR: knowledge index not found for this provider; run scripts/ingest_knowledge.py", file=sys.stderr)
        return 1

    report = evaluate(agent, agent.tool.results_dir)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"LLM / embeddings : {report['llm']} / {report['embeddings']}")
    print(f"Cases            : {report['cases']} (EN + ES)\n")
    print(f"{'Metric':34} {'Target':>8} {'Actual':>8}  Met")
    for name, t in report["targets"].items():
        print(f"{name:34} {t['target']:>8.0%} {t['actual']:>8.1%}  {'yes' if t['met'] else 'NO'}")
    print(f"\nRouting by language       : {report['routing_accuracy_by_language']}")
    print(f"Accuracy by category      : {report['accuracy_by_category']}")
    print(f"Language match            : {report['language_match']:.1%}")
    print(f"ALLOW without rewrite     : {report['allow_without_rewrite_rate']:.1%} "
          f"of {report['generated_answers']} generated answers")
    print(f"Auditor control FPs       : {report['control_false_positives'] or 'none'}")
    print("Latency by route (ms)     :")
    for route, stats in report["latency_ms_by_route"].items():
        print(f"  {route:13} n={stats['n']:<3} mean={stats['mean']:<6} p95={stats['p95']:<6} max={stats['max']}")
    for failure in report["routing_failures"]:
        print(f"ROUTING MISS {failure['id']}: '{failure['message']}' expected {failure['expected']} "
              f"got {failure['got']} (intent={failure['intent']}, source={failure['source']})")
    for failure in report["consistency_failures"] + report["seeded_missed"]:
        print(f"FAILURE {failure}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
