from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from xiagent.core.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    XiAgentError,
)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(XiAgentError, xiagent_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)


async def xiagent_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, XiAgentError):
        return _error_response(500, "internal_error", "Internal server error", {})
    return _error_response(
        _status_code(exc),
        exc.code,
        exc.message,
        exc.details,
    )


async def request_validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return _error_response(500, "internal_error", "Internal server error", {})
    return _error_response(
        422,
        "request_validation_failed",
        "Request validation failed",
        {"errors": _sanitize_validation_errors(exc.errors())},
    )


def _status_code(exc: XiAgentError) -> int:
    if isinstance(exc, AuthenticationError):
        return 401
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


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    return [_strip_input(error) for error in errors]


def _strip_input(value):
    if isinstance(value, dict):
        return {key: _strip_input(item) for key, item in value.items() if key != "input"}
    if isinstance(value, list):
        return [_strip_input(item) for item in value]
    return value
