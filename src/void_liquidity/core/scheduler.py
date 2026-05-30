import asyncio
from dataclasses import dataclass
from typing import Callable

from void_liquidity.core.events import DomainEvent
from void_liquidity.core.runtime import Runtime


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    interval_seconds: float
    event_factory: Callable[[], DomainEvent]

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")


class Scheduler:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.registry: list[ScheduledJob] = []

    def register(self, *jobs: ScheduledJob) -> None:
        for job in jobs:
            if not isinstance(job, ScheduledJob):
                raise ValueError(f"job must be 'ScheduledJob' object not type {type(job)}")

        for job in jobs:
            self.registry.append(job)

    async def run_once(self) -> None:
        for job in self.registry:
            await self.runtime.publish(job.event_factory())

    async def schedule(self) -> None:
        await asyncio.gather(
            *(self._run_job(job) for job in self.registry),
        )

    async def _run_job(self, job: ScheduledJob) -> None:
        while True:
            await self.runtime.publish(job.event_factory())
            await asyncio.sleep(job.interval_seconds)
