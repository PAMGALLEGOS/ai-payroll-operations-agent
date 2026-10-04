"""GET /validation — identical to the Validation Tool, never uses the LLM."""

import json
import shutil

import pytest

from app.validation.tool import ValidationTool


def test_unfiltered_matches_engine_run(api, run_dir):
    body = api.get("/validation").json()
    tool = ValidationTool(run_dir).query("2026-09")
    assert body["results"] == tool.results
    assert body["summary"] == tool.summary
    assert body["summary"]["total_validations"] == 90 and body["summary"]["exception_count"] == 14


@pytest.mark.parametrize("params,count", [
    ({"employee_id": "EMP024"}, 3),
    ({"validation_type": "net_pay"}, 30),
    ({"status": "FAIL"}, 14),
    ({"validation_type": "net_pay", "status": "FAIL"}, 7),
    ({"employee_id": "EMP999"}, 0),
])
def test_filters(api, params, count):
    body = api.get("/validation", params=params).json()
    assert len(body["results"]) == count
    assert body["found"] is (count > 0)


def test_no_llm_is_used(api):
    calls_before = len(api.llm.calls)
    api.get("/validation")
    api.get("/validation", params={"status": "FAIL"})
    assert len(api.llm.calls) == calls_before
    assert "llm_called" not in api.observer.names()


@pytest.mark.parametrize("params", [{"employee_id": "24"}, {"period": "2026-13"}, {"status": "MAYBE"},
                                    {"validation_type": "bonus"}])
def test_invalid_filters_are_422(api, params):
    assert api.get("/validation", params=params).status_code == 422


def test_unknown_period_is_404(api):
    r = api.get("/validation", params={"period": "2026-08"})
    assert r.status_code == 404 and r.json()["error"] == "no_validation_run"


def test_tampered_run_is_503_without_results(api_factory, run_dir, tmp_path):
    folder = tmp_path / "runs"
    shutil.copytree(run_dir, folder)
    pointer = json.loads((folder / "latest_2026-09.json").read_text())
    payload = json.loads((folder / pointer["run_file"]).read_text())
    payload["results"][0]["status"] = "FAIL"
    (folder / pointer["run_file"]).write_text(json.dumps(payload))
    r = api_factory(results_dir=folder).get("/validation")
    assert r.status_code == 503 and r.json()["error"] == "run_integrity_failed"
    assert "results" not in r.json()


def test_multiple_periods_require_choice(api_factory, run_dir, tmp_path):
    folder = tmp_path / "runs"
    shutil.copytree(run_dir, folder)
    (folder / "latest_2026-10.json").write_text((folder / "latest_2026-09.json").read_text())
    r = api_factory(results_dir=folder).get("/validation")
    assert r.status_code == 400 and "2026-09, 2026-10" in r.json()["message"]
