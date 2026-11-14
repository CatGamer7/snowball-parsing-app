import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import ValidationError

from api.errors import APIError
from api.model_catalog import MODELS
from api.schemas import (
    ErrorResponse,
    GLiNERSettings,
    StartRequest,
    StartResponse,
    WikiNeuralSettings,
)
from api.vk_routes import convert_vk_error, detect_token
from core.models import Record
from core.jobs import CollectionProgress, CollectionRecords, job_store
from services.collection import run_collection
from vk.client import VKAPIError, VKClient
from vk.source import VKDataSource


logger = logging.getLogger("snowball.api")

router = APIRouter(prefix="/collection", tags=["collection"])

SETTINGS_SCHEMAS = {
    "urchade/gliner_multi-v2.1": GLiNERSettings,
    "Babelscape/wikineural-multilingual-ner": WikiNeuralSettings,
}

KNOWN_MODEL_IDS = {model["id"] for model in MODELS}


def validate_models(selected_models: dict[str, dict]) -> None:
    # Сначала проверяем имена всех выбранных моделей.
    for model_id in selected_models:
        if model_id not in KNOWN_MODEL_IDS:
            raise APIError(
                status_code=404,
                code="MODEL_NOT_FOUND",
                message=f"Модель {model_id} не найдена",
            )

    # Затем проверяем настройки каждой модели.
    for model_id, settings in selected_models.items():
        settings_schema = SETTINGS_SCHEMAS.get(model_id)

        if settings_schema is None:
            raise APIError(
                status_code=500,
                code="INTERNAL_ERROR",
                message="Для модели не настроена проверка параметров",
            )

        try:
            settings_schema.model_validate(settings)
        except ValidationError:
            raise APIError(
                status_code=422,
                code="VALIDATION_ERROR",
                message=f"Некорректные настройки модели {model_id}",
            ) from None


async def load_seeds(
    source: VKDataSource,
    request: StartRequest,
) -> list[Record]:
    records: list[Record] = []
    seen: set[str] = set()

    for index, seed in enumerate(request.seeds, start=1):
        try:
            found = await source.get_by_ids(
                kind=seed.type,
                ids=[seed.id],
            )

        except VKAPIError as exc:
            # Ошибки формата ID, отсутствующей или недоступной записи.
            if exc.code in {15, 18, 30, 100, 113, 200, 203}:
                raise APIError(
                    status_code=422,
                    code="VALIDATION_ERROR",
                    message=(
                        f"Начальная запись №{index} "
                        "не найдена или недоступна"
                    ),
                ) from None

            raise

        if len(found) != 1:
            raise APIError(
                status_code=422,
                code="VALIDATION_ERROR",
                message=(
                    f"Начальная запись №{index} "
                    "не найдена или недоступна"
                ),
            )

        record = found[0]

        if record.source != "vk" or record.kind != seed.type:
            raise APIError(
                status_code=502,
                code="VK_UNAVAILABLE",
                message="VK API вернул неожиданный тип записи",
            )

        # Одна запись может быть передана и по ID, и по короткому имени.
        # После получения из VK оставляем только уникальные записи.
        if record.key not in seen:
            seen.add(record.key)
            records.append(record)

    return records


@router.get(
    "/{collection_id}/progress",
    response_model=CollectionProgress,
    summary="Получить состояние и прогресс сбора",
    responses={404: {"model": ErrorResponse, "description": "Задание не найдено"}},
)
def get_collection_progress(collection_id: str) -> CollectionProgress:
    progress = job_store.get(collection_id)

    if progress is None:
        raise APIError(
            status_code=404,
            code="COLLECTION_NOT_FOUND",
            message="Задание сбора не найдено",
        )

    return progress


@router.get(
    "/{collection_id}/records",
    response_model=CollectionRecords,
    summary="Получить страницу собранных постов",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_collection_records(
    collection_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> CollectionRecords:
    page = job_store.get_records(collection_id, offset=offset, limit=limit)
    if page is None:
        raise APIError(404, "COLLECTION_NOT_FOUND", "Задание сбора не найдено")
    total, items = page
    return CollectionRecords(
        collection_id=collection_id, total=total, offset=offset, limit=limit, items=items,
    )


@router.post(
    "/start",
    status_code=202,
    response_model=StartResponse,
    summary="Принять задание на сбор данных",
    description=(
        "Проверяет запрос, токен VK и начальные записи. "
        "Ответ running сохранён для совместимости и означает принятие задания. "
        "Фактическое состояние доступно через эндпоинт прогресса. "
        "Сбор выполняется в фоне с GLiNER; ошибки выполнения доступны в прогрессе."
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Токен не прошёл авторизацию",
        },
        403: {
            "model": ErrorResponse,
            "description": "Ключ сообщества не подходит",
        },
        404: {
            "model": ErrorResponse,
            "description": "Модель не найдена",
        },
        422: {
            "model": ErrorResponse,
            "description": "Некорректные настройки или начальные записи",
        },
        429: {
            "model": ErrorResponse,
            "description": "Превышен лимит запросов",
        },
        500: {
            "model": ErrorResponse,
            "description": "Внутренняя ошибка бэкенда",
        },
        502: {
            "model": ErrorResponse,
            "description": "Ошибка обращения к VK API",
        },
    },
)
async def start_collection(
    request: StartRequest,
    background_tasks: BackgroundTasks,
) -> StartResponse:
    validate_models(request.rules.models)

    token = request.token.get_secret_value()

    try:
        # Один клиент используется для проверки токена
        # и получения начальных записей.
        async with VKClient(token) as client:
            await detect_token(client, token)

            source = VKDataSource(client)
            records = await load_seeds(source, request)
            vk_requests_count = client.requests_count

    except VKAPIError as exc:
        raise convert_vk_error(exc) from None

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise APIError(
                status_code=429,
                code="VK_QUOTA_EXCEEDED",
                message="Превышен лимит запросов к VK API",
            ) from None

        raise APIError(
            status_code=502,
            code="VK_UNAVAILABLE",
            message="VK API вернул ошибку HTTP",
        ) from None

    except httpx.RequestError:
        raise APIError(
            status_code=502,
            code="VK_UNAVAILABLE",
            message="Не удалось подключиться к VK API",
        ) from None

    except (ValueError, KeyError, TypeError):
        raise APIError(
            status_code=502,
            code="VK_UNAVAILABLE",
            message="Не удалось обработать ответ VK API",
        ) from None

    job = job_store.create(vk_requests_count=vk_requests_count)

    background_tasks.add_task(
        run_collection,
        job.collection_id,
        records,
        vk_requests_count,
        request,
    )

    return StartResponse(collection_id=job.collection_id)
