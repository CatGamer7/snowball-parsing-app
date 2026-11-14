import logging
import os
from pathlib import Path
import time

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.collection_routes import router as collection_router
from api.errors import (
    APIError,
    api_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from api.model_catalog import MODELS
from api.schemas import ModelInfo
from api.vk_routes import router as vk_router
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

app.include_router(vk_router)
app.include_router(collection_router)


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    instance = os.environ.get("SNOWBALL_INSTANCE_ID")
    if instance:
        response.headers["X-Snowball-Instance"] = instance
    return {"status": "ok"}


@app.get(
    "/collection/models",
    response_model=list[ModelInfo],
)
def list_models() -> list[dict]:
    return MODELS


# В установщике Electron открывает эту страницу: API и UI имеют один origin.
ui_directory = os.environ.get("SNOWBALL_UI_DIR")
if ui_directory:
    directory = Path(ui_directory).resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("Не найдены файлы интерфейса установленного приложения")
    app.mount("/app", StaticFiles(directory=str(directory), html=True), name="desktop-ui")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        access_log=False,
    )