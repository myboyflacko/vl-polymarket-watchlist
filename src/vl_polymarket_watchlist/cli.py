from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from vl_polymarket_watchlist.core.logging import configure_logging
from vl_polymarket_watchlist.markets.discovery.registry import build_source

if TYPE_CHECKING:
    from vl_polymarket_watchlist.markets.discovery.service import MarketDiscoveryService
    from vl_polymarket_watchlist.orderbooks.service import OrderbookCollectionService


logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)

    try:
        if args.command == "init-db":
            init_db()
            print("Database initialized.")
            return 0

        if args.command == "run":
            asyncio.run(run_once(args))
            return 0

        if args.command == "schedule":
            try:
                asyncio.run(schedule(args))
            except KeyboardInterrupt:
                print("Scheduler stopped.")
            return 0

        raise ValueError(f"Unknown command: {args.command}")
    except Exception:
        logger.exception(
            "Command failed",
            extra={
                "event": _command_failure_event(args),
                "context": _command_context(args),
            },
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vl-polymarket-watchlist",
        description="Discover Polymarket markets and collect watchlist orderbooks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables.")

    run_parser = subparsers.add_parser("run", help="Run one collector once.")
    run_parser.add_argument(
        "service",
        choices=("discovery", "orderbooks", "all"),
        help="Collector to run.",
    )
    add_discovery_arguments(run_parser)
    add_orderbook_arguments(run_parser)

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Run discovery and orderbook collection continuously.",
    )
    schedule_parser.add_argument(
        "--discovery-interval",
        type=positive_int,
        default=900,
        help="Seconds between discovery runs.",
    )
    schedule_parser.add_argument(
        "--orderbooks-interval",
        type=positive_int,
        default=300,
        help="Seconds between orderbook collection runs.",
    )
    add_discovery_arguments(schedule_parser)
    add_orderbook_arguments(schedule_parser)

    return parser


def add_discovery_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        default="whale_discovery",
        help="Market discovery source to run.",
    )


def add_orderbook_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--orderbook-batch-size",
        type=positive_int,
        default=50,
        help="Number of token orderbooks per CLOB batch request.",
    )


async def run_once(args: argparse.Namespace) -> None:
    if args.service == "discovery":
        await run_discovery(source_name=args.source)
        return

    if args.service == "orderbooks":
        await run_orderbooks(batch_size=args.orderbook_batch_size)
        return

    await run_discovery(source_name=args.source)
    await run_orderbooks(batch_size=args.orderbook_batch_size)


async def schedule(args: argparse.Namespace) -> None:
    discovery_lock = asyncio.Lock()
    orderbooks_lock = asyncio.Lock()
    discovery_runner = scheduled_runner(
        name="discovery",
        interval=args.discovery_interval,
        runner=lambda: run_locked_discovery(
            lock=discovery_lock,
            source_name=args.source,
        ),
    )
    orderbooks_runner = scheduled_runner(
        name="orderbooks",
        interval=args.orderbooks_interval,
        runner=lambda: run_locked_orderbooks(
            lock=orderbooks_lock,
            batch_size=args.orderbook_batch_size,
        ),
    )
    await asyncio.gather(discovery_runner, orderbooks_runner)


async def scheduled_runner(
    *,
    name: str,
    interval: int,
    runner: Callable[[], Awaitable[object]],
) -> None:
    while True:
        try:
            await runner()
        except Exception:
            logger.exception(
                "Service failed",
                extra={
                    "event": "service.failed",
                    "context": {"service": name},
                },
            )

        await asyncio.sleep(interval)


async def run_locked_discovery(*, lock: asyncio.Lock, source_name: str) -> str:
    if lock.locked():
        log_skipped_service(service="discovery", reason="already_running")
        return ""

    async with lock:
        return await run_discovery(source_name=source_name)


async def run_locked_orderbooks(*, lock: asyncio.Lock, batch_size: int) -> str:
    if lock.locked():
        log_skipped_service(service="orderbooks", reason="already_running")
        return ""

    async with lock:
        return await run_orderbooks(batch_size=batch_size)


def log_skipped_service(*, service: str, reason: str) -> None:
    logger.info(
        "Service skipped",
        extra={
            "event": "service.skipped",
            "context": {
                "service": service,
                "reason": reason,
            },
        },
    )


async def run_discovery(*, source_name: str) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "discovery",
                "source": source_name,
            },
        },
    )
    service = build_discovery_service(source_name=source_name)
    result = await service.run()
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "discovery",
                "run_id": result.run_id,
                "source": result.source,
                "checked": result.checked_count,
                "observed": result.observed_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Discovery completed: "
        f"run_id={result.run_id} "
        f"source={result.source} "
        f"checked={result.checked_count} "
        f"observed={result.observed_count} "
        f"errors={error_count}"
    )
    return result.run_id


async def run_orderbooks(*, batch_size: int) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {"service": "orderbooks", "batch_size": batch_size},
        },
    )
    service = build_orderbook_service(batch_size=batch_size)
    result = await service.run()
    if result.status == "skipped":
        logger.info(
            "Service skipped",
            extra={
                "event": "service.skipped",
                "context": {
                    "service": "orderbooks",
                    "reason": result.skip_reason,
                },
            },
        )
        print(f"Orderbooks skipped: reason={result.skip_reason}")
        return ""

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "orderbooks",
                "run_id": result.run_id,
                "selected": result.selected_token_count,
                "success": result.success_count,
                "failure": result.failure_count,
            },
        },
    )
    print(
        "Orderbooks completed: "
        f"run_id={result.run_id} "
        f"selected={result.selected_token_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return result.run_id or ""


def build_discovery_service(*, source_name: str) -> MarketDiscoveryService:
    from vl_polymarket_watchlist.markets.discovery.service import MarketDiscoveryService

    return MarketDiscoveryService(source=build_source(source_name))


def build_orderbook_service(*, batch_size: int) -> OrderbookCollectionService:
    from vl_polymarket_watchlist.orderbooks.service import OrderbookCollectionService

    return OrderbookCollectionService(batch_size=batch_size)


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    migrations_dir = Path(__file__).resolve().parent / "core/db/migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    command.upgrade(config, "head")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Must be greater than 0.")
    return parsed


def _command_failure_event(args: argparse.Namespace) -> str:
    if args.command in {"run", "schedule"}:
        return "service.failed"

    return "cli.failed"


def _command_context(args: argparse.Namespace) -> dict[str, object]:
    return {
        key: value
        for key, value in vars(args).items()
        if isinstance(value, str | int | float | bool | type(None))
    }


if __name__ == "__main__":
    raise SystemExit(main())
