"""Deterministic bilingual templates (decisions C3-03, C3-04, C3-12).

Every number and status shown here is copied from the Validation Tool output.
Nothing in this module calculates: it formats. Canonical values (validation
types, PASS / FAIL, reason codes, ids, amounts) are never translated.
"""

from __future__ import annotations

from typing import Any

from app.validation.tool import ToolResult

_T: dict[str, dict[str, str]] = {
    "header": {
        "en": "{emp} — period {period} (run {run_id}):",
        "es": "{emp} — periodo {period} (corrida {run_id}):",
    },
    "row_ok": {
        "en": "- {vtype}: {status} — expected {expected} {cur}, provider {actual} {cur}, "
              "difference {diff} {cur}, tolerance {tol} {cur} ({reason})",
        "es": "- {vtype}: {status} — esperado {expected} {cur}, proveedor {actual} {cur}, "
              "diferencia {diff} {cur}, tolerancia {tol} {cur} ({reason})",
    },
    "row_issue": {
        "en": "- {vtype}: {status} — expected {expected}, provider {actual} ({reason}: {detail})",
        "es": "- {vtype}: {status} — esperado {expected}, proveedor {actual} ({reason}: {detail})",
    },
    "not_available": {"en": "not available", "es": "no disponible"},
    "summary": {
        "en": "Run {run_id} (period {period}): {employees} employees, {total} validations — "
              "{passed} PASS, {failed} FAIL, {exceptions} exceptions.",
        "es": "Corrida {run_id} (periodo {period}): {employees} empleados, {total} validaciones — "
              "{passed} PASS, {failed} FAIL, {exceptions} excepciones.",
    },
    "summary_filtered": {
        "en": "Run {run_id} (period {period}), filter {filters}: {total} validations — "
              "{passed} PASS, {failed} FAIL, {exceptions} exceptions.",
        "es": "Corrida {run_id} (periodo {period}), filtro {filters}: {total} validaciones — "
              "{passed} PASS, {failed} FAIL, {exceptions} excepciones.",
    },
    "employees_with_exceptions": {
        "en": "Employees with exceptions ({count}): {list}.",
        "es": "Empleados con excepciones ({count}): {list}.",
    },
    "by_reason": {"en": "By reason code: {list}.", "es": "Por código de motivo: {list}."},
    "failed_detail": {"en": "Failed validations:", "es": "Validaciones con FAIL:"},
    "readiness": {
        "en": "Open exceptions: {exceptions} across {count} employees. The approval decision "
              "is not made by this assistant.",
        "es": "Excepciones abiertas: {exceptions} en {count} empleados. La decisión de aprobación "
              "no la toma este asistente.",
    },
    "readiness_none": {
        "en": "Open exceptions: 0. The approval decision is not made by this assistant.",
        "es": "Excepciones abiertas: 0. La decisión de aprobación no la toma este asistente.",
    },
    "employee_not_found": {
        "en": "{emp} is not in validation run {run_id} for period {period}.",
        "es": "{emp} no está en la corrida de validación {run_id} del periodo {period}.",
    },
    "no_match": {
        "en": "No validation results match {filters} in run {run_id}.",
        "es": "Ningún resultado de validación coincide con {filters} en la corrida {run_id}.",
    },
    "no_run": {
        "en": "There is no validation run for period {period}. Run the validation batch first "
              "(scripts/run_validation.py).",
        "es": "No hay una corrida de validación para el periodo {period}. Primero ejecuta el batch "
              "de validación (scripts/run_validation.py).",
    },
    "run_untrusted": {
        "en": "The validation run for period {period} failed its integrity check, so its results "
              "cannot be shown. Run the validation batch again.",
        "es": "La corrida de validación del periodo {period} no pasó su verificación de integridad, "
              "así que sus resultados no se pueden mostrar. Ejecuta de nuevo el batch de validación.",
    },
    "clarify_missing_employee": {
        "en": "Which employee do you mean? Please give the employee ID (format EMP###).",
        "es": "¿A qué empleado te refieres? Indica el ID del empleado (formato EMP###).",
    },
    "clarify_missing_period": {
        "en": "Which payroll period? Available validation runs: {periods}.",
        "es": "¿Qué periodo de nómina? Corridas de validación disponibles: {periods}.",
    },
    "clarify_no_periods": {
        "en": "There is no validation run available yet. Run the validation batch first.",
        "es": "Todavía no hay corridas de validación. Primero ejecuta el batch de validación.",
    },
    "clarify_multiple_employees": {
        "en": "Please ask about one employee at a time: {list}?",
        "es": "Por favor pregunta por un empleado a la vez: ¿{list}?",
    },
    "clarify_unclear": {
        "en": "I can help with validation results, exceptions and the documented payroll "
              "procedures. Could you rephrase your question?",
        "es": "Puedo ayudarte con resultados de validación, excepciones y los procedimientos de "
              "nómina documentados. ¿Puedes reformular tu pregunta?",
    },
    "oos_prohibited_action": {
        "en": "I can't approve payroll, change validation results or accept, close or resolve "
              "exceptions. Those decisions belong to a human reviewer under the Four-Eyes "
              "Approval Process.",
        "es": "No puedo aprobar la nómina, cambiar resultados de validación ni aceptar, cerrar o "
              "resolver excepciones. Esas decisiones corresponden a un revisor humano bajo el "
              "proceso de aprobación de cuatro ojos (Four-Eyes).",
    },
    "oos_off_topic": {
        "en": "I can only help with this synthetic payroll validation: validation results, "
              "exceptions and the documented procedures.",
        "es": "Solo puedo ayudarte con esta validación de nómina sintética: resultados de "
              "validación, excepciones y los procedimientos documentados.",
    },
    "oos_legal_advice": {
        "en": "This proof of concept uses fictional rules only and can't give legal, tax or "
              "payroll advice for real countries.",
        "es": "Esta prueba de concepto usa solo reglas ficticias y no puede dar asesoría legal, "
              "fiscal ni de nómina para países reales.",
    },
    "rag_insufficient": {
        "en": "The knowledge base has no documented answer to this question.",
        "es": "La base de conocimiento no tiene una respuesta documentada para esta pregunta.",
    },
    "rag_blocked": {
        "en": "The knowledge index is out of date or missing, so documentation can't be used "
              "until it is rebuilt (scripts/ingest_knowledge.py).",
        "es": "El índice de conocimiento está desactualizado o no existe, así que la documentación "
              "no se puede usar hasta reconstruirlo (scripts/ingest_knowledge.py).",
    },
    "explanation_unavailable": {
        "en": "A documented explanation is not available right now.",
        "es": "En este momento no hay una explicación documentada disponible.",
    },
    "relevant_sources": {"en": "Relevant documentation:", "es": "Documentación relevante:"},
    "why": {"en": "Why:", "es": "Por qué:"},
    "hitl": {
        "en": "Exception decisions and payroll approval remain with a human reviewer.",
        "es": "Las decisiones sobre excepciones y la aprobación de la nómina corresponden a un revisor humano.",
    },
    "safe_error": {
        "en": "Something went wrong while answering. No result was changed. Reference: {trace_id}.",
        "es": "Ocurrió un error al responder. Ningún resultado fue modificado. Referencia: {trace_id}.",
    },
    "blocked": {
        "en": "The generated explanation did not pass the safety checks, so only verified "
              "information is shown.",
        "es": "La explicación generada no pasó los controles de seguridad, así que solo se muestra "
              "información verificada.",
    },
}


