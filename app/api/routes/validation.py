"""GET /validation — persisted Engine results through the read-only Validation Tool.

No LLM is involved (spec §13) and the Engine is never executed here (C3-09).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_state
from app.api.errors import ApiError
from app.api.schemas import ValidationResponse
from app.api.state import ApiState
from app.validation.tool import ToolError

router = APIRouter(tags=["validation"])


@router.get("/validation", response_model=ValidationResponse)
def validation(
    period: str | None = Query(default=None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    employee_id: str | None = Query(default=None, pattern=r"^EMP\d{3}$"),
    validation_type: Literal["gross_pay", "total_deductions", "net_pay"] | None = None,
    status: Literal["PASS", "FAIL"] | None = None,
    state: ApiState = Depends(get_state),
) -> ValidationResponse:
    if period is None:
        periods = state.tool.available_periods()
        if not periods:
            raise ApiError(404, "no_validation_run", "No validation run exists yet. Run the validation batch first.")
        if len(periods) > 1:
            raise ApiError(400, "period_required", f"Several runs exist; choose a period: {', '.join(periods)}")
        period = periods[0]

    try:
        result = state.tool.query(period, employee_id=employee_id, validation_type=validation_type, status=status)
    except ToolError as error:
        if "No validation run" in str(error):
            raise ApiError(404, "no_validation_run", str(error)) from None
        raise ApiError(503, "run_integrity_failed",
                       "The validation run failed its integrity check; run the validation batch again.") from None
    return ValidationResponse(**result.to_dict())
