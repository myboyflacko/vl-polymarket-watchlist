import asyncio

import pytest

from void_liquidity.core import (
    BindingRegistry,
    BindingSpec,
    DomainEvent,
    EventBus,
    Runtime,
)


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

    assert seen == ["wallets.changed", "*:test"]


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

        async def handle(self, event: DomainEvent, bus: EventBus) -> None:
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


def test_binding_registry_rejects_duplicate_names() -> None:
    class FakeBinding:
        spec = BindingSpec(name="fake", version="1.0.0", description="Test binding")

        async def handle(self, event: DomainEvent, bus: EventBus) -> None:
            return None

    registry = BindingRegistry()
    registry.register(FakeBinding())

    with pytest.raises(ValueError, match="Binding already registered"):
        registry.register(FakeBinding())
