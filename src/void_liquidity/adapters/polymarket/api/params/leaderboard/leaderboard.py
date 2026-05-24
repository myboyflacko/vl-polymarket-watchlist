from typing import Literal

from pydantic import Field, field_validator

from void_liquidity.adapters.polymarket.api.params.base import BaseParams


class LeaderboardParams(BaseParams):
    category: Literal[
        "OVERALL",
        "POLITICS",
        "SPORTS",
        "CRYPTO",
        "CULTURE",
        "MENTIONS",
        "WEATHER",
        "ECONOMICS",
        "TECH",
        "FINANCE",
    ] = Field(default="OVERALL")

    timePeriod: Literal[
        "DAY",
        "WEEK",
        "MONTH",
        "ALL",
    ] = Field(default="DAY")

    orderBy: Literal["PNL", "VOL"] = Field(default="PNL")

    limit: int = Field(default=25, ge=1, le=50)

    offset: int = Field(default=0, ge=0, le=1000)

    user: str | None = Field(
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
        default=None,
    )

    userName: str | None = None

    @field_validator("category", "timePeriod", "orderBy", mode="before")
    @classmethod
    def capitalize(cls, value: str) -> str:
        return value.upper()
