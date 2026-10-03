"""Talk to the Agent from the console (CP3 — no API or UI yet).

Usage:
    python scripts/ask_agent.py --provider fake                  # interactive, offline
    python scripts/ask_agent.py --provider fake "Why did EMP024 fail?"
    python scripts/ask_agent.py --provider gemini --json "¿Por qué falló EMP027?"

--provider sets both the LLM and the embeddings provider; use --llm / --embeddings
to set them separately. Prerequisites: a validation run (scripts/run_validation.py)
and a knowledge index for the embeddings provider (scripts/ingest_knowledge.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.contracts import AgentRequest  # noqa: E402
from app.agent.factory import build_agent  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError  # noqa: E402
from app.rag.embeddings import EmbeddingsError  # noqa: E402


def show(response, as_json: bool) -> None:
    if as_json:
        print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return
    print(f"\n{response.answer}")
    if response.human_in_the_loop:
        print(f"\n[{response.human_in_the_loop}]")
    audit = response.audit.get("verdict", "-")
    revised = " (revised)" if response.audit.get("revised") else ""
    sources = ", ".join(e["chunk_id"] for e in response.evidence) or "-"
    print(f"\n  route={response.route} ({response.route_source}) intent={response.intent} "
          f"lang={response.language} mode={response.answer_mode}")
    print(f"  evidence={response.evidence_status} [{sources}] audit={audit}{revised} "
          f"trace={response.trace_id} {response.latency_ms} ms\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the payroll validation Agent.")
    parser.add_argument("message", nargs="?", help="One question; omit for interactive mode")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="LLM and embeddings provider")
    parser.add_argument("--llm", choices=["gemini", "fake"])
    parser.add_argument("--embeddings", choices=["gemini", "fake"])
    parser.add_argument("--session", default="console")
    parser.add_argument("--json", action="store_true", help="Print the full structured response")
    args = parser.parse_args()

    try:
        agent = build_agent(get_settings(), llm_provider=args.llm or args.provider,
                            embeddings_provider=args.embeddings or args.provider)
    except (LLMError, EmbeddingsError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.message:
        show(agent.handle(AgentRequest(args.session, args.message)), args.json)
        return 0

    print("Payroll validation Agent — synthetic data only. Empty line to exit.")
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            break
        show(agent.handle(AgentRequest(args.session, message)), args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
