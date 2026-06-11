from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from whale_tracker.core.logging import configure_logging
from whale_tracker.tracker.whales.service import WhaleTrackerService

if TYPE_CHECKING:
    from whale_tracker.tracker.markets.service import MarketTrackerService
    from whale_tracker.tracker.orderbooks.service import OrderBookTrackerService
    from whale_tracker.tracker.trades.service import TradeTrackerService


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

        if args.command == "api":
            run_api(args)
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
        prog="whale-tracker",
        description="Run whale and market tracking services.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables.")

    run_parser = subparsers.add_parser("run", help="Run one service once.")
    run_parser.add_argument(
        "service",
        choices=("whales", "markets", "trades", "orderbooks", "all"),
        help="Service to run.",
    )
    run_parser.add_argument(
        "--whales-run-id",
        default=None,
        help="Whale run id to use for market tracking.",
    )
    run_parser.add_argument(
        "--market-run-id",
        default=None,
        help="Market run id to use for trade and orderbook tracking.",
    )
    run_parser.add_argument(
        "--orderbook-depth",
        type=positive_int,
        default=5,
        help="Number of bid and ask levels to store.",
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Run whales and markets continuously.",
    )
    schedule_parser.add_argument(
        "--whales-interval",
        type=positive_int,
        default=3600,
        help="Seconds between whale tracking runs.",
    )
    schedule_parser.add_argument(
        "--markets-interval",
        type=positive_int,
        default=900,
        help="Seconds between market tracking runs.",
    )
    schedule_parser.add_argument(
        "--trades-interval",
        type=positive_int,
        default=1200,
        help="Seconds between trade tracking runs.",
    )
    schedule_parser.add_argument(
        "--orderbooks-interval",
        type=positive_int,
        default=300,
        help="Seconds between orderbook tracking runs.",
    )
    schedule_parser.add_argument(
        "--whales-run-id",
        default=None,
        help="Whale run id to use for market tracking.",
    )
    schedule_parser.add_argument(
        "--market-run-id",
        default=None,
        help="Market run id to use for trade and orderbook tracking.",
    )
    schedule_parser.add_argument(
        "--orderbook-depth",
        type=positive_int,
        default=5,
        help="Number of bid and ask levels to store.",
    )

    api_parser = subparsers.add_parser(
        "api",
        help="Start the local HTTP API server.",
    )
    api_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="API server host.",
    )
    api_parser.add_argument(
        "--port",
        type=positive_int,
        default=8000,
        help="API server port.",
    )
    api_parser.add_argument(
        "--no-reload",
        action="store_false",
        dest="reload",
        default=True,
        help="Disable local auto-reload.",
    )

    return parser


async def run_once(args: argparse.Namespace) -> None:
    if args.service == "whales":
        await run_whales()
        return

    if args.service == "markets":
        await run_markets(whales_run_id=args.whales_run_id)
        return

    if args.service == "orderbooks":
        await run_orderbooks(
            market_run_id=args.market_run_id,
            depth=args.orderbook_depth,
        )
        return

    if args.service == "trades":
        await run_trades(market_run_id=args.market_run_id)
        return

    whale_run_id = await run_whales()
    market_run_id = await run_markets(whales_run_id=whale_run_id)
    await run_trades(market_run_id=market_run_id)
    await run_orderbooks(market_run_id=market_run_id, depth=args.orderbook_depth)


async def schedule(args: argparse.Namespace) -> None:
    whales_lock = asyncio.Lock()
    markets_lock = asyncio.Lock()
    trades_lock = asyncio.Lock()
    orderbooks_lock = asyncio.Lock()
    whales_runner = scheduled_runner(
        name="whales",
        interval=args.whales_interval,
        runner=lambda: run_locked_whales(lock=whales_lock),
    )
    markets_runner = scheduled_runner(
        name="markets",
        interval=args.markets_interval,
        runner=lambda: run_markets_after_whales(
            whales_lock=whales_lock,
            markets_lock=markets_lock,
            whales_run_id=args.whales_run_id,
        ),
    )
    trades_runner = scheduled_runner(
        name="trades",
        interval=args.trades_interval,
        runner=lambda: run_trades_after_markets(
            markets_lock=markets_lock,
            trades_lock=trades_lock,
            market_run_id=args.market_run_id,
        ),
    )
    orderbooks_runner = scheduled_runner(
        name="orderbooks",
        interval=args.orderbooks_interval,
        runner=lambda: run_orderbooks_after_markets(
            markets_lock=markets_lock,
            orderbooks_lock=orderbooks_lock,
            market_run_id=args.market_run_id,
            depth=args.orderbook_depth,
        ),
    )
    await asyncio.gather(whales_runner, markets_runner, trades_runner, orderbooks_runner)


