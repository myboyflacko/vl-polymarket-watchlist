import asyncio

import pytest

from void_liquidity.core import DomainEvent, EventBus, PluginRegistry, PluginSpec, Runtime


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


def test_runtime_connects_registered_plugins_once() -> None:
    handled: list[str] = []

    class FakePlugin:
        spec = PluginSpec(
            name="fake",
            version="1.0.0",
            description="Test plugin",
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
    runtime.install(FakePlugin())
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


def test_plugin_registry_rejects_duplicate_names() -> None:
    class FakePlugin:
        spec = PluginSpec(name="fake", version="1.0.0", description="Test plugin")

        async def handle(self, event: DomainEvent, bus: EventBus) -> None:
            return None

    registry = PluginRegistry()
    registry.register(FakePlugin())

    with pytest.raises(ValueError, match="Plugin already registered"):
        registry.register(FakePlugin())
