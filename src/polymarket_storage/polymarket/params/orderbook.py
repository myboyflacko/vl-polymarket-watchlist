from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel


class OrderBookRequest(BaseModel):
    token_id: str
    side: Literal["BUY", "SELL"] | None = None


class OrderBooksParams(RootModel[list[OrderBookRequest]]):
    root: list[OrderBookRequest] = Field(default_factory=list)

    def output_body(self) -> list[dict[str, str]]:
        return [
            item.model_dump(exclude_none=True)
            for item in self.root
        ]
