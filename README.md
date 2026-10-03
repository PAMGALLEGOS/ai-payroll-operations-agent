# AI Payroll Operations & Validation Agent — Academic PoC

> **Synthetic data only.** No real employees, payroll data, corporate documents,
> production systems or credentials are used anywhere in this repository.

**Current status: CP2 — Knowledge & RAG** (CP1 deterministic validation core
approved). The Agent, Auditor, API, web app and GCP deployment are added in
later checkpoints, only after each checkpoint is approved. The full README
(architecture, deployment, example questions) is written in Phase 14.

## Core principle

| Question | Answered by |
|---|---|
| "What does the deterministic validation result say?" | **Payroll Validation Engine** (CP1) — the authoritative source of truth |
| "What does the documented knowledge say?" | **RAG layer** (CP2) — documentary evidence only |

The RAG layer never calculates payroll, never decides PASS / FAIL and never
modifies Engine results. The Agent (CP3) will combine both.

## Components

| Component | Path | What it does |
|---|---|---|
| Validation rules | `config/validation_rules.yaml` | Single source of truth: formulas, field mappings, tolerances |
| Validation Engine | `app/validation/` | Expected → provider value → difference → tolerance → PASS/FAIL → result |
| Batch run | `scripts/run_validation.py` | Runs the Engine and persists a versioned run file |
| Knowledge base | `knowledge/` | 9 synthetic documents: 3 SOPs, 5 rules, 1 blueprint |
| Document loader | `app/rag/documents.py` | Markdown + front matter; refuses documents not marked `synthetic: true` |
| Chunking | `app/rag/chunking.py` | One chunk per section, with traceable metadata |
| Embeddings | `app/rag/embeddings.py` | Provider interface: Gemini (approved) + deterministic fake for tests |
| Vector index | `app/rag/vector_index.py` | One JSON file + plain-Python cosine similarity |
| Ingestion | `scripts/ingest_knowledge.py` | Documents → chunks → embeddings → index (once) |
| Retrieval | `scripts/search_knowledge.py` | Question → embedding → similarity search → chunks + metadata |
| Consistency control | `app/rag/consistency.py` | Fails if documentation and the rules YAML drift apart |
| Retrieval evaluation | `scripts/evaluate_retrieval.py` | hit@k, MRR, out-of-scope rejection, threshold calibration |

## Run locally

Requires **Python 3.11**.

```bash
cd ai-payroll-agent
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# All automated tests (no API key needed)
python -m pytest -v

# CP1 — validation batch
python scripts/run_validation.py --period 2026-09

# CP2 — knowledge index and search with the offline test double
python scripts/ingest_knowledge.py --provider fake
python scripts/search_knowledge.py "Is a difference exactly equal to the tolerance a PASS?" --provider fake
python scripts/evaluate_retrieval.py --provider fake
```

### With real Gemini

```bash
cp .env.example .env               # then set GEMINI_API_KEY in .env
python scripts/ingest_knowledge.py --provider gemini
python scripts/search_knowledge.py "Who approves the payroll?" --provider gemini
python scripts/evaluate_retrieval.py --provider gemini
python -m pytest -m eval -v        # evaluation tests against real Gemini
```

The fake provider measures word overlap only. Real retrieval quality and the
Gemini similarity threshold are measured with the Gemini steps above.

## Outputs (generated locally, not committed)

- `data/validation_results/` — immutable validation run files and a `latest_<period>.json` pointer.
- `data/vector_index/<provider>/index.json` — the knowledge index for each embeddings provider.
