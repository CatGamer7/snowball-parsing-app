import logging
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks
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


async def collection_placeholder(
    collection_id: str,
    seed_count: int,
    model_ids: list[str],
) -> None:
    logger.info(
        "Заглушка сбора: id=%s | seeds=%s | models=%s. "
        "Запрос принят; алгоритм сбора ещё не подключён.",
        collection_id,
        seed_count,
        ", ".join(model_ids),
    )


@router.post(
    "/start",
    status_code=202,
    response_model=StartResponse,
    summary="Принять задание на сбор данных",
    description=(
        "Проверяет запрос, токен VK и начальные записи. "
        "В текущей реализации фоновая задача является заглушкой: "
        "сбор данных и запуск ML-моделей ещё не выполняются."
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

    collection_id = str(uuid4())

    background_tasks.add_task(
        collection_placeholder,
        collection_id,
        len(records),
        list(request.rules.models),
    )

    return StartResponse(collection_id=collection_id)