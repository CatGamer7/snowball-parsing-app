import logging

import httpx
from fastapi import APIRouter

from api.errors import APIError
from api.schemas import (
    ErrorResponse,
    ValidateRequest,
    ValidateResponse,
    VKUserInfo,
)
from vk.client import VKAPIError, VKClient


logger = logging.getLogger("snowball.api")

router = APIRouter(prefix="/vk", tags=["vk"])


def convert_vk_error(exc: VKAPIError) -> APIError:
    if exc.code in {5, 27, 28}:
        return APIError(
            status_code=401,
            code="INVALID_TOKEN",
            message="Токен VK недействителен или не прошёл авторизацию",
        )

    if exc.code in {6, 9, 29}:
        return APIError(
            status_code=429,
            code="VK_QUOTA_EXCEEDED",
            message="Превышен лимит запросов к VK API. Повторите попытку позже",
        )

    return APIError(
        status_code=502,
        code="VK_UNAVAILABLE",
        message=(
            "Не удалось проверить токен через VK API. "
            f"Код ошибки VK: {exc.code}"
        ),
    )


def unavailable_response() -> APIError:
    return APIError(
        status_code=502,
        code="VK_UNAVAILABLE",
        message="VK API вернул неожиданный ответ",
    )


async def detect_token(
    client: VKClient,
    token: str,
) -> ValidateResponse:
    async def call(method: str, **params):
        try:
            return await client.call(method, **params)
        except VKAPIError as exc:
            safe_message = exc.message.replace(token, "[TOKEN]")

            logger.warning(
                "VK diagnostic | method=%s | code=%s | message=%r",
                method,
                exc.code,
                safe_message,
            )
            raise

    try:
        profile = await call("account.getProfileInfo")

    except VKAPIError as exc:
        if exc.code == 27:
            # Подтверждаем действительность ключа сообщества.
            permissions = await call("groups.getTokenPermissions")

            if not isinstance(permissions, dict):
                raise unavailable_response()

            if "mask" not in permissions:
                raise unavailable_response()

            raise APIError(
                status_code=403,
                code="UNSUPPORTED_TOKEN_TYPE",
                message=(
                    "Ключ сообщества не подходит. "
                    "Используйте сервисный ключ или ключ пользователя"
                ),
            )

        if exc.code == 28:
            # Отказ пользовательского метода ещё не означает,
            # что сервисный ключ действителен.
            # Дополнительно проверяем чтение публичного профиля.
            users = await call("users.get", user_ids="1")

            if not isinstance(users, list) or not users:
                raise unavailable_response()

            user = users[0]

            if not isinstance(user, dict):
                raise unavailable_response()

            if type(user.get("id")) is not int:
                raise unavailable_response()

            return ValidateResponse(token_type="service")

        raise

    if not isinstance(profile, dict):
        raise unavailable_response()

    # Пользовательский метод выполнен успешно.
    # Получаем ID и имя владельца токена.
    users = await call("users.get")

    if not isinstance(users, list) or not users:
        raise unavailable_response()

    user = users[0]

    if not isinstance(user, dict):
        raise unavailable_response()

    user_id = user.get("id")
    first_name = user.get("first_name")
    last_name = user.get("last_name")

    if (
        type(user_id) is not int
        or not isinstance(first_name, str)
        or not isinstance(last_name, str)
    ):
        raise unavailable_response()

    return ValidateResponse(
        token_type="user",
        user=VKUserInfo(
            id=user_id,
            name=f"{first_name} {last_name}".strip(),
        ),
    )


async def validate_token(token: str) -> ValidateResponse:
    try:
        async with VKClient(token) as client:
            return await detect_token(client, token)

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
        raise unavailable_response() from None


@router.post(
    "/validate",
    response_model=ValidateResponse,
    response_model_exclude_none=True,
    summary="Проверить токен VK",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Токен не прошёл авторизацию",
        },
        403: {
            "model": ErrorResponse,
            "description": "Ключ сообщества не подходит",
        },
        422: {
            "model": ErrorResponse,
            "description": "Некорректные входные данные",
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
async def validate_vk_token(
    request: ValidateRequest,
) -> ValidateResponse:
    return await validate_token(request.token.get_secret_value())