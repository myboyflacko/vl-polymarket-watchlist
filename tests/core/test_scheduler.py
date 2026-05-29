import asyncio
import contextlib

import pytest

from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.scheduler import ScheduledJob, Scheduler


def test_scheduled_job_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="interval_seconds"):
        ScheduledJob(
            name="invalid",
            interval_seconds=0,
            event_factory=lambda: DomainEvent.create(
                event_type="invalid.requested",
                source="test",
            ),
        )


def test_scheduler_run_once_publishes_fresh_events() -> None:
    seen: list[str] = []
    bus = EventBus()
    bus.subscribe("job.requested", lambda event: seen.append(event.correlation_id))
    scheduler = Scheduler(runtime=Runtime(bus=bus))
    scheduler.register(
        ScheduledJob(
            name="job",
            interval_seconds=60,
            event_factory=lambda: DomainEvent.create(
                event_type="job.requested",
                source="test",
            ),
        )
    )

    asyncio.run(scheduler.run_once())
    asyncio.run(scheduler.run_once())

    assert len(seen) == 2
    assert seen[0] != seen[1]


def test_scheduler_runs_registered_jobs_independently() -> None:
    seen: list[str] = []
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, lambda event: seen.append(event.event_type))
    scheduler = Scheduler(runtime=Runtime(bus=bus))
    scheduler.register(
        ScheduledJob(
            name="slow",
            interval_seconds=0.03,
            event_factory=lambda: DomainEvent.create(
                event_type="slow.requested",
                source="test",
            ),
        )
    )
    scheduler.register(
        ScheduledJob(
            name="fast",
            interval_seconds=0.01,
            event_factory=lambda: DomainEvent.create(
                event_type="fast.requested",
                source="test",
            ),
        )
    )

    async def run_briefly() -> None:
        task = asyncio.create_task(scheduler.schedule())
        await asyncio.sleep(0.04)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_briefly())

    assert "slow.requested" in seen
    assert seen.count("fast.requested") > seen.count("slow.requested")