def t(key: str, lang: str, **values: Any) -> str:
    return _T[key]["es" if lang == "es" else "en"].format(**values)


def _signed(value: str | None) -> str | None:
    if value is None:
        return None
    return value if value.startswith("-") or value.strip("0.") == "" else f"+{value}"


def format_result_row(r: dict[str, Any], lang: str) -> str:
    cur = r.get("currency", "")
    if r["difference"] is None:
        na = t("not_available", lang)
        return t(
            "row_issue", lang,
            vtype=r["validation_type"], status=r["status"],
            expected=f"{r['expected_value']} {cur}" if r["expected_value"] else na,
            actual=f"{r['actual_value']} {cur}" if r["actual_value"] else na,
            reason=r["reason_code"], detail=r["detail"],
        )
    return t(
        "row_ok", lang, vtype=r["validation_type"], status=r["status"], cur=cur,
        expected=r["expected_value"], actual=r["actual_value"], diff=_signed(r["difference"]),
        tol=r["tolerance"], reason=r["reason_code"],
    )


def employee_facts(result: ToolResult, employee_id: str, lang: str,
                   only_types: list[str] | None = None) -> str:
    rows = [r for r in result.results if not only_types or r["validation_type"] in only_types]
    lines = [t("header", lang, emp=employee_id, period=result.period, run_id=result.run["run_id"])]
    lines += [format_result_row(r, lang) for r in rows]
    return "\n".join(lines)


