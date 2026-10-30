from core.models import Record
from core.source import DataSource, SearchQuery
from vk.client import VKClient
from vk.models import VKGroup, VKPost, VKUser

GROUP_FIELDS = "description,members_count"
USER_FIELDS = "screen_name"
MAX_SEARCH_COUNT = 200  # максимум постов за один вызов newsfeed.search


class VKDataSource(DataSource):

    name = "vk"

    def __init__(self, client: VKClient):
        self._client = client

    async def get_by_ids(self, kind: str, ids: list[str]) -> list[Record]:
        if not ids:
            return []
        joined = ",".join(ids)

        if kind == "group":
            response = await self._client.call(
                "groups.getById", group_ids=joined, fields=GROUP_FIELDS
            )
            items = response["groups"] if isinstance(response, dict) else response
            return [VKGroup.from_api(item) for item in items]

        if kind == "user":
            items = await self._client.call(
                "users.get", user_ids=joined, fields=USER_FIELDS
            )
            return [VKUser.from_api(item) for item in items]

        if kind == "post":
            items = await self._client.call("wall.getById", posts=joined)
            items = items["items"] if isinstance(items, dict) else items
            return [VKPost.from_api(item) for item in items]

        raise ValueError(f"Неизвестный тип записи VK: {kind}")

    async def search(self, query: SearchQuery) -> list[Record]:
        if query.source != self.name:
            raise ValueError(f"Запрос адресован источнику {query.source}, а не {self.name}")

        response = await self._client.call(
            "newsfeed.search",
            q=query.text,
            count=min(query.limit, MAX_SEARCH_COUNT),
            extended=1,
            fields=f"{GROUP_FIELDS},{USER_FIELDS}",
        )

        if query.kind == "post":
            return [VKPost.from_api(item) for item in response["items"]]

        if query.kind == "group":
            return [VKGroup.from_api(item) for item in response.get("groups", [])]

        if query.kind == "user":
            return [VKUser.from_api(item) for item in response.get("profiles", [])]

        raise ValueError(f"Неизвестный тип записи VK: {query.kind}")