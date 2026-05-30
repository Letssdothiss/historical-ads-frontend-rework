"""Custom error classes"""

from fastapi import HTTPException


class AppError(HTTPException):
    """Base application error"""

    def __init__(self, status_code: int, detail: dict):
        self.status_code = status_code
        self.detail = detail
        super().__init__(status_code=status_code, detail=detail)


class NotFoundError(AppError):
    """Resource not found"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(404, {"error": "not_found", "message": message})


class BadRequestError(AppError):
    """Bad request error"""

    def __init__(self, message: str = "Bad request"):
        super().__init__(400, {"error": "bad_request", "message": message})


class ExternalAPIError(AppError):
    """External API error"""

    def __init__(self, message: str = "External API error"):
        super().__init__(502, {"error": "external_api_error", "message": message})


class TimeoutError(AppError):
    """Timeout error"""

    def __init__(self, message: str = "Request timeout"):
        super().__init__(504, {"error": "timeout", "message": message})


class ConflictError(AppError):
    """Conflict error"""

    def __init__(self, message: str = "Conflict"):
        super().__init__(409, {"error": "conflict", "message": message})
