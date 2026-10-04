# AI Payroll Operations & Validation Agent — Academic PoC

> **Synthetic data only.** No real employees, payroll data, corporate documents,
> production systems or credentials are used anywhere in this repository.

**Current status: CP4 — end-to-end demo** (CP1 validation core, CP2 knowledge &
RAG and CP3 Agent approved). The application runs locally with a FastAPI API, a
Streamlit interface and JSON-lines observability. Docker / GCP readiness and the
final README come in CP5.

## Quick start — the demo

```bash
python scripts/run_demo.py --provider fake --prepare     # offline, no credentials
python scripts/run_demo.py --prepare                     # with Gemini (.env: GEMINI_API_KEY, GEMINI_MODEL)
```

It prepares the validation run and the knowledge index if missing, starts the
API on http://127.0.0.1:8000 (contract docs at /docs) and the interface on
http://localhost:8501. The interface opens in Spanish; switch to English in the
sidebar. Ctrl+C stops both.

## Core principle

| Question | Answered by |
|---|---|
| "What does the deterministic validation result say?" | **Payroll Validation Engine** (CP1) — the authoritative source of truth |
| "What does the documented knowledge say?" | **RAG layer** (CP2) — documentary evidence only |
| "What is the user asking, and how do I explain it?" | **Agent** (CP3) — intent, routing, orchestration, explanation |

The LLM classifies intent and writes explanations from evidence it is given.
Routes, entities, Engine facts, numbers and statuses are always decided by
deterministic code. The Agent never recalculates, changes or approves anything:
exception and approval decisions remain with a human reviewer.

## Agent routes

| Route | Example (EN / ES) | Answer |
|---|---|---|
| `RAG` | "What is the net pay tolerance?" / "¿Quién aprueba la nómina?" | LLM, only from cited chunks |
| `TOOL` | "Did EMP024 pass?" / "¿Cuántas excepciones hay?" | Deterministic template, no LLM |
| `TOOL_RAG` | "Why did EMP024 fail?" / "¿La nómina está lista para aprobarse?" | Engine facts by template + cited LLM explanation |
| `CLARIFY` | "Why did the employee fail?" | Template; the next message can complete the question |
| `OUT_OF_SCOPE` | "Approve the payroll" / "¿Tasa de ISR en México?" | Template |

Every generated answer passes the Auditor (ALLOW / REVISE once / BLOCK).

## Components

| Component | Path | What it does |
|---|---|---|
| Validation rules | `config/validation_rules.yaml` | Single source of truth: formulas, field mappings, tolerances |
| Validation Engine | `app/validation/` | Expected → provider value → difference → tolerance → PASS/FAIL → result |
| Validation Tool | `app/validation/tool.py` | Read-only, integrity-checked access to the latest persisted run |
| Knowledge base | `knowledge/` | 9 synthetic documents: 3 SOPs, 5 rules, 1 blueprint |
| RAG | `app/rag/` | Chunking, embeddings (Gemini + fake), JSON index, retrieval, docs ↔ YAML check |
| LLM clients | `app/llm/` | `LLMClient` interface: Gemini (structured output) + scriptable fake |
| Agent | `app/agent/` | Language, entities, intent, routing matrix, session, templates, explainer, orchestrator |
| Auditor | `app/audit/` | Deterministic checks and ALLOW / REVISE / BLOCK |
| API | `app/api/` | `POST /chat`, `GET /validation`, `POST /documents/ingest`, `GET /health` |
| Web interface | `app/web/` | Streamlit: Validation Dashboard + Chat (ES / EN), talks to the API only |
| Observability | `app/observability/` | One JSON line per event with `trace_id`, to stdout and `logs/agent.jsonl` |
| Scripts | `scripts/` | Batch run, ingestion, search, evaluations, console chat, demo launcher, KPI report |

## Run locally

Requires **Python 3.11**.

```bash
cd ai-payroll-agent
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# All automated tests (no API key, no network)
python -m pytest -v

# Prepare data
python scripts/run_validation.py --period 2026-09
python scripts/ingest_knowledge.py --provider fake

# Talk to the Agent offline
python scripts/ask_agent.py --provider fake
python scripts/ask_agent.py --provider fake "Why did EMP024 fail?"
python scripts/evaluate_agent.py --provider fake
```

### With real Gemini

```bash
cp .env.example .env               # set GEMINI_API_KEY and GEMINI_MODEL in .env
python scripts/ingest_knowledge.py --provider gemini
python scripts/ask_agent.py --provider gemini "¿Por qué falló EMP027?"
python scripts/evaluate_retrieval.py --provider gemini
python scripts/evaluate_agent.py --provider gemini --out cp3_gemini_eval.json
python -m pytest -m eval -v        # retrieval + Agent targets against real Gemini
```

The fake providers share the deterministic keyword rules of the fallback, so
their scores measure the deterministic layer only. Real routing and explanation
quality are measured with the Gemini steps above.

## Run the pieces separately

```bash
uvicorn app.api.main:app --port 8000
streamlit run app/web/streamlit_app.py
python scripts/metrics_report.py          # KPIs from logs/agent.jsonl
```

To follow one interaction, copy its `trace_id` from the interface (technical
details) and search for it in `logs/agent.jsonl`.

## Outputs (generated locally, not committed)

- `data/validation_results/` — immutable validation run files and a `latest_<period>.json` pointer.
- `data/vector_index/<provider>/index.json` — the knowledge index for each embeddings provider.
- `logs/agent.jsonl` — event log (metadata only: no questions, prompts or answers).
