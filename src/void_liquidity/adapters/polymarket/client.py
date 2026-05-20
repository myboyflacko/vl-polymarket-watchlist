import httpx

from typing import Any
from urllib.parse import urljoin


class HTTPClient:
    def __init__(self, timeout: float = 10.0):
        self.client = httpx.AsyncClient(
            timeout=timeout,
        )

    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict | None = None,
    ) -> dict[str, Any] | list[Any]:

        url = urljoin(base_url, endpoint)

        try:
            response = await self.client.get(
                url=url,
                params=params,
            )

            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"HTTP error for {url}: "
                f"{exc.response.status_code} "
                f"{exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Request failed for {url}: {exc}"
            ) from exc


    async def close(self):
        await self.client.aclose()