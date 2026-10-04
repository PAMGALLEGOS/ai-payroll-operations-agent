"""Cloud Run deployment package (academic PoC, approved D1): static checks, offline.

They protect the two rules that matter most for the deployment:
* no secret or local evidence can enter the image or the upload;
* FastAPI stays internal (127.0.0.1) and only Streamlit listens publicly on $PORT.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
START = (ROOT / "deploy" / "start.sh").read_text(encoding="utf-8")


def _patterns(name: str) -> set[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


@pytest.mark.parametrize("name", [".dockerignore", ".gcloudignore"])
def test_secrets_and_local_artefacts_are_excluded(name):
    patterns = _patterns(name)
    for required in (".env", ".env.*", "*.zip", "*.jsonl", "cp*_gemini*.json", "data/validation_results/*.json"):
        assert required in patterns, (name, required)
    assert {"logs", "logs/"} & patterns and {"tests", "tests/"} & patterns and {".git"} & patterns
    assert {".venv", ".venv/"} & patterns


def test_dockerignore_keeps_only_the_gemini_index():
    patterns = _patterns(".dockerignore")
    assert "data/vector_index/*" in patterns and "!data/vector_index/gemini/" in patterns


def test_gcloudignore_does_not_drop_the_gemini_index():
    patterns = _patterns(".gcloudignore")
    assert "data/vector_index/fake/" in patterns
    assert not any(p.startswith("data/vector_index") and "gemini" in p for p in patterns)
    assert "data/vector_index/" not in patterns


def test_dockerfile_never_carries_the_api_key():
    instructions = [line.strip().upper() for line in DOCKERFILE.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    assert not any("GEMINI_API_KEY" in line for line in instructions)   # no ENV / ARG / RUN with the key
    upper = DOCKERFILE.upper()
    assert "COPY .ENV" not in upper and "COPY . ." not in upper
    assert "FROM PYTHON:3.11-SLIM" in upper
    assert "USER APPUSER" in upper


def test_image_builds_the_synthetic_run_and_the_fake_index():
    assert "scripts/run_validation.py --period 2026-09" in DOCKERFILE
    assert "scripts/ingest_knowledge.py --provider fake" in DOCKERFILE
    assert 'CMD ["bash", "deploy/start.sh"]' in DOCKERFILE


def test_api_is_internal_and_ui_is_public():
    assert '--host 127.0.0.1 --port "${API_PORT}"' in START
    assert "--server.address 0.0.0.0" in START and '--server.port "${PORT}"' in START
    assert 'export API_BASE_URL="http://127.0.0.1:${API_PORT}"' in START
    assert "0.0.0.0" not in START.split("python -m uvicorn", 1)[1].split("\n", 1)[0]


def test_start_script_syntax():
    subprocess.run(["bash", "-n", str(ROOT / "deploy" / "start.sh")], check=True)
