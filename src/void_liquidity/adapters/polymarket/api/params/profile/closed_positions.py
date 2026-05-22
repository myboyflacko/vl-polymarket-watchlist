from typing import Literal

from pydantic import Field, field_validator, model_validator

from void_liquidity.adapters.polymarket.api.params.base import BaseParams


class ClosedPositionsParams(BaseParams):
    user: str = Field(
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )
    market: list[str] | None = Field(default=None)
    title: str | None = Field(default=None, max_length=100)
    eventId: list[int] | None = None
    limit: int = Field(default=10, ge=0, le=50)
    offset: int = Field(default=0, ge=0, le=100000)
    sortBy: Literal[
        "REALIZEDPNL",
        "TITLE",
        "PRICE",
        "AVGPRICE",
        "TIMESTAMP",
    ] = Field(default="REALIZEDPNL")
    sortDirection: Literal["ASC", "DESC"] = Field(default="DESC")

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

    @field_validator("sortBy", "sortDirection", mode="before")
    @classmethod
    def capitalize(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_market_or_event_id(self) -> "ClosedPositionsParams":
        if self.market is not None and self.eventId is not None:
            raise ValueError("market cannot be used together with eventId")

        return self

    def output_params(self) -> dict:
        params = super().output_params()

        if "market" in params:
            params["market"] = ",".join(params["market"])

        if "eventId" in params:
            params["eventId"] = ",".join(str(event_id) for event_id in params["eventId"])

        return params
