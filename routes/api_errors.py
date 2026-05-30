from __future__ import annotations

from typing import Any

from flask import jsonify, request
from werkzeug.exceptions import HTTPException


_DEFAULT_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    500: "internal_server_error",
}


def api_error_payload(
    message: str,
    *,
    status: int,
    code: str | None = None,
    details: dict[str, Any] | list[Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": message,
        "code": code or _DEFAULT_ERROR_CODES.get(status, "error"),
        "status": status,
    }
    if details is not None:
        payload["details"] = details
    if extra:
        payload.update(extra)
    return payload


def api_error_response(
    message: str,
    *,
    status: int,
    code: str | None = None,
    details: dict[str, Any] | list[Any] | None = None,
    extra: dict[str, Any] | None = None,
):
    return jsonify(api_error_payload(message, status=status, code=code, details=details, extra=extra)), status


def wants_api_error() -> bool:
    return request.path.startswith("/api/")


def handle_api_http_exception(error: HTTPException):
    if not wants_api_error():
        return error
    status = error.code or 500
    return api_error_response(
        error.description or error.name,
        status=status,
        code=_DEFAULT_ERROR_CODES.get(status, error.name.lower().replace(" ", "_")),
    )
