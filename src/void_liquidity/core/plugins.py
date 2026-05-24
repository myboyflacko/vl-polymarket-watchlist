from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from void_liquidity.core.events import DomainEvent, EventBus


@dataclass(frozen=True)
class PluginSpec:
    name: str
    version: str
    description: str
    consumes: tuple[str, ...] = field(default_factory=tuple)
    produces: tuple[str, ...] = field(default_factory=tuple)


class Plugin(Protocol):
    spec: PluginSpec

    async def handle(self, event: DomainEvent, bus: EventBus) -> None:
        """Handle one event emitted through the runtime bus."""


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        if plugin.spec.name in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.spec.name}")

        self._plugins[plugin.spec.name] = plugin

    def get(self, name: str) -> Plugin:
        return self._plugins[name]

    def all(self) -> tuple[Plugin, ...]:
        return tuple(self._plugins.values())

    def connect(self, bus: EventBus) -> None:
        for plugin in self._plugins.values():
            for event_type in plugin.spec.consumes:
                bus.subscribe(event_type, self._handler_for(plugin, bus))

    @staticmethod
    def _handler_for(plugin: Plugin, bus: EventBus):
        async def handler(event: DomainEvent) -> None:
            await plugin.handle(event=event, bus=bus)

        return handler
