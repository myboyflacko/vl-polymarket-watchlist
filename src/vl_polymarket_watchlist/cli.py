from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from vl_polymarket_watchlist.core.logging import configure_logging
from vl_polymarket_watchlist.market_acquisition.strategies import build_strategy

if TYPE_CHECKING:
    from vl_polymarket_watchlist.market_acquisition.service import MarketCollectorService


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
        description="Collect and store Polymarket markets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables.")

    run_parser = subparsers.add_parser("run", help="Run one collector once.")
    run_parser.add_argument(
        "service",
        choices=("markets", "all"),
        help="Collector to run.",
    )
    add_market_arguments(run_parser)

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Run market collection continuously.",
    )
    schedule_parser.add_argument(
        "--markets-interval",
        type=positive_int,
        default=900,
        help="Seconds between market collection runs.",
    )
    add_market_arguments(schedule_parser)

    return parser


def add_market_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strategy",
        default="leaderboard_current_positions",
        help="Market collector strategy to run.",
    )


async def run_once(args: argparse.Namespace) -> None:
    await run_markets(strategy_name=args.strategy)


async def schedule(args: argparse.Namespace) -> None:
    markets_lock = asyncio.Lock()
    markets_runner = scheduled_runner(
        name="markets",
        interval=args.markets_interval,
        runner=lambda: run_locked_markets(
            lock=markets_lock,
            strategy_name=args.strategy,
        ),
    )
    await markets_runner


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


async def run_locked_markets(*, lock: asyncio.Lock, strategy_name: str) -> str:
    if lock.locked():
        log_skipped_service(service="markets", reason="already_running")
        return ""

    async with lock:
        return await run_markets(strategy_name=strategy_name)


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


async def run_markets(*, strategy_name: str) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "markets",
                "strategy": strategy_name,
            },
        },
    )
    service = build_market_service(strategy_name=strategy_name)
    result = await service.run()
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "markets",
                "run_id": result.run_id,
                "strategy": result.strategy_name,
                "checked": result.checked_market_count,
                "stored": result.stored_market_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Markets completed: "
        f"run_id={result.run_id} "
        f"strategy={result.strategy_name} "
        f"checked={result.checked_market_count} "
        f"stored={result.stored_market_count} "
        f"errors={error_count}"
    )
    return result.run_id


def build_market_service(*, strategy_name: str) -> MarketCollectorService:
    from vl_polymarket_watchlist.market_acquisition.service import MarketCollectorService

    return MarketCollectorService(strategy=build_strategy(strategy_name))


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
