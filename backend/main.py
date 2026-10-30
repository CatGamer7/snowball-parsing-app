import logging
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from api.errors import (
    APIError,
    api_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from api.model_catalog import MODELS
from api.schemas import ModelInfo
from config import HOST, PORT


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("snowball.api")

app = FastAPI(title="snowball-parsing-app")

app.add_exception_handler(APIError, api_error_handler)

app.add_exception_handler(
    RequestValidationError,
    validation_error_handler,
)

app.add_exception_handler(Exception, internal_error_handler)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000

        logger.error(
            "%s %s -> unhandled error | %.1f ms",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "%s %s -> %s | %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )

    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/collection/models",
    response_model=list[ModelInfo],
)
def list_models() -> list[dict]:
    return MODELS


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        access_log=False,
    )