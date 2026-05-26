from typing import Literal

from pydantic import Field, field_validator, model_validator

from void_liquidity.adapters.polymarket.api.params.base import BaseParams


class TradesParams(BaseParams):
    """Query params for Polymarket Data API `/trades`.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
    """

    limit: int = Field(default=100, ge=0, le=10_000)
    offset: int = Field(default=0, ge=0, le=10_000)
    takerOnly: bool = True
    filterType: Literal["CASH", "TOKENS"] | None = None
    filterAmount: float | None = Field(default=None, ge=0)
    market: list[str] | None = Field(default=None)
    eventId: list[int] | None = None
    user: str | None = Field(
        default=None,
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )
    side: Literal["BUY", "SELL"] | None = None

    @field_validator("market", mode="before")
    @classmethod
    def parse_market(cls, value: str | list[str] | None) -> list[str] | None:
        if value is None or isinstance(value, list):
            return value

        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value

        for market in value:
            if len(market) != 66 or not market.startswith("0x"):
                raise ValueError("market must contain 0x-prefixed 64-hex condition IDs")

            int(market[2:], 16)

        return value

    @field_validator("eventId", mode="before")
    @classmethod
    def parse_event_id(cls, value: str | list[int] | None) -> list[int] | None:
        if value is None or isinstance(value, list):
            return value

        return [int(item.strip()) for item in value.split(",") if item.strip()]

    @field_validator("eventId")
    @classmethod
    def validate_event_id(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value

        for event_id in value:
            if event_id < 1:
                raise ValueError("eventId values must be greater than or equal to 1")

        return value

    @field_validator("filterType", "side", mode="before")
    @classmethod
    def capitalize(cls, value: str | None) -> str | None:
        if value is None:
            return value

        return value.upper()

    @model_validator(mode="after")
    def validate_combined_params(self) -> "TradesParams":
        if self.market is not None and self.eventId is not None:
            raise ValueError("market cannot be used together with eventId")

        if (self.filterType is None) != (self.filterAmount is None):
            raise ValueError("filterType and filterAmount must be provided together")

        return self

    def output_params(self) -> dict:
        params = super().output_params()

        if "market" in params:
            params["market"] = ",".join(params["market"])

        if "eventId" in params:
            params["eventId"] = ",".join(str(event_id) for event_id in params["eventId"])

        return params
