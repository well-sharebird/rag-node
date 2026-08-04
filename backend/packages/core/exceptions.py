import logging

logger = logging.getLogger("app.exceptions")


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500, detail: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        logger.info("NotFoundException: %s", message)
        super().__init__(message, status_code=404)


class ValidationException(AppException):
    def __init__(self, message: str = "Validation error"):
        logger.info("ValidationException: %s", message)
        super().__init__(message, status_code=422)


class ProcessingException(AppException):
    def __init__(self, message: str = "Processing error"):
        logger.error("ProcessingException: %s", message)
        super().__init__(message, status_code=500)