def _filters_text(filters: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in filters.items() if v is not None)


def aggregate_facts(result: ToolResult, lang: str, list_failures: bool = False) -> str:
    s = result.summary
    common = dict(run_id=result.run["run_id"], period=result.period, total=s["total_validations"],
                  passed=s["pass_count"], failed=s["fail_count"], exceptions=s["exception_count"])
    filters = _filters_text(result.filters)
    lines = [t("summary_filtered", lang, filters=filters, **common) if filters
             else t("summary", lang, employees=s["employees_validated"], **common)]

    if s["employees_with_exceptions"]:
        lines.append(t("employees_with_exceptions", lang, count=len(s["employees_with_exceptions"]),
                       list=", ".join(s["employees_with_exceptions"])))
    reasons = {k: v for k, v in s["by_reason_code"].items() if k != "WITHIN_TOLERANCE"}
    if reasons:
        lines.append(t("by_reason", lang, list=", ".join(f"{k} {v}" for k, v in reasons.items())))

    failed = [r for r in result.results if r["status"] == "FAIL"]
    if failed and (list_failures or filters):
        lines.append(t("failed_detail", lang))
        lines += [f"- {r['employee_id']} {r['validation_type']}: {r['reason_code']}" for r in failed]
    return "\n".join(lines)


def readiness_facts(result: ToolResult, lang: str) -> str:
    s = result.summary
    common = dict(run_id=result.run["run_id"], period=result.period, total=s["total_validations"],
                  passed=s["pass_count"], failed=s["fail_count"], exceptions=s["exception_count"],
                  employees=s["employees_validated"])
    lines = [t("summary", lang, **common)]
    if s["exception_count"]:
        lines.append(t("readiness", lang, exceptions=s["exception_count"],
                       count=len(s["employees_with_exceptions"])))
        lines.append(t("employees_with_exceptions", lang, count=len(s["employees_with_exceptions"]),
                       list=", ".join(s["employees_with_exceptions"])))
    else:
        lines.append(t("readiness_none", lang))
    return "\n".join(lines)


def no_match(result: ToolResult, lang: str) -> str:
    if result.filters.get("employee_id") and result.filters["employee_id"] not in result.employee_ids:
        return t("employee_not_found", lang, emp=result.filters["employee_id"],
                 run_id=result.run["run_id"], period=result.period)
    return t("no_match", lang, filters=_filters_text(result.filters), run_id=result.run["run_id"])


def sources_list(evidence: list[dict[str, Any]], lang: str) -> str:
    lines = [t("relevant_sources", lang)]
    lines += [f"- [{e['chunk_id']}] {e['document_title']} > {e['section']} ({e['source_document']})"
              for e in evidence]
    return "\n".join(lines)
