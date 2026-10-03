"""Language detection, entity extraction, prohibited actions and keyword intent (EN / ES)."""

import pytest

from app.agent.entities import extract_entities, remainder_without_entities
from app.agent.keywords import glossary_to_english, is_prohibited_action, keyword_intent
from app.agent.language import detect_language


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Why did EMP024 fail?", "en"),
        ("What is the net pay tolerance?", "en"),
        ("¿Por qué falló EMP024?", "es"),
        ("Cual es la tolerancia del pago neto", "es"),
        ("Aprueba la nomina", "es"),
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_message_without_language_signal_keeps_session_language():
    assert detect_language("EMP024", default="es") == "es"
    assert detect_language("EMP024", default="en") == "en"


@pytest.mark.parametrize(
    "text,employees",
    [
        ("Why did EMP024 fail?", ["EMP024"]),
        ("why did emp024 fail", ["EMP024"]),
        ("status of EMP-024", ["EMP024"]),
        ("status of EMP 024", ["EMP024"]),
        ("Compare EMP023 and EMP024", ["EMP023", "EMP024"]),
        ("EMP024 and again EMP024", ["EMP024"]),
        ("employee 24", []),
    ],
)
def test_employee_extraction(text, employees):
    assert extract_entities(text).employee_ids == employees


def test_single_employee_property_is_none_when_several():
    assert extract_entities("EMP023 EMP024").employee_id is None


@pytest.mark.parametrize(
    "text,vtype",
    [
        ("net pay of EMP025", "net_pay"),
        ("pago neto de EMP025", "net_pay"),
        ("gross pay", "gross_pay"),
        ("salario bruto", "gross_pay"),
        ("total deductions", "total_deductions"),
        ("deducciones", "total_deductions"),
        ("gross and net", None),
        ("network issue", None),
    ],
)
def test_validation_type_extraction(text, vtype):
    assert extract_entities(text).validation_type == vtype


def test_period_and_status_extraction():
    entities = extract_entities("Which employees failed in 2026-09?")
    assert entities.period == "2026-09"
    assert entities.status_filter == "FAIL"
    assert extract_entities("¿Qué empleados fallaron?").status_filter == "FAIL"
    assert extract_entities("period 2026-13").period is None


def test_remainder_without_entities():
    assert remainder_without_entities("EMP024 please") == "please"
    assert remainder_without_entities("EMP024") == ""


@pytest.mark.parametrize(
    "text",
    [
        "Approve the payroll", "please approve payroll", "Can you close the exception for EMP026?",
        "Mark EMP024 as PASS", "override the result", "Change EMP024 to PASS",
        "Aprueba la nómina", "Por favor marca EMP024 como PASS", "¿Puedes cerrar la excepción de EMP026?",
        "cambia el resultado de EMP024", "Necesito que apruebes la nómina",
    ],
)
def test_prohibited_actions_are_detected(text):
    assert is_prohibited_action(text)


@pytest.mark.parametrize(
    "text",
    [
        "Can the AI assistant approve payroll?", "Who approves the payroll?", "Is payroll ready for approval?",
        "¿Puede el asistente aprobar la nómina?", "¿Quién aprueba la nómina?", "Why did EMP024 fail?",
        "Compare EMP023 and EMP024", "Explain the four-eyes process", "Muéstrame el resultado de EMP025",
    ],
)
def test_questions_are_not_prohibited_actions(text):
    assert not is_prohibited_action(text)


@pytest.mark.parametrize(
    "text,in_msg,in_session,last,expected",
    [
        ("What is the net pay tolerance?", False, False, None, "policy_question"),
        ("¿Cuál es la tolerancia del pago neto?", False, False, None, "policy_question"),
        ("Which deductions are included in total deductions?", False, False, None, "policy_question"),
        ("Did EMP024 pass validation?", True, False, None, "validation_lookup"),
        ("¿EMP024 pasó la validación?", True, False, None, "validation_lookup"),
        ("What was the difference?", False, True, None, "validation_lookup"),
        ("Why did EMP024 fail?", True, False, None, "validation_explanation"),
        ("¿Por qué falló el empleado?", False, False, None, "validation_explanation"),
        ("And EMP026?", True, True, "validation_explanation", "validation_explanation"),
        ("How many exceptions are there?", False, False, None, "aggregate_lookup"),
        ("¿Qué empleados fallaron?", False, False, None, "aggregate_lookup"),
        ("Is payroll ready for approval?", False, False, None, "readiness_question"),
        ("¿La nómina está lista para aprobarse?", False, False, None, "readiness_question"),
        ("What is the income tax rate in Mexico?", False, False, None, "out_of_scope"),
        ("What is the capital of France?", False, False, None, "out_of_scope"),
        ("Hmm?", False, False, None, "unclear"),
        ("Explain the four-eyes process", False, True, None, "policy_question"),
    ],
)
def test_keyword_intent(text, in_msg, in_session, last, expected):
    assert keyword_intent(text, in_msg, in_session, last) == expected


def test_glossary_rewrites_spanish_terms():
    assert "net pay" in glossary_to_english("¿Cuál es la tolerancia del pago neto?")
    assert "tolerance" in glossary_to_english("¿Cuál es la tolerancia del pago neto?")
