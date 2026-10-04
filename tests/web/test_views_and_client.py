"""UI helpers (pure functions) and the HTTP client used by Streamlit."""

import httpx
import pytest

from app.validation.tool import ValidationTool
from app.web import views
from app.web.api_client import ApiClient, ApiResponseError, ApiUnavailable
from app.web.i18n import EXAMPLE_QUESTIONS, LABELS, t


@pytest.fixture
def run(run_dir):
    return ValidationTool(run_dir).query("2026-09")


# ------------------------------------------------------------------ i18n
def test_every_label_has_both_languages():
    assert all(set(v) == {"es", "en"} for v in LABELS.values())


def test_spanish_is_the_default():
    assert t("tab_chat", "fr") == LABELS["tab_chat"]["es"]


def test_example_questions_cover_both_languages_equally():
    assert len(EXAMPLE_QUESTIONS["es"]) == len(EXAMPLE_QUESTIONS["en"]) >= 5


# ------------------------------------------------------------------ views
def test_metrics_come_from_engine_summary(run):
    metrics = dict(views.summary_metrics(run.summary, "en"))
    assert metrics == {"Validations": 90, "PASS": 76, "FAIL": 14, "Exceptions": 14, "Employees with exceptions": 8}


def test_result_rows_copy_values_without_recalculating(run):
    rows = views.results_rows(run.results, "es")
    emp024_net = next(r for r in rows if r["Empleado"] == "EMP024" and r["Validación"] == "net_pay")
    assert emp024_net["Diferencia"] == "350.00" and emp024_net["Estado"] == "FAIL" and emp024_net[""] == "❌"
    missing = next(r for r in rows if r["Empleado"] == "EMP027" and r["Validación"] == "gross_pay")
    assert missing["Esperado"] == "—" and missing["Reason code"] == "MISSING_INPUT"


def test_reason_codes_exclude_pass(run):
    assert views.reason_code_counts(run.summary) == {"INVALID_INPUT": 2, "MISSING_INPUT": 6, "OUT_OF_TOLERANCE": 6}


def test_route_badges_and_sources():
    assert views.route_badge("TOOL_RAG", "es") == ("TOOL_RAG · Engine + documentación", "violet")
    rows = views.source_rows([{"chunk_id": "RULE-003-C03", "document_title": "Net Pay", "section": "Tolerance",
                               "score": 0.81234}], "en")
    assert rows == [{"Chunk": "RULE-003-C03", "Document": "Net Pay", "Section": "Tolerance", "Similarity": 0.812}]


def test_technical_details_lists_failed_checks():
    details = views.technical_details({"route": "RAG", "audit": {"verdict": "BLOCK", "revised": True,
                                       "checks": [{"name": "numeric_grounding", "passed": False},
                                                  {"name": "scope", "passed": True}]}})
    assert details["audit_verdict"] == "BLOCK" and details["failed_checks"] == ["numeric_grounding"]


# ------------------------------------------------------------------ client
def _client(handler):
    return ApiClient("http://api", transport=httpx.MockTransport(handler))


def test_client_success_and_query_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).validation(employee_id="EMP024", status=None) == {"ok": True}
    assert seen["url"] == "http://api/validation?employee_id=EMP024"


def test_client_sends_session_id_only_when_present():
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(200, json={})

    client = _client(handler)
    client.chat("hola")
    client.chat("hola", "S-1")
    assert b"session_id" not in bodies[0] and b'"S-1"' in bodies[1]


def test_client_api_error_is_readable():
    client = _client(lambda r: httpx.Response(404, json={"error": "no_validation_run", "message": "none",
                                                         "trace_id": "TRACE-1"}))
    with pytest.raises(ApiResponseError) as info:
        client.validation()
    assert (info.value.status_code, info.value.error, info.value.trace_id) == (404, "no_validation_run", "TRACE-1")


def test_client_api_down_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiUnavailable):
        _client(handler).health()
