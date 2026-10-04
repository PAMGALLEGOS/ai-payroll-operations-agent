"""Evaluate the Agent against the approved CP3 targets.

    python scripts/evaluate_agent.py --provider gemini          # REAL evaluation (needs GEMINI_API_KEY,
                                                                  GEMINI_MODEL and the Gemini index)
    python scripts/evaluate_agent.py --provider fake            # harness check, offline
    python scripts/evaluate_agent.py --provider gemini --json --out eval_report.json
    python scripts/evaluate_agent.py --provider gemini --min-interval 13 --out eval.json   # paced (F7a)

Metrics and approved targets:
  routing_accuracy                >= 90 %   all cases in routing_cases.yaml
  clarify_missing_employee        =  100 %  CLARIFY with reason missing_employee
  out_of_scope                    >= 90 %   OUT_OF_SCOPE
  agent_engine_consistency        =  100 %  results identical to the Validation Tool AND no
                                            ungrounded amount in the answer
  seeded_auditor_detection        =  100 %  seeded_responses.yaml (deterministic, no LLM)
  intent_llm_rate                 =  100 %  responses whose intent was classified by the LLM, out of
                                            all responses that asked the LLM (F3; the keyword
                                            fallback no longer hides a failing LLM)
  generation_success_rate         =  100 %  RAG / TOOL_RAG answers with sufficient evidence where
                                            the LLM generated the text (F3)
  allow_without_rewrite_rate      reported  answers the LLM really generated that were ALLOWed on
                                            the first attempt; deterministic fallbacks are excluded (F3)
  llm_fallbacks                   reported  how many times each LLM task fell back
  provider_errors                 reported  failed LLM calls by cause: quota_429, unavailable_503,
                                            timeout, other (F7a)
Overall status (F7a):
  PASS          every target met
  FAIL          a target missed for a reason other than provider quota / availability
  INCONCLUSIVE  only LLM-dependent targets missed AND the provider returned 429 / 503 /
                timeouts: rerun with pacing; this is not an Agent quality result
Exit code: 0 PASS, 1 FAIL or error, 2 INCONCLUSIVE.

Quota guard (F7c, Gemini only): a one-request preflight runs first; a quota or
availability error ends the run before any case (INCONCLUSIVE). During the run,
3 consecutive 429 responses stop it early (INCONCLUSIVE, partial report). The
report keeps the first masked provider message per error category
(`quota_guard.error_samples`), including the Google `quotaId`.

Case sets (F7d; the cases file and the targets are never modified):
  --case-set full         all cases in routing_cases.yaml (default)
  --case-set stratified   rule fixed before any run: the first case of every
                          category x language, plus, for out_of_scope, the first
                          case decided by the LLM (the first one is a prohibited
                          action decided by a rule, which never reaches Gemini).
                          14 cases, ~16 Gemini requests (+1 preflight): fits the
                          free-tier daily quota of 20.
N10 check (reported, not a target): for Spanish questions answered on the RAG
route, the retrieval query must be the English rewrite, not the original text.
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
from app.observability.events import RecordingObserver  # noqa: E402
from app.audit.auditor import Auditor  # noqa: E402
from app.audit.checks import AuditContext, check_numeric_grounding  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.paths import REPO_ROOT  # noqa: E402
from app.llm.client import LLMError  # noqa: E402
from app.rag.chunking import chunk_documents  # noqa: E402
from app.rag.documents import load_documents  # noqa: E402
from app.rag.embeddings import EmbeddingsError  # noqa: E402
from app.validation.tool import ValidationTool  # noqa: E402
from scripts.eval_pacing import (  # noqa: E402
    ENV_MIN_INTERVAL, QuotaGuard, is_transient, min_interval_from_env, paced_gemini_llm, preflight, provider_errors,
    shared_guard, shared_pacer,
)

EVAL_DIR = REPO_ROOT / "tests" / "evaluation"
TARGETS = {
    "routing_accuracy": 0.90,
    "clarify_missing_employee": 1.00,
    "out_of_scope": 0.90,
    "agent_engine_consistency": 1.00,
    "seeded_auditor_detection": 1.00,
    "intent_llm_rate": 1.00,
    "generation_success_rate": 1.00,
}
GENERATION_TASKS = {"RAG": "rag_answer", "TOOL_RAG": "tool_rag_explain"}
# Targets a provider outage can make fail (the LLM decides or writes). The other two are
# deterministic: provider errors never excuse them.
CASE_SETS = ("full", "stratified")
# Gemini requests of one run, measured with the fake LLM (tests keep these exact).
ESTIMATED_LLM_CALLS = {"full": 75, "stratified": 16}


SPANISH_MARKERS = {"el", "la", "los", "las", "de", "del", "que", "cual", "quien", "es", "por", "para", "con",
                   "una", "un", "nomina", "pago", "neto", "tolerancia", "aprueba"}


def is_english_rewrite(query: str, original: str) -> bool:
    """N10 heuristic: ASCII, different from the question, and no common Spanish words."""
    words = {w.strip("¿?¡!.,:;()\"'").lower() for w in query.split()}
    return query.isascii() and query.strip() != original.strip() and not (words & SPANISH_MARKERS)


def select_cases(cases: list[dict[str, Any]], case_set: str = "full") -> list[dict[str, Any]]:
    """Apply the predefined case-set rule (F7d). File order is kept; cases are never edited."""
    if case_set == "full":
        return list(cases)
    if case_set != "stratified":
        raise ValueError(f"unknown case set {case_set!r} (use one of {CASE_SETS})")
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    llm_oos: dict[str, dict[str, Any]] = {}
    for case in cases:
        chosen.setdefault((case["category"], case["lang"]), case)
        if case["category"] == "out_of_scope" and case.get("expected_reason") != "prohibited_action":
            llm_oos.setdefault(case["lang"], case)
    ids = {c["id"] for c in chosen.values()} | {c["id"] for c in llm_oos.values()}
    return [c for c in cases if c["id"] in ids]


LLM_DEPENDENT = {"routing_accuracy", "clarify_missing_employee", "out_of_scope",
                 "intent_llm_rate", "generation_success_rate"}


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


def run_routing(agent: Agent, cases: list[dict[str, Any]], guard: QuotaGuard | None = None) -> dict[str, Any]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    by_language: dict[str, list[bool]] = defaultdict(list)
    latency: dict[str, list[int]] = defaultdict(list)
    failures, consistency_failures = [], []
    consistent = checked = generated = allowed_first = language_ok = 0
    intent_asked = intent_by_llm = generation_expected = generation_ok = 0
    fallbacks: dict[str, int] = defaultdict(int)

    cases_run = 0
    n10: list[dict[str, Any]] = []
    queries: list[str] = []
    original_retrieve = agent._retrieve

    def spy(query):                                   # read-only: records the retrieval query (N10)
        queries.append(query)
        return original_retrieve(query)

    agent._retrieve = spy
    for case in cases:
        if guard is not None and guard.tripped:
            break                                    # F7c: stop spending quota
        cases_run += 1
        session = f"eval-{case['id']}"
        for message in case.get("setup", []):
            agent.handle(AgentRequest(session, message))
        queries.clear()
        r = agent.handle(AgentRequest(session, case["message"]))
        if case["lang"] == "es" and r.route == "RAG" and queries:
            query = queries[0]
            n10.append({"id": case["id"], "query": query,
                        "english_rewrite": is_english_rewrite(query, case["message"])})

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
        degraded = r.versions.get("llm_degraded", [])
        for task in degraded:
            fallbacks[task] += 1
        # Intent: only responses where the LLM classifier was asked (rule-decided routes and
        # resumed clarifications never ask it).
        if r.route_source in ("llm_intent", "fallback"):
            intent_asked += 1
            intent_by_llm += r.route_source == "llm_intent"
        # Generation: RAG / TOOL_RAG with sufficient evidence always ask the LLM for text.
        task = GENERATION_TASKS.get(r.route)
        if task and r.evidence_status == "sufficient":
            generation_expected += 1
            really_generated = task not in degraded
            generation_ok += really_generated
            # ALLOW without rewrite counts only text the LLM wrote (a deterministic
            # fallback audited as ALLOW is not a generated answer).
            if really_generated and r.audit:
                generated += 1
                allowed_first += r.audit.get("verdict") == "ALLOW" and not r.audit.get("revised")

    agent._retrieve = original_retrieve
    all_results = [ok for values in by_category.values() for ok in values]
    return {
        "cases": len(cases),
        "cases_run": cases_run,
        "case_ids": [c["id"] for c in cases],
        "n10_check": {"cases": n10, "passed": all(x["english_rewrite"] for x in n10) if n10 else None},
        "routing_accuracy": _rate(sum(all_results), len(all_results)),
        "routing_accuracy_by_language": {k: _rate(sum(v), len(v)) for k, v in by_language.items()},
        "accuracy_by_category": {k: _rate(sum(v), len(v)) for k, v in by_category.items()},
        "clarify_missing_employee": _rate(sum(by_category["clarify_missing_employee"]),
                                          len(by_category["clarify_missing_employee"])),
        "out_of_scope": _rate(sum(by_category["out_of_scope"]), len(by_category["out_of_scope"])),
        "agent_engine_consistency": _rate(consistent, checked),
        "agent_engine_responses_checked": checked,
        "intent_llm_rate": _rate(intent_by_llm, intent_asked),
        "intent_classified_responses": intent_asked,
        "generation_success_rate": _rate(generation_ok, generation_expected),
        "generation_expected": generation_expected,
        "allow_without_rewrite_rate": _rate(allowed_first, generated),
        "generated_answers": generated,
        "llm_fallbacks": dict(sorted(fallbacks.items())),
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


def overall_status(targets: dict[str, dict[str, Any]], errors: dict[str, int]) -> str:
    missed = {name for name, t in targets.items() if not t["met"]}
    if not missed:
        return "PASS"
    if missed <= LLM_DEPENDENT and is_transient(errors):
        return "INCONCLUSIVE"
    return "FAIL"


def evaluate(agent: Agent, results_dir: Path, observer: RecordingObserver | None = None,
             guard: QuotaGuard | None = None, case_set: str = "full") -> dict[str, Any]:
    """`observer` must be the one the Agent was built with; it gives the provider errors (F7a).
    `guard` (F7c) stops the routing cases early when the provider quota is exhausted."""
    cases = yaml.safe_load((EVAL_DIR / "routing_cases.yaml").read_text(encoding="utf-8"))["cases"]
    report = {"llm": f"{agent.llm.name}/{agent.llm.model}",
              "embeddings": (f"{agent.retriever.provider.name}/{agent.retriever.provider.model}"
                             if agent.retriever else None)}
    cases = select_cases(cases, case_set)
    report["case_set"] = case_set
    report["estimated_llm_calls"] = ESTIMATED_LLM_CALLS[case_set]
    report.update(run_routing(agent, cases, guard))
    report.update(run_seeded(results_dir))
    report["targets"] = {
        name: {"target": target, "actual": report[name], "met": report[name] >= target}
        for name, target in TARGETS.items()
    }
    report["provider_errors"] = provider_errors(observer.events) if observer else {}
    report["status"] = overall_status(report["targets"], report["provider_errors"])
    if guard is not None:
        report["quota_guard"] = guard.summary()
        if guard.tripped and report["status"] == "PASS":   # a partial run can never PASS
            report["status"] = "INCONCLUSIVE"
        if guard.tripped and report["status"] == "FAIL" and not (
                {n for n, t in report["targets"].items() if not t["met"]} - LLM_DEPENDENT):
            report["status"] = "INCONCLUSIVE"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Agent against the CP3 targets.")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="LLM and embeddings provider")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", help="Also write the JSON report to this file")
    parser.add_argument("--case-set", choices=CASE_SETS, default="full",
                        help="full (all cases) or stratified (14 predefined cases, fits 20 requests/day)")
    parser.add_argument("--min-interval", type=float, default=None,
                        help=f"seconds between Gemini requests (default: ${ENV_MIN_INTERVAL} or 0 = no pacing)")
    args = parser.parse_args()

    settings = get_settings()
    min_interval = args.min_interval if args.min_interval is not None else min_interval_from_env()
    observer = RecordingObserver()
    gemini = (args.provider or settings.llm_provider) == "gemini"
    guard = None
    try:
        llm = None
        if gemini:   # always through the evaluation client: pacing (if any) + quota guard (F7c)
            key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
            guard = shared_guard([key])
            llm = paced_gemini_llm(settings, min_interval, guard=guard)
        agent = build_agent(settings, llm=llm, llm_provider=args.provider, embeddings_provider=args.provider,
                            observer=observer)
    except (LLMError, EmbeddingsError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if agent.retriever is None:
        print("ERROR: knowledge index not found for this provider; run scripts/ingest_knowledge.py", file=sys.stderr)
        return 1

    if min_interval > 0:
        print(f"Pacing: {min_interval:g} s between Gemini requests "
              f"(≈ {60 / min_interval:.1f} requests/minute). This run takes ≈ {(ESTIMATED_LLM_CALLS[args.case_set] + 1) * min_interval / 60:.0f}+ min.",
              file=sys.stderr)
    if gemini:
        check = preflight(llm)
        if not check["ok"]:
            status = "INCONCLUSIVE" if check["transient"] else "FAIL"
            print(f"PREFLIGHT {status}: {check['error']}", file=sys.stderr)
            if status == "INCONCLUSIVE":
                print("No case was run. Provider quota / availability: see quotaId above "
                      "(PerMinute: wait a minute; PerDay: wait for the daily reset).", file=sys.stderr)
            if args.out:
                Path(args.out).write_text(json.dumps({"status": status, "preflight": check,
                                                      "quota_guard": guard.summary()}, indent=2,
                                                     ensure_ascii=False) + "\n", encoding="utf-8")
            return 2 if status == "INCONCLUSIVE" else 1
    if gemini:
        print(f"Case set: {args.case_set} · estimated Gemini requests: {ESTIMATED_LLM_CALLS[args.case_set]} "
              f"+ 1 preflight", file=sys.stderr)
    report = evaluate(agent, agent.tool.results_dir, observer, guard, args.case_set)
    report["pacing"] = {"min_interval_seconds": min_interval,
                        "requests": shared_pacer(min_interval).requests if gemini else None}
    exit_code = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[report["status"]]
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return exit_code

    print(f"LLM / embeddings : {report['llm']} / {report['embeddings']}")
    print(f"Cases            : {report['cases_run']} of {report['cases']} run · case set {report['case_set']} (EN + ES)")
    if report["case_set"] != "full":
        print(f"Case ids         : {', '.join(report['case_ids'])}")
    print(f"N10 check        : {report['n10_check']['passed']} {report['n10_check']['cases']}\n")
    print(f"{'Metric':34} {'Target':>8} {'Actual':>8}  Met")
    for name, t in report["targets"].items():
        print(f"{name:34} {t['target']:>8.0%} {t['actual']:>8.1%}  {'yes' if t['met'] else 'NO'}")
    print(f"\nRouting by language       : {report['routing_accuracy_by_language']}")
    print(f"Accuracy by category      : {report['accuracy_by_category']}")
    print(f"Language match            : {report['language_match']:.1%}")
    print(f"ALLOW without rewrite     : {report['allow_without_rewrite_rate']:.1%} "
          f"of {report['generated_answers']} generated answers")
    print(f"LLM fallbacks by task     : {report['llm_fallbacks'] or 'none'}")
    print(f"Auditor control FPs       : {report['control_false_positives'] or 'none'}")
    print("Latency by route (ms)     :")
    for route, stats in report["latency_ms_by_route"].items():
        print(f"  {route:13} n={stats['n']:<3} mean={stats['mean']:<6} p95={stats['p95']:<6} max={stats['max']}")
    for failure in report["routing_failures"]:
        print(f"ROUTING MISS {failure['id']}: '{failure['message']}' expected {failure['expected']} "
              f"got {failure['got']} (intent={failure['intent']}, source={failure['source']})")
    for failure in report["consistency_failures"] + report["seeded_missed"]:
        print(f"FAILURE {failure}")
    print(f"\nProvider errors           : {report['provider_errors'] or 'none'}")
    if report.get("quota_guard", {}).get("tripped"):
        print(f"STOPPED EARLY             : {report['quota_guard']['reason']} after "
              f"{report['cases_run']} of {report['cases']} cases")
    for category, sample in report.get("quota_guard", {}).get("error_samples", {}).items():
        print(f"Provider error sample [{category}]: {sample}")
    print(f"STATUS: {report['status']}")
    if report["status"] == "INCONCLUSIVE":
        print("  Provider quota / availability errors made LLM-dependent targets fail. This is not an Agent "
              f"quality result: rerun with pacing (--min-interval or ${ENV_MIN_INTERVAL}).")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
