"""POST /documents/ingest (D15, D4-06, D4-07) and GET /health."""

import shutil
import threading

from pydantic import SecretStr

from app.core.config import Settings
from app.core.paths import KNOWLEDGE_DIR


def _stale_knowledge(tmp_path):
    knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, knowledge)
    doc = knowledge / "rules" / "net_pay_rule.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nAdded after indexing.\n", encoding="utf-8")
    return knowledge


# ------------------------------------------------------------------ health
def test_health_ok(api):
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["components"]["validation_runs"]["periods"] == ["2026-09"]
    assert body["components"]["knowledge_index"] == {"status": "ok", "provider": "fake",
                                                     "model": "fake-hashing-v1", "chunks": 50}


def test_health_degraded_with_stale_index(api_factory, tmp_path):
    body = api_factory(knowledge_dir=_stale_knowledge(tmp_path)).get("/health").json()
    assert body["status"] == "degraded" and body["components"]["knowledge_index"]["status"] == "stale"


def test_health_degraded_without_run(api_factory, tmp_path):
    body = api_factory(results_dir=tmp_path / "empty").get("/health").json()
    assert body["status"] == "degraded" and body["components"]["validation_runs"]["status"] == "missing"


def test_health_never_exposes_secrets(api_factory):
    settings = Settings(_env_file=None, gemini_api_key=SecretStr("AIza-secret-key"),
                        ingest_token=SecretStr("tok-123"))
    text = api_factory(settings=settings).get("/health").text
    assert "AIza-secret-key" not in text and "tok-123" not in text
    assert '"ingest_protected":true' in text


def test_health_reports_startup_failure_instead_of_crashing(run_dir, tmp_path):
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    app = create_app(Settings(_env_file=None), results_dir=run_dir, index_dir=tmp_path,
                     llm_provider="gemini", embeddings_provider="fake")   # no API key -> Agent cannot be built
    with TestClient(app) as client:
        body = client.get("/health").json()
        assert body["status"] == "degraded"
        assert "GEMINI_API_KEY" in body["components"]["agent"]["error"]
        r = client.post("/chat", json={"message": "hi"})
        assert r.status_code == 503 and r.json()["error"] == "agent_unavailable"
        assert client.get("/validation").status_code == 200       # the dashboard still works


# ------------------------------------------------------------------ ingest
def test_ingest_rebuilds_from_knowledge_folder(api):
    body = api.post("/documents/ingest").json()
    assert body == {**body, "provider": "fake", "documents": 9, "chunks": 50, "index_status": "ok"}
    assert "ingest_completed" in api.observer.names()


def test_ingest_fixes_stale_index_without_restart(api_factory, tmp_path):
    client = api_factory(knowledge_dir=_stale_knowledge(tmp_path))
    assert client.post("/chat", json={"message": "What is the net pay tolerance?"}).json()["evidence_status"] \
        == "blocked_stale_index"
    assert client.post("/documents/ingest").json()["index_status"] == "ok"
    after = client.post("/chat", json={"message": "What is the net pay tolerance?"}).json()
    assert after["evidence_status"] == "sufficient"
    assert client.get("/health").json()["status"] == "ok"


def test_ingest_keeps_conversations(api):
    first = api.post("/chat", json={"message": "Why did EMP024 fail?"}).json()
    api.post("/documents/ingest")
    follow = api.post("/chat", json={"message": "What was the difference?", "session_id": first["session_id"]}).json()
    assert follow["entities"]["employee_id"] == "EMP024"


def test_ingest_refuses_uploads(api):
    r = api.post("/documents/ingest", files={"file": ("real_policy.md", b"# not synthetic")})
    assert r.status_code == 400 and r.json()["error"] == "uploads_not_accepted"


def test_ingest_token_required_when_configured(api_factory):
    client = api_factory(settings=Settings(_env_file=None, ingest_token=SecretStr("tok-123")))
    assert client.post("/documents/ingest").status_code == 401
    assert client.post("/documents/ingest", headers={"X-Ingest-Token": "wrong"}).status_code == 401
    assert client.post("/documents/ingest", headers={"X-Ingest-Token": "tok-123"}).status_code == 200


def test_concurrent_ingestion_is_refused(api, monkeypatch):
    from app.api.routes import documents

    started, release = threading.Event(), threading.Event()
    real_ingest = documents.ingest

    def slow_ingest(*args, **kwargs):
        started.set()
        release.wait(5)
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr(documents, "ingest", slow_ingest)
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("first", api.post("/documents/ingest").status_code))
    worker.start()
    started.wait(5)
    second = api.post("/documents/ingest")
    release.set()
    worker.join(10)
    assert second.status_code == 409 and results["first"] == 200


# ------------------------------------------------------------------ errors
def test_unexpected_error_is_generic_500_with_trace(api, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(api.app.state.api.tool, "available_periods", boom)
    r = api.get("/validation")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error" and body["trace_id"].startswith("TRACE-")
    assert "hunter2" not in r.text
