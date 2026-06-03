from __future__ import annotations

import argparse
import asyncio
import logging
from importlib import import_module

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine
from whale_tracker.core.logging import configure_logging
from whale_tracker.tracker.markets.service import MarketTrackerService
from whale_tracker.tracker.whales.service import WhaleTrackerService


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
        prog="whale-tracker",
        description="Run whale and market tracking services.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables.")

    run_parser = subparsers.add_parser("run", help="Run one service once.")
    run_parser.add_argument(
        "service",
        choices=("whales", "markets", "all"),
        help="Service to run.",
    )
    add_service_options(run_parser)

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
    add_service_options(schedule_parser)

    return parser


def add_service_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-scoring",
        action="store_true",
        help="Disable default scoring profiles.",
    )
    parser.add_argument(
        "--market-limit",
        type=positive_int,
        default=None,
        help="Max scored markets to persist when market scoring is enabled.",
    )
    parser.add_argument(
        "--whales-run-id",
        default=None,
        help="Whale run id to use for market tracking.",
    )


async def run_once(args: argparse.Namespace) -> None:
    scoring_enabled = not args.no_scoring

    if args.service == "whales":
        await run_whales(scoring_enabled=scoring_enabled)
        return

    if args.service == "markets":
        await run_markets(
            scoring_enabled=scoring_enabled,
            limit=args.market_limit,
            whales_run_id=args.whales_run_id,
        )
        return

    whale_run_id = await run_whales(scoring_enabled=scoring_enabled)
    await run_markets(
        scoring_enabled=scoring_enabled,
        limit=args.market_limit,
        whales_run_id=whale_run_id,
    )


async def schedule(args: argparse.Namespace) -> None:
    scoring_enabled = not args.no_scoring
    whales_runner = scheduled_runner(
        name="whales",
        interval=args.whales_interval,
        runner=lambda: run_whales(scoring_enabled=scoring_enabled),
    )
    markets_runner = scheduled_runner(
        name="markets",
        interval=args.markets_interval,
        runner=lambda: run_markets(
            scoring_enabled=scoring_enabled,
            limit=args.market_limit,
            whales_run_id=args.whales_run_id,
        ),
    )
    await asyncio.gather(whales_runner, markets_runner)


async def scheduled_runner(
    *,
    name: str,
    interval: int,
    runner,
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


async def run_whales(*, scoring_enabled: bool) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "whales",
                "scoring_enabled": scoring_enabled,
            },
        },
    )
    service = build_whale_service(scoring_enabled=scoring_enabled)
    result = await service.run()
    selected_count = result.result_whales.wallet_count
    error_count = len(result.collection_errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "whales",
                "run_id": result.run_id,
                "checked": result.whales.checked_wallet_count,
                "filtered": result.filtered_whales.wallet_count,
                "selected": selected_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Whales completed: "
        f"run_id={result.run_id} "
        f"checked={result.whales.checked_wallet_count} "
        f"filtered={result.filtered_whales.wallet_count} "
        f"selected={selected_count} "
        f"errors={error_count}"
    )
    return result.run_id


async def run_markets(
    *,
    scoring_enabled: bool,
    limit: int | None,
    whales_run_id: str | None,
) -> str:
    logger.info(
        "Service started",
        extra={
            "event": "service.started",
            "context": {
                "service": "markets",
                "scoring_enabled": scoring_enabled,
                "limit": limit,
                "whales_run_id": whales_run_id,
            },
        },
    )
    service = build_market_service(scoring_enabled=scoring_enabled)
    result = await service.run(whales_run_id=whales_run_id, limit=limit)
    selected_count = result.result_markets.market_count
    error_count = len(result.errors)

    logger.info(
        "Service completed",
        extra={
            "event": "service.completed",
            "context": {
                "service": "markets",
                "run_id": result.run_id,
                "whales_run_id": result.whales_run_id,
                "checked": result.filtered_markets.checked_market_count,
                "filtered": result.filtered_markets.market_count,
                "selected": selected_count,
                "errors": error_count,
            },
        },
    )

    print(
        "Markets completed: "
        f"run_id={result.run_id} "
        f"whales_run_id={result.whales_run_id or ''} "
        f"checked={result.filtered_markets.checked_market_count} "
        f"filtered={result.filtered_markets.market_count} "
        f"selected={selected_count} "
        f"errors={error_count}"
    )
    return result.run_id


def build_whale_service(*, scoring_enabled: bool) -> WhaleTrackerService:
    service = WhaleTrackerService()
    if not scoring_enabled:
        service.register_scoring(None)

    return service


def build_market_service(*, scoring_enabled: bool) -> MarketTrackerService:
    service = MarketTrackerService()
    if not scoring_enabled:
        service.register_scoring(None)

    return service


def init_db() -> None:
    import_module("whale_tracker.tracker.whales.models")
    import_module("whale_tracker.tracker.markets.models")

    engine = create_database_engine()
    Base.metadata.create_all(engine)


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
