"""Render the real Streamlit script headless (streamlit.testing.AppTest) against the real API.

The UI's HTTP client is replaced by one that calls the FastAPI app in-process,
so the whole chain UI -> API -> Agent -> Tool / RAG -> Auditor runs without a
browser, network or credentials.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.web import api_client
from app.web.api_client import ApiClient

APP = str(Path(__file__).resolve().parents[2] / "app" / "web" / "streamlit_app.py")


@pytest.fixture
def ui(api, monkeypatch):
    in_process = ApiClient("http://testserver")
    in_process._client = api            # the FastAPI TestClient is an httpx.Client
    monkeypatch.setattr(api_client, "make_client", lambda: in_process)
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def _texts(app):
    return " ".join(m.value for m in app.markdown) + " " + " ".join(c.value for c in app.caption)


def test_dashboard_shows_engine_metrics_in_spanish_by_default(ui):
    metrics = {m.label: m.value for m in ui.metric}
    assert metrics["Validaciones"] == "90" and metrics["FAIL"] == "14" and metrics["Excepciones"] == "14"
    assert len(ui.dataframe) == 1
    assert "Operando" in _texts(ui)


def test_dashboard_filter_uses_api_summary(ui):
    ui.selectbox[2].select("FAIL").run()          # status filter
    metrics = {m.label: m.value for m in ui.metric}
    assert metrics["Validaciones"] == "14" and metrics["PASS"] == "0"


def test_language_switch_to_english(ui):
    ui.radio[0].set_value("en").run()
    assert "Validations" in {m.label for m in ui.metric}


def test_chat_shows_answer_engine_table_sources_and_hitl(ui):
    ui.radio[1].set_value("chat").run()
    ui.chat_input[0].set_value("¿Por qué falló EMP024?").run()
    assert not ui.exception
    text = _texts(ui)
    assert "TOOL_RAG" in " ".join(str(getattr(b, "value", "")) for b in ui.get("badge")) or "TOOL_RAG" in text
    assert "diferencia +350.00 SYN" in text
    assert len(ui.dataframe) >= 2               # Engine results table + sources
    assert any("revisor humano" in i.value for i in ui.info)


def test_example_question_button_goes_to_chat(ui):
    ui.button(key="ex-es-Aprueba la nómina").click().run()
    assert not ui.exception
    assert "No puedo aprobar la nómina" in _texts(ui)


def test_follow_up_keeps_session(ui):
    ui.radio[1].set_value("chat").run()
    ui.chat_input[0].set_value("Why did EMP024 fail?").run()
    ui.chat_input[0].set_value("What was the difference?").run()
    assert _texts(ui).count("difference +350.00 SYN") >= 2


def test_ui_survives_api_down(monkeypatch):
    class Down:
        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise api_client.ApiUnavailable("refused")
            return fail

    monkeypatch.setattr(api_client, "make_client", lambda: Down())
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception
    assert any("run_demo.py" in e.value for e in app.error)


def _ui_with(api, monkeypatch):
    in_process = ApiClient("http://testserver")
    in_process._client = api
    monkeypatch.setattr(api_client, "make_client", lambda: in_process)
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    return app


def test_chat_warns_when_llm_unavailable(api_factory, monkeypatch):
    from tests.helpers import failing_llm

    app = _ui_with(api_factory(llm=failing_llm()), monkeypatch)
    app.radio[1].set_value("chat").run()
    app.chat_input[0].set_value("¿Quién aprueba la nómina?").run()
    assert not app.exception
    assert any("LLM no disponible" in w.value for w in app.warning)


def test_chat_has_no_warning_when_llm_works(ui):
    ui.radio[1].set_value("chat").run()
    ui.chat_input[0].set_value("¿Quién aprueba la nómina?").run()
    assert not any("LLM no disponible" in w.value for w in ui.warning)
