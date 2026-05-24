from typing import Any
from urllib.parse import urljoin

import httpx


class HTTPClientError(RuntimeError):
    pass


class HTTPStatusCodeError(HTTPClientError):
    def __init__(
        self,
        url: str,
        status_code: int,
        response_text: str,
    ) -> None:
        super().__init__(f"HTTP error for {url}: {status_code} {response_text}")
        self.url = url
        self.status_code = status_code
        self.response_text = response_text


class HTTPClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self.client = httpx.AsyncClient(timeout=timeout)

    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
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
            raise HTTPStatusCodeError(
                url=url,
                status_code=exc.response.status_code,
                response_text=exc.response.text,
            ) from exc

        except httpx.RequestError as exc:
            raise HTTPClientError(
                f"Request failed for {url}: {exc}"
            ) from exc

    async def close(self) -> None:
        await self.client.aclose()
