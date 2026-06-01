import asyncio

import pytest

from void_liquidity.core.bindings import BindingRegistry, BindingSpec
from void_liquidity.core.cache import WorkflowCache
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime


def test_event_bus_routes_specific_and_wildcard_handlers() -> None:
    seen: list[str] = []
    bus = EventBus()

    bus.subscribe("wallets.changed", lambda event: seen.append(event.event_type))
    bus.subscribe(EventBus.WILDCARD, lambda event: seen.append(f"*:{event.source}"))

    asyncio.run(
        bus.publish(
            DomainEvent.create(
                event_type="wallets.changed",
                source="test",
            )
        )
    )

    assert seen == ["*:test", "wallets.changed"]


def test_runtime_connects_registered_bindings_once() -> None:
    handled: list[str] = []

    class FakeBinding:
        spec = BindingSpec(
            name="fake",
            version="1.0.0",
            description="Test binding",
            consumes=("run.requested",),
            produces=("run.completed",),
        )

        async def handle(
            self,
            event: DomainEvent,
            bus: EventBus,
            cache: WorkflowCache | None = None,
        ) -> None:
            handled.append(event.correlation_id)
            await bus.publish(
                DomainEvent.create(
                    event_type="run.completed",
                    source="fake",
                    correlation_id=event.correlation_id,
                )
            )

    completed: list[str] = []
    runtime = Runtime()
    runtime.install(FakeBinding())
    runtime.bus.subscribe("run.completed", lambda event: completed.append(event.source))

    asyncio.run(
        runtime.publish(
            DomainEvent.create(
                event_type="run.requested",
                source="test",
                correlation_id="abc",
            )
        )
    )

    assert handled == ["abc"]
    assert completed == ["fake"]


def test_runtime_passes_cache_to_registered_bindings() -> None:
    seen: list[WorkflowCache | None] = []
    cache = WorkflowCache()

    class FakeBinding:
        spec = BindingSpec(
            name="fake",
            version="1.0.0",
            description="Test binding",
            consumes=("run.requested",),
        )

        async def handle(
            self,
            event: DomainEvent,
            bus: EventBus,
            cache: WorkflowCache | None = None,
        ) -> None:
            seen.append(cache)

    runtime = Runtime(cache=cache)
    runtime.install(FakeBinding())

    asyncio.run(
        runtime.publish(
            DomainEvent.create(
                event_type="run.requested",
                source="test",
            )
        )
    )

    assert seen == [cache]


def test_binding_registry_rejects_duplicate_names() -> None:
    class FakeBinding:
        spec = BindingSpec(name="fake", version="1.0.0", description="Test binding")

        async def handle(self, event: DomainEvent, bus: EventBus) -> None:
            return None

    registry = BindingRegistry()
    registry.register(FakeBinding())

    with pytest.raises(ValueError, match="Binding already registered"):
        registry.register(FakeBinding())
