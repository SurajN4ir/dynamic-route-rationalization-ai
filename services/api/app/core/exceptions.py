"""Centralized exception handling.

Every error response (validation, HTTP, application, or unhandled) is
normalized to the single envelope defined in
docs/architecture/05-api-specification.md:

    { "error": { "code": "string", "message": "string", "details": {} } }

Domain/service code should raise an AppError subclass rather than a bare
HTTPException, so the error always carries a stable machine-readable `code`
in addition to an HTTP status.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for application errors that should reach the client as a
    structured, well-known error rather than a generic 500."""

    code: str = "internal_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "Resource not found."


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "A required dependency is currently unavailable."


class UnprocessableEntityError(AppError):
    """A request body that is well-formed JSON but semantically invalid -
    e.g. telemetry referencing an unknown vehicle, or failing a
    domain-specific range check Pydantic's own field constraints can't
    express. Distinct from RequestValidationError (malformed/missing
    fields, handled by FastAPI itself)."""

    code = "unprocessable_entity"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "The request could not be processed."


def _error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error."
    return _error_response(exc.status_code, "http_error", detail)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "validation_error",
        "Request validation failed.",
        {"errors": jsonable_encoder(exc.errors())},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing request", exc_info=exc)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An unexpected error occurred."
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette's add_exception_handler is typed as taking a handler for the
    # exact `Exception` base type; passing a subclass-specific handler (the
    # documented FastAPI pattern) is correct at runtime but mypy can't see
    # it - see https://github.com/encode/starlette/discussions/2027.
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
