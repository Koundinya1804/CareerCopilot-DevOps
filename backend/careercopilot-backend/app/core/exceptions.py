"""
app/core/exceptions.py
──────────────────────
Application-level exception hierarchy plus FastAPI exception handlers.

All domain exceptions extend AppException which carries an HTTP status code,
a machine-readable error code, and a human-readable message.  Handlers at the
bottom convert them to consistent JSON responses:

    {
        "success": false,
        "error": {
            "code": "USER_NOT_FOUND",
            "message": "No user found with the provided identifier.",
            "details": null
        }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import JWTError
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Base ──────────────────────────────────────────────────────────────────────
class AppException(Exception):
    """Base class for all application exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


# ── Auth Exceptions ───────────────────────────────────────────────────────────
class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed.", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class InvalidCredentialsError(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="The email or password you entered is incorrect.",
            code="INVALID_CREDENTIALS",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class TokenExpiredError(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="Your session has expired. Please log in again.",
            code="TOKEN_EXPIRED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class TokenInvalidError(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="The provided token is invalid.",
            code="TOKEN_INVALID",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class InsufficientPermissionsError(AppException):
    def __init__(self, required_role: str = "admin") -> None:
        super().__init__(
            message=f"This action requires the '{required_role}' role.",
            code="INSUFFICIENT_PERMISSIONS",
            status_code=status.HTTP_403_FORBIDDEN,
        )


# ── Resource Exceptions ───────────────────────────────────────────────────────
class NotFoundError(AppException):
    def __init__(self, resource: str = "Resource", identifier: Any = None) -> None:
        detail = f" with identifier '{identifier}'" if identifier else ""
        super().__init__(
            message=f"{resource}{detail} was not found.",
            code=f"{resource.upper().replace(' ', '_')}_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "A resource with this data already exists.") -> None:
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
        )


class ValidationError(AppException):
    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class RateLimitError(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="Too many requests. Please slow down.",
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ServiceUnavailableError(AppException):
    def __init__(self, service: str = "External service") -> None:
        super().__init__(
            message=f"{service} is temporarily unavailable.",
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ── Response builder ──────────────────────────────────────────────────────────
def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=content)


# ── Exception Handlers ────────────────────────────────────────────────────────
def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the FastAPI app instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "app_exception",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            {"field": ".".join(str(l) for l in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        logger.info(
            "validation_error",
            path=request.url.path,
            errors=field_errors,
        )
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Request validation failed. Check the 'details' field.",
            field_errors,
        )

    @app.exception_handler(JWTError)
    async def jwt_exception_handler(request: Request, exc: JWTError) -> JSONResponse:
        logger.warning("jwt_error", path=request.url.path, error=str(exc))
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_INVALID",
            "The provided token is invalid or has expired.",
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        logger.error("db_integrity_error", path=request.url.path, error=str(exc.orig))
        return _error_response(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "A record with this data already exists.",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred. Our team has been notified.",
        )
