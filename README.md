# AI Payroll Operations & Validation Agent — Academic PoC

> **Synthetic data only.** No real employees, payroll data, corporate documents,
> production systems or credentials are used anywhere in this repository.

**Current status:** Final academic PoC — deterministic Payroll Validation Engine, synthetic Knowledge Base & RAG, Agent orchestration, Auditor guardrails, FastAPI + Streamlit interface, JSON-lines observability, automated QA, Docker packaging, and a verified Google Cloud Run deployment with a successful real-Gemini end-to-end smoke test.

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
python scripts/diagnose_llm.py     # first: checks the model and both LLM calls (key never printed)
python scripts/ingest_knowledge.py --provider gemini
python scripts/ask_agent.py --provider gemini "¿Por qué falló EMP027?"
python scripts/evaluate_retrieval.py --provider gemini
python scripts/evaluate_agent.py --provider gemini --out cp3_gemini_eval.json
python -m pytest -m eval -v        # canary + retrieval + Agent targets against real Gemini
```

`intent_llm_rate` and `generation_success_rate` (target 100 %) prove that Gemini
itself answered; the deterministic fallback alone cannot meet them.

**Free tier (5 requests/minute per model):** pace the evaluation and run the
full Agent evaluation only once (≈ 75 requests, ≈ 17–20 min):

```bash
python scripts/evaluate_agent.py --provider gemini --min-interval 13 --out cp4_gemini_eval.json
# wait 60 s, then (reuses the report; only the canaries and N10 call Gemini):
EVAL_LLM_MIN_INTERVAL_SECONDS=13 EVAL_AGENT_REPORT=cp4_gemini_eval.json python -m pytest -m eval -v
```

The report status is PASS, FAIL, or INCONCLUSIVE (LLM-dependent targets missed
because of 429 / 503 / timeouts: rerun, it is not an Agent quality result).

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


## Cloud deployment — verified

The PoC was successfully deployed and smoke-tested on Google Cloud Run on October 4, 2026.

- Service: `payroll-agent`
- Region: `us-central1`
- Revision: `payroll-agent-00001-5pd`
- Traffic: `100%`
- Runtime: Google Cloud Run
- Secrets: Gemini API key injected at runtime through Google Secret Manager
- Maximum instances: `1`
- Application: https://payroll-agent-190772421839.us-central1.run.app

Deployment topology:

`Browser → Streamlit → internal FastAPI/Uvicorn → Agent → Validation Engine / RAG → Auditor`

### Verified end-to-end execution

A controlled production smoke test was executed against the deployed application:

**Question:** `¿Por qué falló EMP024?`

**Final route:** `TOOL_RAG`  
**Trace ID:** `TRACE-4f596f6a`  
**HTTP status:** `200`

Cloud Logging confirmed the execution chain:

`request_received → llm_called (intent) → intent_identified → tool_called → engine_result → rag_retrieved → llm_called → auditor_result → route_decided → response_completed`

The deterministic Validation Engine found the employee and returned one failed validation. RAG retrieved supporting documentation, the LLM generated the grounded explanation, and the Auditor executed before the Agent returned the final response.

This smoke test demonstrates the integrated runtime architecture. It does **not** replace the statistical evaluation suite.

### Evaluation note

The real-Gemini stratified evaluation remains **INCONCLUSIVE** because provider/quota errors interrupted the run after 11 of 14 cases. It is intentionally not reported as PASS or as an estimate of full-population Gemini quality.

The deterministic layer, resilience controls, deployment, and successful cloud end-to-end execution are documented separately in `docs/CP4_EVIDENCIA_FINAL.md`.