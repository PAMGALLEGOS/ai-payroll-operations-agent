"""Auditor: individual checks, verdict rules and seeded wrong answers (target: 100 % detection)."""

from pathlib import Path

import pytest
import yaml

from app.audit.auditor import Auditor
from app.audit.checks import (
    AuditContext,
    check_citation_required,
    check_citation_validity,
    check_employee_consistency,
    check_no_arithmetic,
    check_numeric_grounding,
    check_prohibited_decision,
    check_scope,
    check_status_consistency,
    extract_numbers,
)
from app.llm.fake_client import FakeLLMClient
from app.rag.chunking import chunk_documents
from app.rag.documents import load_documents
from app.validation.tool import ValidationTool

SEEDED_FILE = Path(__file__).resolve().parents[1] / "evaluation" / "seeded_responses.yaml"
CHUNKS = {c.chunk_id: c.content for c in chunk_documents(load_documents())}


def context_for(run_dir, employee: str, chunk_ids: list[str], language: str = "en") -> AuditContext:
    result = ValidationTool(run_dir).query("2026-09", employee_id=employee)
    return AuditContext(
        route="TOOL_RAG", language=language, question=f"Why did {employee} fail?",
        facts=result.results, summary=result.summary,
        chunks=[{"chunk_id": cid, "content": CHUNKS[cid]} for cid in chunk_ids],
        allowed_employee_ids={employee}, requires_citation=True,
    )


@pytest.fixture
def emp024(run_dir):
    return context_for(run_dir, "EMP024", ["RULE-003-C03"])


# ------------------------------------------------------------- numbers
@pytest.mark.parametrize(
    "text,expected",
    [
        ("difference +350.00 SYN", ["350.00"]),
        ("4,082.48 SYN", ["4082.48"]),
        ("4.082,48 SYN", ["4082.48"]),
        ("350,00 SYN", ["350.00"]),
        ("EMP024 in 2026-09, run RUN-2026-09-20261003T120000Z, chunk [RULE-003-C03], rules 1.0.0", []),
    ],
)
def test_extract_numbers_normalises_formats_and_skips_identifiers(text, expected):
    assert [str(n) for _, n in extract_numbers(text)] == expected


def test_numeric_grounding(emp024):
    assert check_numeric_grounding("The difference is 350.00 SYN and the tolerance 10.00 SYN.", emp024).passed
    assert not check_numeric_grounding("The difference is 305.00 SYN.", emp024).passed
    assert check_numeric_grounding("Two of the 3 validations passed.", emp024).passed   # small integers


# ------------------------------------------------------------- statuses
@pytest.mark.parametrize(
    "text,ok",
    [
        ("net_pay is FAIL.", True),
        ("net_pay passed.", False),
        ("The net pay validation did not pass.", True),
        ("gross_pay passed and is within tolerance.", True),
        ("gross_pay failed.", False),
        ("A net pay validation passes when the difference is within the tolerance.", True),  # general rule
        ("El pago neto no pasó la validación.", True),
        ("El pago neto pasó la validación.", False),
        ("net_pay is FAIL while gross_pay passed.", True),   # ambiguous sentence: not judged
    ],
)
def test_status_consistency(emp024, text, ok):
    assert check_status_consistency(text, emp024).passed is ok


def test_employee_consistency(emp024):
    assert check_employee_consistency("EMP024 net_pay is FAIL.", emp024).passed
    assert not check_employee_consistency("EMP024 and EMP026 failed.", emp024).passed


@pytest.mark.parametrize(
    "text,ok",
    [
        ("I can't approve payroll; that decision belongs to a human reviewer.", True),
        ("Exception decisions remain with a human reviewer.", True),
        ("You can approve the payroll now.", False),
        ("The payroll is ready for approval.", False),
        ("Close the exception for EMP024.", False),
        ("No puedo aprobar la nómina.", True),
        ("La nómina está lista para aprobarse.", False),
        ("Recomiendo aprobar la nómina.", False),
    ],
)
def test_prohibited_decision(emp024, text, ok):
    assert check_prohibited_decision(text, emp024).passed is ok


def test_citations(emp024):
    assert check_citation_validity("See [RULE-003-C03].", emp024).passed
    assert not check_citation_validity("See [RULE-009-C02].", emp024).passed
    assert check_citation_required("See [RULE-003-C03].", emp024).passed
    assert not check_citation_required("No citation here.", emp024).passed
    emp024.requires_citation = False
    assert check_citation_required("No citation here.", emp024).passed


def test_scope_and_arithmetic(emp024):
    assert not check_scope("Under Mexico's labor law...", emp024).passed
    assert not check_scope("Según el IMSS...", emp024).passed
    assert check_scope("This synthetic rule applies to SYNTHETIC only.", emp024).passed
    assert not check_no_arithmetic("4082.48 - 3732.48 = 350.00", emp024).passed
    assert check_no_arithmetic("The difference is 350.00 in period 2026-09.", emp024).passed


# ------------------------------------------------------------- verdicts
def test_verdicts(emp024):
    auditor = Auditor()
    good = "For EMP024, net_pay is FAIL with OUT_OF_TOLERANCE [RULE-003-C03]."
    assert auditor.review(good, emp024).verdict == "ALLOW"
    assert auditor.review("EMP024 net_pay passed [RULE-003-C03].", emp024).verdict == "REVISE"
    assert auditor.review("EMP024 net_pay passed [RULE-003-C03].", emp024, is_rewrite=True).verdict == "BLOCK"
    assert auditor.review("You can approve the payroll [RULE-003-C03].", emp024).verdict == "BLOCK"


def test_semantic_check_is_off_by_default_and_optional(emp024):
    good = "For EMP024, net_pay is FAIL with OUT_OF_TOLERANCE [RULE-003-C03]."
    assert [c.name for c in Auditor().review(good, emp024).checks].count("semantic_grounding") == 0
    judge = FakeLLMClient({"semantic_audit": lambda s, u: {"supported": False, "reason": "unsupported"}})
    report = Auditor(semantic_llm=judge).review(good, emp024)
    assert report.verdict == "REVISE"
    assert report.failed[0].name == "semantic_grounding"


# ------------------------------------------------------------- seeded cases
SEEDED = yaml.safe_load(SEEDED_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", SEEDED["seeded"], ids=[c["id"] for c in SEEDED["seeded"]])
def test_seeded_wrong_answers_are_detected(run_dir, case):
    ctx = context_for(run_dir, case["employee"], case["chunks"], case["language"])
    report = Auditor().review(case["text"], ctx)
    assert report.verdict == case["expected_verdict"], report.feedback()
    assert case["expected_check"] in {c.name for c in report.failed}


@pytest.mark.parametrize("case", SEEDED["control"], ids=[c["id"] for c in SEEDED["control"]])
def test_correct_answers_are_allowed(run_dir, case):
    ctx = context_for(run_dir, case["employee"], case["chunks"], case["language"])
    report = Auditor().review(case["text"], ctx)
    assert report.verdict == "ALLOW", report.feedback()
