import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from packages.core.exceptions import AppException

logger = logging.getLogger("app.errors")


def register_error_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(
            "AppException | %s %s | %d | %s",
            request.method, request.url.path,
            exc.status_code, exc.message,
            extra={"path": request.url.path, "status": exc.status_code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "UnhandledException | %s %s | %s: %s",
            request.method, request.url.path,
            type(exc).__name__, exc,
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"error": f"{type(exc).__name__}: {exc}"},
        )
