"""Uniform JSON errors: {"error", "message", "trace_id"} — never a stack trace."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.observability.context import current_trace_id


class ApiError(HTTPException):
    def __init__(self, status_code: int, error: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.error = error


def _body(error: str, message: str, request: Request) -> dict:
    return {"error": error, "message": message,
            "trace_id": getattr(request.state, "trace_id", None) or current_trace_id()}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(_body(exc.error, str(exc.detail), request), status_code=exc.status_code)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(_body("http_error", str(exc.detail), request), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Report where and what, never echo the submitted values back.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'] if p != 'body')}: {err['msg']}" for err in exc.errors()
        )
        return JSONResponse(_body("invalid_request", problems, request), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        observer = getattr(request.app.state, "api", None)
        if observer is not None:
            observer.observer.emit("error", component="api", error_type=type(exc).__name__)
        return JSONResponse(
            _body("internal_error", "Unexpected error. No payroll result was changed.", request), status_code=500
        )