def run_api(args: argparse.Namespace) -> None:
    import uvicorn

    print(f"Starting API server at http://{args.host}:{args.port}")
    uvicorn.run(
        "whale_tracker.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


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


async def run_locked_whales(*, lock: asyncio.Lock) -> str:
    async with lock:
        return await run_whales()


async def run_markets_after_whales(
    *,
    whales_lock: asyncio.Lock,
    markets_lock: asyncio.Lock,
    whales_run_id: str | None,
) -> str:
    await wait_for_service_lock(
        lock=whales_lock,
        service="markets",
        waiting_for="whales",
    )
    async with markets_lock:
        return await run_markets(whales_run_id=whales_run_id)


async def run_trades_after_markets(
    *,
    markets_lock: asyncio.Lock,
    trades_lock: asyncio.Lock,
    market_run_id: str | None,
) -> str | None:
    await wait_for_service_lock(
        lock=markets_lock,
        service="trades",
        waiting_for="markets",
    )
    if trades_lock.locked():
        log_skipped_service(service="trades", reason="already_running")
        return None

    async with trades_lock:
        return await run_trades(market_run_id=market_run_id)


async def run_orderbooks_after_markets(
    *,
    markets_lock: asyncio.Lock,
    orderbooks_lock: asyncio.Lock,
    market_run_id: str | None,
    depth: int,
) -> str | None:
    await wait_for_service_lock(
        lock=markets_lock,
        service="orderbooks",
        waiting_for="markets",
    )
    if orderbooks_lock.locked():
        log_skipped_service(service="orderbooks", reason="already_running")
        return None

    async with orderbooks_lock:
        return await run_orderbooks(market_run_id=market_run_id, depth=depth)


async def wait_for_service_lock(
    *,
    lock: asyncio.Lock,
    service: str,
    waiting_for: str,
) -> None:
    if not lock.locked():
        return

    logger.info(
        "Waiting for service",
        extra={
            "event": "service.waiting",
            "context": {
                "service": service,
                "waiting_for": waiting_for,
            },
        },
    )
    async with lock:
        pass


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


async def run_whales() -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {"service": "whales"},
        },
    )
    service = build_whale_service()
    result = await service.run()
    error_count = 0

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "whales",
                "run_id": result.run_id,
                "checked": result.whales.checked_wallet_count,
                "observed": result.whales.wallet_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Whales completed: "
        f"run_id={result.run_id} "
        f"checked={result.whales.checked_wallet_count} "
        f"observed={result.whales.wallet_count} "
        f"errors={error_count}"
    )
    return result.run_id


async def run_markets(*, whales_run_id: str | None) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "markets",
                "whales_run_id": whales_run_id,
            },
        },
    )
    service = build_market_service()
    result = await service.run(whales_run_id=whales_run_id)
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "markets",
                "run_id": result.run_id,
                "whales_run_id": result.whales_run_id,
                "checked": result.collected_markets.checked_market_count,
                "tracked": result.tracked_markets.market_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Markets completed: "
        f"run_id={result.run_id} "
        f"whales_run_id={result.whales_run_id or ''} "
        f"checked={result.collected_markets.checked_market_count} "
        f"tracked={result.tracked_markets.market_count} "
        f"errors={error_count}"
    )
    return result.run_id


async def run_orderbooks(*, market_run_id: str | None, depth: int) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "orderbooks",
                "market_run_id": market_run_id,
                "depth": depth,
            },
        },
    )
    service = build_orderbook_service()
    result = await service.run(market_run_id=market_run_id, depth=depth)
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "orderbooks",
                "run_id": result.run_id,
                "market_run_id": result.market_run_id,
                "checked": result.collected_orderbooks.checked_market_count,
                "stored": result.tracked_orderbooks.orderbook_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Orderbooks completed: "
        f"run_id={result.run_id} "
        f"market_run_id={result.market_run_id} "
        f"checked={result.collected_orderbooks.checked_market_count} "
        f"stored={result.tracked_orderbooks.orderbook_count} "
        f"errors={error_count}"
    )
    return result.run_id


async def run_trades(*, market_run_id: str | None) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "trades",
                "market_run_id": market_run_id,
            },
        },
    )
    service = build_trade_service()
    result = await service.run(market_run_id=market_run_id)
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "trades",
                "run_id": result.run_id,
                "market_run_id": result.market_run_id,
                "checked": result.collected_trades.checked_source_count,
                "stored": result.tracked_trades.trade_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Trades completed: "
        f"run_id={result.run_id} "
        f"market_run_id={result.market_run_id} "
        f"checked={result.collected_trades.checked_source_count} "
        f"stored={result.tracked_trades.trade_count} "
        f"errors={error_count}"
    )
    return result.run_id


def build_whale_service() -> WhaleTrackerService:
    return WhaleTrackerService()


def build_market_service() -> MarketTrackerService:
    from whale_tracker.tracker.markets.service import MarketTrackerService

    return MarketTrackerService()


def build_orderbook_service() -> OrderBookTrackerService:
    from whale_tracker.tracker.orderbooks.service import OrderBookTrackerService

    return OrderBookTrackerService()


def build_trade_service() -> TradeTrackerService:
    from whale_tracker.tracker.trades.service import TradeTrackerService

    return TradeTrackerService()


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

    if args.command == "api":
        return "api.failed"

    return "cli.failed"


def _command_context(args: argparse.Namespace) -> dict[str, object]:
    return {
        key: value
        for key, value in vars(args).items()
        if isinstance(value, str | int | float | bool | type(None))
    }


if __name__ == "__main__":
    raise SystemExit(main())
