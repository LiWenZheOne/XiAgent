from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from xiagent.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    XiAgentError,
)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(XiAgentError, xiagent_error_handler)


async def xiagent_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, XiAgentError):
        return _error_response(500, "internal_error", "Internal server error", {})
    return _error_response(
        _status_code(exc),
        exc.code,
        exc.message,
        exc.details,
    )


def _status_code(exc: XiAgentError) -> int:
    if isinstance(exc, PermissionDeniedError):
        return 403
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, ValidationError):
        return 400
    return 500


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )
