import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
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


class GLiNERSettings(APIModel):
    labels: list[NonBlankString] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def labels_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Метки не должны повторяться")

        return value


class WikiNeuralSettings(APIModel):
    pass


class Seed(APIModel):
    type: Literal["group", "user", "post"]
    id: NonBlankString

    @model_validator(mode="after")
    def check_id(self) -> "Seed":
        if self.type == "post":
            if not re.fullmatch(r"-?[1-9]\d*_[1-9]\d*", self.id):
                raise ValueError(
                    "ID поста должен иметь вид owner_id_post_id"
                )
        else:
            if (
                "/" in self.id
                or any(character.isspace() for character in self.id)
            ):
                raise ValueError(
                    "Передайте ID или короткое имя, без URL и пробелов"
                )

        return self


class Rules(APIModel):
    models: dict[str, dict[str, Any]] = Field(min_length=1)
    threshold: float = Field(ge=0, le=1)
    max_depth: int = Field(default=2, ge=1, le=5)


class StartRequest(ValidateRequest):
    seeds: list[Seed] = Field(min_length=1)
    rules: Rules


class StartResponse(APIModel):
    collection_id: str
    status: Literal["running"] = "running"


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