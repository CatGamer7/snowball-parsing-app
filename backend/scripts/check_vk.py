import asyncio
import os

from dotenv import load_dotenv

from core.source import SearchQuery
from vk.client import VKAPIError, VKClient
from vk.source import VKDataSource


async def check(title: str, coro) -> None:
    print(f"\n--- {title}")
    try:
        for record in await coro:
            print(record.key, "|", record)
    except VKAPIError as e:
        print("Ошибка VK:", e.code, e.message)


async def main() -> None:
    load_dotenv()
    async with VKClient(os.environ["VK_TOKEN"]) as client:
        vk = VKDataSource(client)
        await check("get_by_ids: сообщества", vk.get_by_ids("group", ["vk"]))
        await check("get_by_ids: пользователи", vk.get_by_ids("user", ["durov"]))
        await check("search: посты", vk.search(SearchQuery(source="vk", kind="post", text="ТПУ", limit=3)))
        await check("search: сообщества-авторы", vk.search(SearchQuery(source="vk", kind="group", text="ТПУ", limit=10)))
        await check("search: пользователи-авторы", vk.search(SearchQuery(source="vk", kind="user", text="ТПУ", limit=10)))


asyncio.run(main())