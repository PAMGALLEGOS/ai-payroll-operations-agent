"""Pure presentation helpers for the Streamlit UI (tested without a browser).

They only select and rename fields returned by the API. They never calculate a
validation outcome: every count shown comes from the Engine summary returned by
GET /validation or POST /chat.
"""

from __future__ import annotations

from typing import Any

from app.web.i18n import t

ROUTE_COLORS = {"RAG": "blue", "TOOL": "green", "TOOL_RAG": "violet", "CLARIFY": "orange", "OUT_OF_SCOPE": "red"}
STATUS_ICON = {"PASS": "✅", "FAIL": "❌"}


def summary_metrics(summary: dict[str, Any], lang: str) -> list[tuple[str, Any]]:
    return [
        (t("metric_total", lang), summary["total_validations"]),
        (t("metric_pass", lang), summary["pass_count"]),
        (t("metric_fail", lang), summary["fail_count"]),
        (t("metric_exceptions", lang), summary["exception_count"]),
        (t("metric_employees_exc", lang), len(summary.get("employees_with_exceptions", []))),
    ]


def results_rows(results: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    """Engine results as table rows. Values are copied, never recomputed."""
    return [
        {
            "": STATUS_ICON.get(r["status"], ""),
            t("col_employee", lang): r["employee_id"],
            t("col_type", lang): r["validation_type"],
            t("col_status", lang): r["status"],
            t("col_expected", lang): r["expected_value"] or "—",
            t("col_actual", lang): r["actual_value"] or "—",
            t("col_difference", lang): r["difference"] or "—",
            t("col_tolerance", lang): r["tolerance"],
            t("col_reason", lang): r["reason_code"],
            t("col_detail", lang): r["detail"],
        }
        for r in results
    ]


def reason_code_counts(summary: dict[str, Any]) -> dict[str, int]:
    """Exception reason codes from the Engine summary (WITHIN_TOLERANCE is not an exception)."""
    return {k: v for k, v in summary.get("by_reason_code", {}).items() if k != "WITHIN_TOLERANCE"}


def employee_options(results: list[dict[str, Any]]) -> list[str]:
    return sorted({r["employee_id"] for r in results})


def run_caption(run: dict[str, Any], lang: str) -> str:
    fingerprint = (run.get("results_fingerprint") or "")[:12]
    return (f"{t('run_info', lang)} {run.get('run_id')} · {run.get('run_timestamp')} · "
            f"engine {run.get('engine_version')} · rules {run.get('rules_version')} · fingerprint {fingerprint}…")


def route_badge(route: str, lang: str) -> tuple[str, str]:
    return f"{route} · {t(f'route_{route}', lang)}", ROUTE_COLORS.get(route, "gray")


def source_rows(evidence: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    return [
        {
            t("col_chunk", lang): e["chunk_id"],
            t("col_document", lang): e.get("document_title", ""),
            t("col_section", lang): e.get("section", ""),
            t("col_score", lang): round(float(e.get("score", 0)), 3),
        }
        for e in evidence
    ]


def technical_details(response: dict[str, Any]) -> dict[str, Any]:
    audit = response.get("audit") or {}
    return {
        "route": response.get("route"),
        "route_source": response.get("route_source"),
        "intent": response.get("intent"),
        "language": response.get("language"),
        "answer_mode": response.get("answer_mode"),
        "evidence_status": response.get("evidence_status"),
        "audit_verdict": audit.get("verdict"),
        "audit_revised": audit.get("revised", False),
        "failed_checks": [c["name"] for c in audit.get("checks", []) if not c.get("passed")],
        "entities": response.get("entities"),
        "trace_id": response.get("trace_id"),
        "latency_ms": response.get("latency_ms"),
        "versions": response.get("versions"),
    }


def llm_degraded(response: dict[str, Any]) -> bool:
    """True when an LLM step failed and a deterministic answer is shown instead (QA warning).

    An Auditor BLOCK also ends in `safe_fallback`, but there the LLM did answer, so it
    is not reported as "LLM unavailable".
    """
    if (response.get("versions") or {}).get("llm_degraded"):
        return True
    if response.get("route_source") == "fallback":
        return True
    return (response.get("route") in ("RAG", "TOOL_RAG") and response.get("evidence_status") == "sufficient"
            and response.get("answer_mode") == "template")


def health_rows(health: dict[str, Any], lang: str) -> list[tuple[str, str]]:
    rows = []
    for name, component in health.get("components", {}).items():
        label_key = f"component_{name}"
        try:
            label = t(label_key, lang)
        except KeyError:
            label = name
        rows.append((label, str(component.get("status"))))
    return rows
