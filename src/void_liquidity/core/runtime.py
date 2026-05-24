from __future__ import annotations

from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.plugins import Plugin, PluginRegistry


class Runtime:
    def __init__(
        self,
        *,
        bus: EventBus | None = None,
        registry: PluginRegistry | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.registry = registry or PluginRegistry()
        self._connected = False

    def install(self, plugin: Plugin) -> None:
        self.registry.register(plugin)
        self._connected = False

    async def publish(self, event: DomainEvent) -> None:
        self._connect_once()
        await self.bus.publish(event)

    def _connect_once(self) -> None:
        if self._connected:
            return

        self.registry.connect(self.bus)
        self._connected = True
