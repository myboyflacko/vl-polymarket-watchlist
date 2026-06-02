from __future__ import annotations

import argparse
import asyncio
import logging
from importlib import import_module

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine
from whale_tracker.core.logging import configure_logging
from whale_tracker.tracker.markets.profiles import MarketTrackingProfile
from whale_tracker.tracker.markets.service import MarketTrackerService
from whale_tracker.tracker.whales.scoring import WhaleScoringProfile
from whale_tracker.tracker.whales.service import WhaleTrackerService


logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)

    if args.command == "init-db":
        init_db()
        print("Database initialized.")
        return 0

    if args.command == "run":
        asyncio.run(run_once(args))
        return 0

    if args.command == "schedule":
        asyncio.run(schedule(args))
        return 0

    raise ValueError(f"Unknown command: {args.command}")


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
        "--interval",
        type=positive_int,
        default=3600,
        help="Seconds to sleep after each full workflow run.",
    )
    add_service_options(schedule_parser)

    return parser


def add_service_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--score",
        action="store_true",
        help="Enable default scoring profiles.",
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
    if args.service == "whales":
        await run_whales(score=args.score)
        return

    if args.service == "markets":
        await run_markets(
            score=args.score,
            limit=args.market_limit,
            whales_run_id=args.whales_run_id,
        )
        return

    whale_run_id = await run_whales(score=args.score)
    await run_markets(
        score=args.score,
        limit=args.market_limit,
        whales_run_id=whale_run_id,
    )


async def schedule(args: argparse.Namespace) -> None:
    while True:
        try:
            await run_once(
                argparse.Namespace(
                    service="all",
                    score=args.score,
                    market_limit=args.market_limit,
                    whales_run_id=args.whales_run_id,
                )
            )
        except Exception:
            logger.exception("Scheduled workflow failed")

        await asyncio.sleep(args.interval)


async def run_whales(*, score: bool) -> str:
    service = build_whale_service(score=score)
    result = await service.run()
    selected_count = result.result_whales.wallet_count

    print(
        "Whales completed: "
        f"run_id={result.run_id} "
        f"checked={result.whales.checked_wallet_count} "
        f"filtered={result.filtered_whales.wallet_count} "
        f"selected={selected_count} "
        f"errors={len(result.collection_errors)}"
    )
    return result.run_id


async def run_markets(
    *,
    score: bool,
    limit: int | None,
    whales_run_id: str | None,
) -> str:
    service = build_market_service(score=score)
    result = await service.run(whales_run_id=whales_run_id, limit=limit)
    selected_count = result.result_markets.market_count

    print(
        "Markets completed: "
        f"run_id={result.run_id} "
        f"whales_run_id={result.whales_run_id or ''} "
        f"checked={result.filtered_markets.checked_market_count} "
        f"filtered={result.filtered_markets.market_count} "
        f"selected={selected_count} "
        f"errors={len(result.errors)}"
    )
    return result.run_id


def build_whale_service(*, score: bool) -> WhaleTrackerService:
    service = WhaleTrackerService()
    if score:
        service.register_scoring(WhaleScoringProfile())

    return service


def build_market_service(*, score: bool) -> MarketTrackerService:
    service = MarketTrackerService()
    if score:
        service.register_scoring(MarketTrackingProfile().scoring)

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


if __name__ == "__main__":
    raise SystemExit(main())
