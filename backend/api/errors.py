import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger("snowball.api")


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)

        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(
    request: Request,
    exc: APIError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Некорректные входные данные",
            }
        },
    )


async def internal_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "Необработанная ошибка: %s %s | %s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка бэкенда",
            }
        },
    )