from abc import ABC, abstractmethod

from core.models import Record
from core.source import SearchQuery


class Expander(ABC):

    @abstractmethod
    def expand(self, records: list[Record]) -> list[SearchQuery]:
        """Сформировать поисковые запросы для следующей волны расширения."""