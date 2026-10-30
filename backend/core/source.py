from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from core.models import Record


class SearchQuery(BaseModel):

    model_config = ConfigDict(frozen=True)

    source: str      # какому источнику адресован запрос, например "vk"
    kind: str        # какие записи искать, например "group"
    text: str        # текст запроса
    limit: int = 20  # сколько записей вернуть максимум


class DataSource(ABC):

    name: str  # совпадает с Record.source и SearchQuery.source

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Record]:
        """Выполнить поисковый запрос."""

    @abstractmethod
    async def get_by_ids(self, kind: str, ids: list[str]) -> list[Record]:
        """Получить записи по идентификаторам (например, начальные записи пользователя)."""