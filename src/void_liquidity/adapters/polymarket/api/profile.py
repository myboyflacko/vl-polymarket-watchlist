import asyncio
from typing import Any

from pydantic import Field

from void_liquidity.adapters.polymarket.client import HTTPClient
from void_liquidity.adapters.polymarket.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
)
from void_liquidity.adapters.polymarket.params.base import BaseParams
from void_liquidity.settings import Settings
from void_liquidity.util.log import log_error, log_event

settings = Settings()
profile_request_semaphore = asyncio.Semaphore(
    settings.polymarket.max_concurrent_profile_requests,
)


class PolymarketRateLimitError(RuntimeError):
    pass


class ProfileParams(BaseParams):
    address: str = Field(
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )


async def get_closed_positions(
    client: HTTPClient,
    params: ClosedPositionsParams,
) -> dict[str, Any] | list[Any] | None:

    base_url = settings.polymarket.data_api
    endpoint = "/v1/closed-positions"
    query_params = params.output_params()
    max_attempts = settings.polymarket.rate_limit_retry_attempts + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async with profile_request_semaphore:
                if settings.polymarket.request_delay_seconds:
                    await asyncio.sleep(settings.polymarket.request_delay_seconds)

                log_event(
                    "info",
                    "polymarket.rate_limit.attempt",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                return await client.get(
                    base_url=base_url,
                    endpoint=endpoint,
                    params=query_params,
                )

        except Exception as exc:
            error_text = str(exc).lower()
            is_rate_limited = (
                "429" in error_text
                or "too many requests" in error_text
                or "error 1015" in error_text
                or "you are being rate limited" in error_text
            )

            if is_rate_limited and attempt < max_attempts:
                wait_seconds = settings.polymarket.rate_limit_backoff_seconds * attempt
                log_event(
                    "warning",
                    "polymarket.rate_limit.retry",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    sleep_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue

            log_error(
                event="polymarket.get_closed_positions_failed",
                exc=exc,
                endpoint=endpoint,
                params=params.model_dump(exclude_none=True),
            )

            if is_rate_limited:
                raise PolymarketRateLimitError(
                    f"Rate limited for {endpoint} after {attempt} attempts"
                ) from exc

            return None

    return None


async def get_current_positions(
    client: HTTPClient,
    params: CurrentPositionsParams,
) -> dict[str, Any] | list[Any] | None:
    """Fetch current positions for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user
    """

    base_url = settings.polymarket.data_api
    endpoint = "/v1/positions"
    query_params = params.output_params()
    max_attempts = settings.polymarket.rate_limit_retry_attempts + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async with profile_request_semaphore:
                if settings.polymarket.request_delay_seconds:
                    await asyncio.sleep(settings.polymarket.request_delay_seconds)

                log_event(
                    "info",
                    "polymarket.rate_limit.attempt",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                return await client.get(
                    base_url=base_url,
                    endpoint=endpoint,
                    params=query_params,
                )

        except Exception as exc:
            error_text = str(exc).lower()
            is_rate_limited = (
                "429" in error_text
                or "too many requests" in error_text
                or "error 1015" in error_text
                or "you are being rate limited" in error_text
            )

            if is_rate_limited and attempt < max_attempts:
                wait_seconds = settings.polymarket.rate_limit_backoff_seconds * attempt
                log_event(
                    "warning",
                    "polymarket.rate_limit.retry",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    sleep_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue

            log_error(
                event="polymarket.get_current_positions_failed",
                exc=exc,
                endpoint=endpoint,
                params=params.model_dump(exclude_none=True),
            )

            if is_rate_limited:
                raise PolymarketRateLimitError(
                    f"Rate limited for {endpoint} after {attempt} attempts"
                ) from exc

            return None

    return None


async def get_activity(
    client: HTTPClient,
    params: ActivityParams,
) -> dict[str, Any] | list[Any] | None:
    """Fetch activity rows for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-user-activity
    """

    base_url = settings.polymarket.data_api
    endpoint = "/activity"
    query_params = params.output_params()
    max_attempts = settings.polymarket.rate_limit_retry_attempts + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async with profile_request_semaphore:
                if settings.polymarket.request_delay_seconds:
                    await asyncio.sleep(settings.polymarket.request_delay_seconds)

                log_event(
                    "info",
                    "polymarket.rate_limit.attempt",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                return await client.get(
                    base_url=base_url,
                    endpoint=endpoint,
                    params=query_params,
                )

        except Exception as exc:
            error_text = str(exc).lower()
            is_rate_limited = (
                "429" in error_text
                or "too many requests" in error_text
                or "error 1015" in error_text
                or "you are being rate limited" in error_text
            )

            if is_rate_limited and attempt < max_attempts:
                wait_seconds = settings.polymarket.rate_limit_backoff_seconds * attempt
                log_event(
                    "warning",
                    "polymarket.rate_limit.retry",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    sleep_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue

            log_error(
                event="polymarket.get_activity_failed",
                exc=exc,
                endpoint=endpoint,
                params=params.model_dump(exclude_none=True),
            )

            if is_rate_limited:
                raise PolymarketRateLimitError(
                    f"Rate limited for {endpoint} after {attempt} attempts"
                ) from exc

            return None

    return None


get_profile = get_closed_positions
