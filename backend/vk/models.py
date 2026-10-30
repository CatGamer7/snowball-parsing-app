from typing import Literal

from core.models import Record


class VKGroup(Record):
    """Сообщество VK."""

    source: Literal["vk"] = "vk"
    kind: Literal["group"] = "group"
    name: str
    screen_name: str | None = None
    description: str | None = None
    members_count: int | None = None

    @classmethod
    def from_api(cls, data: dict) -> "VKGroup":

        return cls(
            id=str(data["id"]),
            name=data["name"],
            screen_name=data.get("screen_name"),
            description=data.get("description"),
            members_count=data.get("members_count"),
        )


class VKUser(Record):
    """Пользователь VK."""

    source: Literal["vk"] = "vk"
    kind: Literal["user"] = "user"
    first_name: str
    last_name: str
    screen_name: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "VKUser":

        return cls(
            id=str(data["id"]),
            first_name=data["first_name"],
            last_name=data["last_name"],
            screen_name=data.get("screen_name"),
        )


class VKPost(Record):
    """Пост на стене VK."""

    source: Literal["vk"] = "vk"
    kind: Literal["post"] = "post"
    owner_id: int  # автор: < 0 — сообщество, > 0 — пользователь
    text: str
    date: int      # время публикации, Unix timestamp

    @classmethod
    def from_api(cls, data: dict) -> "VKPost":
        
        return cls(
            id=f"{data['owner_id']}_{data['id']}",
            owner_id=data["owner_id"],
            text=data.get("text", ""),
            date=data["date"],
        )