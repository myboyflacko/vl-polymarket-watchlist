from typing import Literal

from pydantic import Field, field_validator, model_validator

from void_liquidity.adapters.polymarket.api.params.base import BaseParams


class ActivityParams(BaseParams):
    """Query params for Polymarket Data API `/activity`.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-user-activity
    """

    user: str = Field(
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )
    market: list[str] | None = Field(default=None)
    eventId: list[int] | None = None
    type: list[
        Literal[
            "TRADE",
            "SPLIT",
            "MERGE",
            "REDEEM",
            "REWARD",
            "CONVERSION",
            "MAKER_REBATE",
            "REFERRAL_REWARD",
        ]
    ] | None = Field(default=None)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    side: Literal["BUY", "SELL"] | None = None
    limit: int = Field(default=100, ge=0, le=500)
    offset: int = Field(default=0, ge=0, le=3000)
    sortBy: Literal["TIMESTAMP", "TOKENS", "CASH"] = Field(default="TIMESTAMP")
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

    @field_validator("type", mode="before")
    @classmethod
    def parse_type(cls, value: str | list[str] | None) -> list[str] | None:
        if value is None:
            return value

        if isinstance(value, list):
            return [item.upper() for item in value]

        return [item.strip().upper() for item in value.split(",") if item.strip()]

    @field_validator("side", "sortBy", "sortDirection", mode="before")
    @classmethod
    def capitalize(cls, value: str | None) -> str | None:
        if value is None:
            return value

        return value.upper()

    @model_validator(mode="after")
    def validate_market_or_event_id(self) -> "ActivityParams":
        if self.market is not None and self.eventId is not None:
            raise ValueError("market cannot be used together with eventId")

        return self

    def output_params(self) -> dict:
        params = super().output_params()

        if "market" in params:
            params["market"] = ",".join(params["market"])

        if "eventId" in params:
            params["eventId"] = ",".join(str(event_id) for event_id in params["eventId"])

        if "type" in params:
            params["type"] = ",".join(params["type"])

        return params
