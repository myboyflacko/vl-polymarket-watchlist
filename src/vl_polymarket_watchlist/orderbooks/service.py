from __future__ import annotations

from datetime import UTC, datetime

from vl_polymarket_watchlist.core.time import ensure_utc
from vl_polymarket_watchlist.orderbooks.domain import OrderBookCollectionResult
from vl_polymarket_watchlist.orderbooks.parser import parse_orderbook_payload
from vl_polymarket_watchlist.orderbooks.repository import (
    complete_orderbook_collection_run,
    create_orderbook_collection_run,
    persist_orderbook_snapshots,
    snapshot_collectable_watchlist,
)
from vl_polymarket_watchlist.polymarket.client import get_polymarket_data_client
from vl_polymarket_watchlist.polymarket.params.orderbook import (
    OrderBookRequest,
    OrderBooksParams,
)


class OrderbookCollectionService:
    def __init__(self, *, batch_size: int = 50) -> None:
        self.batch_size = batch_size

    async def run(self, *, now: datetime | None = None) -> OrderBookCollectionResult:
        generated_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(generated_at)
        create_orderbook_collection_run(
            run_id=run_id,
            started_at=generated_at,
            config_json={"batch_size": self.batch_size},
        )
        items = snapshot_collectable_watchlist(run_id=run_id, selected_at=generated_at)
        client = get_polymarket_data_client()
        snapshots = []
        errors = []

        for batch in _batches(items, self.batch_size):
            try:
                payloads = await client.get_order_books(
                    OrderBooksParams(
                        root=[
                            OrderBookRequest(token_id=item.token_id)
                            for item in batch
                        ]
                    )
                )
            except Exception as exc:
                errors.append(str(exc))
                continue

            payload_by_token = {
                str(payload.get("asset_id") or payload.get("token_id")): payload
                for payload in payloads
                if isinstance(payload, dict)
            }
            for item in batch:
                payload = payload_by_token.get(item.token_id)
                if payload is None:
                    errors.append(f"missing orderbook payload for {item.token_id}")
                    continue

                snapshots.append(
                    parse_orderbook_payload(
                        condition_id=item.condition_id,
                        token_id=item.token_id,
                        payload=payload,
                        generated_at=generated_at,
                    )
                )

        persist_orderbook_snapshots(run_id=run_id, snapshots=snapshots)
        complete_orderbook_collection_run(
            run_id=run_id,
            finished_at=datetime.now(UTC),
            success_count=len(snapshots),
            failure_count=len(errors),
            error_message="; ".join(errors) or None,
        )
        return OrderBookCollectionResult(
            run_id=run_id,
            selected_token_count=len(items),
            success_count=len(snapshots),
            failure_count=len(errors),
            snapshots=snapshots,
            generated_at=generated_at,
        )


def _build_run_id(generated_at: datetime) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-orderbooks"


def _batches[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
