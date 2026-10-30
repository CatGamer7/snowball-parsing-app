import logging
import time

import uvicorn
from fastapi import FastAPI, Request

from config import HOST, PORT
from model_catalog import MODELS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("snowball.api")

app = FastAPI(title="snowball-parsing-app")


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


@app.get("/collection/models")
def list_models() -> list[dict]:
    return MODELS


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        access_log=False,
    )