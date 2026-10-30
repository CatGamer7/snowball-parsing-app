from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)


NonBlankString = Annotated[
    str,
    Field(min_length=1, pattern=r"\S"),
]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValidateRequest(APIModel):
    token: SecretStr = Field(min_length=1)

    @field_validator("token")
    @classmethod
    def token_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Токен не должен быть пустым")

        return value


class VKUserInfo(APIModel):
    id: int
    name: str


class ValidateResponse(APIModel):
    valid: Literal[True] = True
    token_type: Literal["user", "service"]
    user: VKUserInfo | None = None


class ModelInfo(APIModel):
    id: NonBlankString
    name: NonBlankString
    description: str
    task: Literal["ner"]
    settings_schema: dict[str, Any]


class ErrorDetail(APIModel):
    code: Literal[
        "INVALID_TOKEN",
        "UNSUPPORTED_TOKEN_TYPE",
        "MODEL_NOT_FOUND",
        "VALIDATION_ERROR",
        "VK_QUOTA_EXCEEDED",
        "VK_UNAVAILABLE",
        "INTERNAL_ERROR",
    ]
    message: str


class ErrorResponse(APIModel):
    error: ErrorDetail