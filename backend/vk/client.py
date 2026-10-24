import asyncio
import time

import httpx

API_URL = "https://api.vk.com/method/"
API_VERSION = "5.199"
MIN_INTERVAL = 0.34  # VK разрешает не больше ~3 запросов в секунду


class VKAPIError(Exception):

    def __init__(self, code: int, message: str):
        super().__init__(f"VK API error {code}: {message}")
        self.code = code
        self.message = message


class VKClient:
    """Вызов методов VK API с соблюдением лимита частоты запросов."""

    def __init__(self, token: str, timeout: float = 10.0):
        self._http = httpx.AsyncClient(
            base_url=API_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def call(self, method: str, **params) -> dict | list:
        params = {k: v for k, v in params.items() if v is not None}
        params["v"] = API_VERSION

        # Выдерживаем паузу между запросами
        async with self._lock:
            wait = MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

        response = await self._http.post(method, data=params)
        response.raise_for_status()
        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            raise VKAPIError(error.get("error_code", -1), error.get("error_msg", ""))
        return payload["response"]

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "VKClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()