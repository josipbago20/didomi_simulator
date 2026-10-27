"""Didomi (Feathers) error bodies: {name, message, code, className, errors}."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

NAMES = {
    400: ("BadRequest", "bad-request"),
    401: ("NotAuthenticated", "not-authenticated"),
    403: ("Forbidden", "forbidden"),
    404: ("NotFound", "not-found"),
    405: ("MethodNotAllowed", "method-not-allowed"),
    429: ("TooManyRequests", "too-many-requests"),
    500: ("GeneralError", "general-error"),
}


class DidomiError(Exception):
    def __init__(self, code: int, message: str, errors: dict | None = None, headers: dict | None = None):
        self.code, self.message, self.errors, self.headers = code, message, errors or {}, headers


def body(code: int, message: str, errors: dict | None = None) -> dict:
    name, class_name = NAMES.get(code, ("GeneralError", "general-error"))
    return {"name": name, "message": message, "code": code, "className": class_name, "errors": errors or {}}


def install(app: FastAPI) -> None:
    @app.exception_handler(DidomiError)
    async def _didomi(_: Request, exc: DidomiError):
        return JSONResponse(body(exc.code, exc.message, exc.errors), status_code=exc.code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = {".".join(str(p) for p in e["loc"][1:]) or "body": e["msg"] for e in exc.errors()}
        return JSONResponse(body(400, "Invalid request: " + "; ".join(f"{k}: {v}" for k, v in errors.items()),
                                 errors), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        message = "Page not found" if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(body(exc.status_code, message), status_code=exc.status_code)
