# AI Payroll Operations & Validation Agent — academic PoC image for Cloud Run.
#
# One container, one public port (approved D1, PoC simplification):
#   Streamlit UI  -> 0.0.0.0:$PORT        (public, Cloud Run)
#   FastAPI API   -> 127.0.0.1:8000       (internal only; the UI calls it over HTTP)
#
# No secret is ever written into this image: GEMINI_API_KEY is injected at run
# time by Cloud Run from Secret Manager. .env is excluded by .dockerignore and
# .gcloudignore. Only synthetic data is included.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    LOG_FILE=/tmp/agent.jsonl

WORKDIR /srv/app

# Dependencies first (pinned in requirements.txt), for layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code and synthetic inputs only (see .dockerignore).
COPY app/ app/
COPY config/ config/
COPY knowledge/ knowledge/
COPY scripts/ scripts/
COPY .streamlit/ .streamlit/
COPY deploy/ deploy/
COPY pyproject.toml .
# data/: synthetic payroll inputs, plus data/vector_index/gemini/ when it was
# generated locally before the build (optional; see docs/DEPLOY_GCP.md §3).
COPY data/ data/

# Deterministic artefacts built inside the image (no credentials needed):
#  1. the validation run for the synthetic period (Engine, CP1);
#  2. the fake knowledge index, as offline fallback (D5-13).
RUN python scripts/run_validation.py --period 2026-09 \
 && python scripts/ingest_knowledge.py --provider fake

# Build-time integrity check: a Gemini index, if present, must match knowledge/.
# A stale index fails the build instead of reaching Cloud Run.
RUN python -c "import sys; from app.rag.ingest import index_path, is_index_stale; \
from app.rag.vector_index import VectorIndex; p = index_path('gemini'); \
print('Gemini index:', 'present' if p.exists() else 'absent (deploy with EMBEDDINGS_PROVIDER=fake)'); \
sys.exit(1 if p.exists() and is_index_stale(VectorIndex.load(p)) else 0)"

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv/app
USER appuser

EXPOSE 8080
CMD ["bash", "deploy/start.sh"]
