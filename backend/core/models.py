from pydantic import BaseModel, ConfigDict


class Record(BaseModel):

    model_config = ConfigDict(frozen=True)

    source: str  # источник данных, например "vk"
    kind: str    # тип записи внутри источника, например "group"
    id: str      # идентификатор внутри источника

    @property
    def key(self) -> str:

        return f"{self.source}:{self.kind}:{self.id}"