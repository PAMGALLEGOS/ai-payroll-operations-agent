"""User-interface labels in Spanish (default, D4-10) and English.

Only the interface is translated. The Agent answers in the language of the
question, and canonical values (PASS / FAIL, reason codes, ids, amounts) are
never translated.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "es"

LABELS: dict[str, dict[str, str]] = {
    "app_title": {"es": "Agente de Validación de Nómina", "en": "Payroll Validation Agent"},
    "app_subtitle": {
        "es": "Prueba de concepto académica · solo datos sintéticos · el Engine es la fuente de verdad",
        "en": "Academic proof of concept · synthetic data only · the Engine is the source of truth",
    },
    "language": {"es": "Idioma de la interfaz", "en": "Interface language"},
    "tab_dashboard": {"es": "📊 Dashboard de validación", "en": "📊 Validation dashboard"},
    "tab_chat": {"es": "💬 Chat", "en": "💬 Chat"},
    "api_status": {"es": "Estado del sistema", "en": "System status"},
    "api_down": {
        "es": "No se pudo conectar con la API. Inicia el demo con `python scripts/run_demo.py`.",
        "en": "Could not reach the API. Start the demo with `python scripts/run_demo.py`.",
    },
    "status_ok": {"es": "Operando", "en": "Operational"},
    "status_degraded": {"es": "Degradado", "en": "Degraded"},
    "component_validation_runs": {"es": "Corridas de validación", "en": "Validation runs"},
    "component_agent": {"es": "Agente", "en": "Agent"},
    "component_knowledge_index": {"es": "Índice de conocimiento", "en": "Knowledge index"},
    "component_llm": {"es": "LLM", "en": "LLM"},
    "metric_total": {"es": "Validaciones", "en": "Validations"},
    "metric_pass": {"es": "PASS", "en": "PASS"},
    "metric_fail": {"es": "FAIL", "en": "FAIL"},
    "metric_exceptions": {"es": "Excepciones", "en": "Exceptions"},
    "metric_employees_exc": {"es": "Empleados con excepción", "en": "Employees with exceptions"},
    "filters": {"es": "Filtros", "en": "Filters"},
    "filter_employee": {"es": "Empleado", "en": "Employee"},
    "filter_type": {"es": "Tipo de validación", "en": "Validation type"},
    "filter_status": {"es": "Estado", "en": "Status"},
    "all": {"es": "Todos", "en": "All"},
    "results_table": {"es": "Resultados del Engine", "en": "Engine results"},
    "reason_chart": {"es": "Excepciones por reason code", "en": "Exceptions by reason code"},
    "no_exceptions": {"es": "Sin excepciones con estos filtros.", "en": "No exceptions for these filters."},
    "run_info": {"es": "Corrida", "en": "Run"},
    "dashboard_note": {
        "es": "Los datos vienen directamente de los resultados persistidos del Validation Engine. "
              "Este tablero no usa el LLM.",
        "en": "Data comes directly from the persisted Validation Engine results. "
              "This dashboard does not use the LLM.",
    },
    "no_results": {"es": "No hay resultados para estos filtros.", "en": "No results for these filters."},
    "chat_placeholder": {"es": "Escribe tu pregunta en español o inglés…", "en": "Ask in English or Spanish…"},
    "chat_intro": {
        "es": "Pregunta por resultados de validación, excepciones o procedimientos documentados. "
              "El asistente explica; nunca aprueba la nómina.",
        "en": "Ask about validation results, exceptions or documented procedures. "
              "The assistant explains; it never approves payroll.",
    },
    "new_conversation": {"es": "Nueva conversación", "en": "New conversation"},
    "examples": {"es": "Preguntas de ejemplo", "en": "Example questions"},
    "show_details": {"es": "Mostrar detalles técnicos", "en": "Show technical details"},
    "engine_facts": {"es": "Resultados del Engine (autoritativos)", "en": "Engine results (authoritative)"},
    "sources": {"es": "Fuentes documentales", "en": "Documentary sources"},
    "technical_details": {"es": "Detalles técnicos", "en": "Technical details"},
    "llm_degraded": {"es": "LLM no disponible: se muestra información verificada (respuesta determinista).",
                     "en": "LLM unavailable: showing verified information (deterministic answer)."},
    "thinking": {"es": "Consultando…", "en": "Working…"},
    "error_prefix": {"es": "Error de la API", "en": "API error"},
    "route_RAG": {"es": "Documentación", "en": "Documentation"},
    "route_TOOL": {"es": "Resultado del Engine", "en": "Engine result"},
    "route_TOOL_RAG": {"es": "Engine + documentación", "en": "Engine + documentation"},
    "route_CLARIFY": {"es": "Aclaración", "en": "Clarification"},
    "route_OUT_OF_SCOPE": {"es": "Fuera de alcance", "en": "Out of scope"},
    "col_employee": {"es": "Empleado", "en": "Employee"},
    "col_type": {"es": "Validación", "en": "Validation"},
    "col_status": {"es": "Estado", "en": "Status"},
    "col_expected": {"es": "Esperado", "en": "Expected"},
    "col_actual": {"es": "Proveedor", "en": "Provider"},
    "col_difference": {"es": "Diferencia", "en": "Difference"},
    "col_tolerance": {"es": "Tolerancia", "en": "Tolerance"},
    "col_reason": {"es": "Reason code", "en": "Reason code"},
    "col_detail": {"es": "Detalle", "en": "Detail"},
    "col_chunk": {"es": "Chunk", "en": "Chunk"},
    "col_document": {"es": "Documento", "en": "Document"},
    "col_section": {"es": "Sección", "en": "Section"},
    "col_score": {"es": "Similitud", "en": "Similarity"},
}

EXAMPLE_QUESTIONS = {
    "es": [
        "¿Por qué falló EMP024?",
        "¿Cuál fue la diferencia?",
        "¿EMP001 pasó la validación?",
        "¿Cuántas excepciones hay?",
        "¿Quién aprueba la nómina?",
        "¿La nómina está lista para aprobarse?",
        "¿Por qué falló el empleado?",
        "Aprueba la nómina",
    ],
    "en": [
        "Why did EMP024 fail?",
        "What was the difference?",
        "Did EMP001 pass validation?",
        "How many exceptions are there?",
        "Who approves the payroll?",
        "Is payroll ready for approval?",
        "Why did the employee fail?",
        "Approve the payroll",
    ],
}


def t(key: str, lang: str) -> str:
    entry = LABELS[key]
    return entry.get(lang) or entry[DEFAULT_LANGUAGE]
