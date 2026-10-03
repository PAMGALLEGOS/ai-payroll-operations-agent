"""Bilingual (EN / ES) vocabulary used by deterministic components.

Used by:
  * the prohibited-action rule (runs BEFORE the LLM, cannot be overridden by it);
  * the keyword intent fallback (when the LLM is unavailable or returns invalid
    output) — the fake LLM uses the same function so tests are deterministic;
  * the fake LLM's English search-query rewrite (glossary).

Matching is done on accent-free lower-case text so "nómina" and "nomina",
"por qué" and "porque" behave the same.
"""

from __future__ import annotations

import re
import unicodedata

from app.agent.contracts import Intent


def normalize(text: str) -> str:
    """Lower-case, accents removed, punctuation turned into spaces."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9_\-]+", " ", without_accents).strip() + " "


def _has(text: str, phrases: tuple[str, ...]) -> bool:
    return any(f" {p} " in text for p in phrases)


# ----------------------------------------------------------- prohibited actions
# An ORDER to act (not a question about policy). Checked at the start of the
# message, optionally after "please / por favor", or after "can you / puedes".
_ACTION_VERBS = (
    # English
    "approve", "authorize", "authorise", "override", "change", "modify", "update", "edit",
    "mark", "close", "resolve", "accept", "delete", "remove", "pay", "release", "reject",
    "set", "fix", "correct", "overwrite", "sign off", "sign-off",
    # Spanish (imperative and infinitive)
    "aprueba", "apruebe", "aprobar", "autoriza", "autorizar", "cambia", "cambiar", "modifica",
    "modificar", "actualiza", "actualizar", "edita", "editar", "marca", "marcar", "cierra",
    "cerrar", "resuelve", "resolver", "acepta", "aceptar", "borra", "borrar", "elimina",
    "eliminar", "paga", "pagar", "libera", "liberar", "rechaza", "rechazar", "corrige", "corregir",
    # Spanish subjunctive after "necesito que / quiero que"
    "apruebes", "autorices", "cambies", "modifiques", "actualices", "marques", "cierres",
    "resuelvas", "aceptes", "borres", "elimines", "pagues", "liberes", "rechaces", "corrijas",
)
_POLITE_PREFIX = r"(?:(?:please|pls|kindly|por favor|porfa)\s+)?"
_REQUEST_PREFIX = (
    r"(?:(?:can|could|would|will) you\s+(?:please\s+)?|"
    r"(?:puedes|podrias|podria|me ayudas a|ayudame a|necesito que|quiero que)\s+(?:por favor\s+)?)?"
)
_PROHIBITED = re.compile(
    rf"^\s*{_POLITE_PREFIX}{_REQUEST_PREFIX}(?:{'|'.join(re.escape(v) for v in _ACTION_VERBS)})\b"
)


def is_prohibited_action(message: str) -> bool:
    """True when the message orders the Agent to act on payroll (approve, change, close...)."""
    return bool(_PROHIBITED.match(normalize(message).strip()))


# --------------------------------------------------------------- vocabularies
WHY = ("why", "por que", "porque", "explain why", "cause", "causa", "motivo")
RESULT_WORDS = (
    "pass", "passed", "fail", "failed", "failing", "status", "result", "results", "difference",
    "differences", "expected", "provider value", "amount", "how much", "did not pass", "didn t pass",
    "paso", "fallo", "fallaron", "estado", "resultado", "resultados", "diferencia", "esperado",
    "valor del proveedor", "monto", "cuanto", "no paso",
)
POLICY_WORDS = (
    "procedure", "process", "policy", "rule", "rules", "tolerance", "tolerances", "formula",
    "definition", "define", "defined", "mean", "means", "meaning", "sop", "four-eyes", "four eyes",
    "who approves", "prerequisite", "prerequisites", "role", "roles", "step", "steps", "evidence",
    "escalate", "escalation", "segregation", "deadline", "reason codes", "re-run", "rerun",
    "proceso", "procedimiento", "politica", "regla", "reglas", "tolerancia", "tolerancias",
    "formula", "definicion", "significa", "cuatro ojos", "quien aprueba", "requisito",
    "requisitos", "rol", "roles", "paso a paso", "pasos", "evidencia", "escalamiento",
    "segregacion", "plazo", "codigos de motivo",
)
AGGREGATE_WORDS = (
    "how many", "which employees", "what employees", "list", "total number",
    "summary", "number of", "who failed", "count", "all exceptions", "open exceptions",
    "cuantos", "cuantas", "que empleados", "cuales empleados", "lista de", "listar",
    "resumen", "numero de", "quienes fallaron", "quien fallo", "conteo",
)
READINESS_WORDS = (
    "ready for approval", "ready to approve", "ready to be approved", "approval readiness",
    "is payroll ready", "is the payroll ready", "can we approve", "can payroll be approved",
    "lista para aprobacion", "lista para aprobar", "lista para su aprobacion", "listo para aprobar",
    "podemos aprobar", "se puede aprobar", "esta lista la nomina", "la nomina esta lista",
)
LEGAL_WORDS = (
    "mexico", "colombia", "chile", "peru", "argentina", "brazil", "brasil", "spain", "espana",
    "usa", "united states", "estados unidos", "isr", "imss", "sat", "dian", "sunat", "afp",
    "law", "laws", "legislation", "legal", "ley", "leyes", "legislacion", "tax rate", "tasa de impuesto",
)
DOMAIN_WORDS = (
    "payroll", "nomina", "employee", "employees", "empleado", "empleados", "validation",
    "validations", "validacion", "validaciones", "exception", "exceptions", "excepcion",
    "excepciones", "tolerance", "tolerancia", "gross", "bruto", "net", "neto", "deduction",
    "deductions", "deduccion", "deducciones", "salary", "salario", "approval", "aprobacion",
    "approve", "aprobar", "approver", "aprobador", "preparer", "preparador", "provider",
    "proveedor", "reason code", "run", "corrida", "overtime", "horas extra", "input", "inputs",
    "insumo", "insumos", "pass", "fail", "missing", "faltante", "invalid", "invalido", "engine",
    "motor", "blueprint", "sop", "difference", "diferencia", "ai assistant", "asistente",
    "out_of_tolerance", "missing_input", "invalid_input", "within_tolerance", "pay", "pago",
) + POLICY_WORDS + AGGREGATE_WORDS


def keyword_intent(message: str, has_employee_in_message: bool, has_employee_in_session: bool,
                   last_intent: str | None = None) -> Intent:
    """Deterministic intent classification used as fallback and by the fake LLM.

    Order matters: the most specific signals are checked first.
    """
    text = normalize(message)

    if _has(text, LEGAL_WORDS):
        return "out_of_scope"
    if _has(text, READINESS_WORDS):
        return "readiness_question"
    if _has(text, AGGREGATE_WORDS):
        return "aggregate_lookup"

    asks_why = _has(text, WHY)
    mentions_result = _has(text, RESULT_WORDS)
    mentions_policy = _has(text, POLICY_WORDS)

    if asks_why and (has_employee_in_message or mentions_result
                     or (has_employee_in_session and not mentions_policy)):
        return "validation_explanation"
    if has_employee_in_message and not mentions_policy:
        # "And EMP026?" after an explanation keeps the same kind of question.
        if not mentions_result and not asks_why and last_intent in ("validation_explanation", "validation_lookup"):
            return last_intent  # type: ignore[return-value]
        return "validation_lookup"
    if mentions_result and not mentions_policy:
        return "validation_lookup"
    if mentions_policy or _has(text, DOMAIN_WORDS) or asks_why:
        return "policy_question"
    if len(text.split()) <= 3:
        return "unclear"
    return "out_of_scope"


def mentions_legal_or_real_country(message: str) -> bool:
    return _has(normalize(message), LEGAL_WORDS)


# --------------------------------------------------------- ES -> EN glossary
# Used only by the FAKE LLM to rewrite Spanish questions into an English search
# query, mimicking what the real LLM does (the knowledge base is in English).
GLOSSARY = (
    ("pago neto", "net pay"), ("salario bruto", "gross pay"), ("pago bruto", "gross pay"),
    ("horas extra", "overtime"), ("salario base", "base salary"), ("cuatro ojos", "four-eyes"),
    ("valor del proveedor", "provider value"), ("codigo de motivo", "reason code"),
    ("tolerancia", "tolerance"), ("neto", "net pay"), ("bruto", "gross pay"),
    ("deducciones", "deductions"), ("deduccion", "deduction"), ("aprobacion", "approval"),
    ("aprobar", "approve"), ("aprueba", "approves"), ("nomina", "payroll"),
    ("excepciones", "exceptions"), ("excepcion", "exception"), ("procedimiento", "procedure"),
    ("proceso", "process"), ("revision", "review"), ("revisar", "review"), ("faltante", "missing"),
    ("falta", "missing"), ("invalido", "invalid"), ("negativo", "negative"), ("negativa", "negative"),
    ("evidencia", "evidence"), ("corrida", "run"), ("validacion", "validation"),
    ("quien", "who"), ("preparador", "preparer"), ("aprobador", "approver"),
    ("requisitos", "prerequisites"), ("diferencia", "difference"), ("proveedor", "provider"),
    ("empleado", "employee"), ("plazo", "deadline"), ("escalamiento", "escalation"),
    ("asistente", "AI assistant"), ("calcula", "calculated"), ("calculo", "calculation"),
    ("regla", "rule"), ("igual", "equal"), ("exactamente", "exactly"), ("resolver", "resolve"),
    ("insumo", "input"), ("valor", "value"), ("incluyen", "included"), ("permite", "allowed"),
    ("permitida", "allowed"), ("produce", "produce"), ("antes", "before"), ("puede", "can"),
)


def glossary_to_english(message: str) -> str:
    text = normalize(message)
    for spanish, english in GLOSSARY:
        text = text.replace(f" {spanish} ", f" {english} ")
    return " ".join(text.split())
