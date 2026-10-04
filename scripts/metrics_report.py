"""KPI report from the JSON-lines event log (spec §15).

    python scripts/metrics_report.py                     # logs/agent.jsonl (+ rotated files)
    python scripts/metrics_report.py --log path/to/agent.jsonl --json

Reports: interactions by route, latency p50 / p95 / max by route, answer modes,
final Auditor verdicts and rewrite rate, Validation Tool calls and errors,
retrieval outcomes, LLM calls by task (success rate, mean duration), fallbacks,
contained errors and API requests by endpoint / status.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = REPO_ROOT / "logs" / "agent.jsonl"


def read_events(log: Path) -> list[dict[str, Any]]:
    files = sorted(log.parent.glob(log.name + ".*"), reverse=True) + [log]   # oldest rotated first
    events: list[dict[str, Any]] = []
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # a non-JSON line (e.g. a server banner) is ignored
    return events


def _percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(round(pct * len(ordered))) - 1))]


def compute_kpis(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    of = lambda name: [e for e in events if e.get("event") == name]  # noqa: E731

    completed = of("response_completed")
    latency: dict[str, list[int]] = defaultdict(list)
    for e in completed:
        latency[e["route"]].append(int(e.get("latency_ms", 0)))

    llm: dict[str, dict[str, Any]] = {}
    for task, calls in _group(of("llm_called"), "task").items():
        llm[task] = {"calls": len(calls), "ok_rate": round(sum(c.get("ok", False) for c in calls) / len(calls), 4),
                     "mean_ms": round(statistics.mean(c.get("duration_ms", 0) for c in calls))}

    verdicts = Counter(e.get("verdict") for e in completed)
    revised = sum(bool(e.get("revised")) for e in completed)
    api = Counter(f"{e.get('method')} {e.get('path')} {e.get('status_code')}" for e in of("api_request"))

    return {
        "events": len(events),
        "interactions": len(completed),
        "traces": len({e.get("trace_id") for e in completed}),
        "by_route": dict(Counter(e["route"] for e in completed)),
        "latency_ms_by_route": {
            route: {"n": len(v), "p50": _percentile(v, 0.50), "p95": _percentile(v, 0.95), "max": max(v)}
            for route, v in sorted(latency.items())
        },
        "answer_modes": dict(Counter(e.get("answer_mode") for e in completed)),
        "auditor_final_verdicts": dict(verdicts),
        "rewrite_rate": round(revised / len(completed), 4) if completed else 0.0,
        "tool_calls": len(of("tool_called")),
        "tool_errors": dict(Counter(e.get("error_type") for e in of("tool_error"))),
        "retrieval": dict(Counter(e.get("evidence_status") for e in of("rag_retrieved"))),
        "llm_calls": llm,
        "fallbacks": sum(e.get("source") == "fallback" for e in of("intent_identified")),
        "errors": dict(Counter(f"{e.get('component')}:{e.get('error_type')}" for e in of("error"))),
        "api_requests": dict(api),
        "ingestions": len(of("ingest_completed")),
    }


def _group(items: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[str(item.get(key))].append(item)
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description="KPIs from the Agent's event log.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    events = read_events(args.log)
    if not events:
        print(f"No events found in {args.log}. Use the demo first (scripts/run_demo.py).", file=sys.stderr)
        return 1
    kpis = compute_kpis(events)
    if args.json:
        print(json.dumps(kpis, indent=2, ensure_ascii=False))
        return 0

    print(f"Events / interactions : {kpis['events']} / {kpis['interactions']}")
    print(f"By route              : {kpis['by_route']}")
    print("Latency (ms)          :")
    for route, s in kpis["latency_ms_by_route"].items():
        print(f"  {route:13} n={s['n']:<4} p50={s['p50']:<6} p95={s['p95']:<6} max={s['max']}")
    print(f"Answer modes          : {kpis['answer_modes']}")
    print(f"Auditor final verdict : {kpis['auditor_final_verdicts']} (rewrite rate {kpis['rewrite_rate']:.1%})")
    print(f"Tool calls / errors   : {kpis['tool_calls']} / {kpis['tool_errors'] or 'none'}")
    print(f"Retrieval outcomes    : {kpis['retrieval']}")
    print(f"LLM calls             : {kpis['llm_calls']}")
    print(f"Intent fallbacks      : {kpis['fallbacks']}")
    print(f"Contained errors      : {kpis['errors'] or 'none'}")
    print(f"API requests          : {kpis['api_requests']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
