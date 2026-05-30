from __future__ import annotations

from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.bindings import Binding, BindingRegistry


class Runtime:
    def __init__(
        self,
        *,
        bus: EventBus | None = None,
        registry: BindingRegistry | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.registry = registry or BindingRegistry()
        self._connected = False

    def install(self, *bindings: Binding) -> None:
        for binding in bindings:
            if not isinstance(binding, Binding):
                raise ValueError(f"Binding must be a Binding instance not type {type(binding)}")

        for binding in bindings:
            self.registry.register(binding)
        self._connected = False

    async def publish(self, event: DomainEvent) -> None:
        self._connect_once()
        await self.bus.publish(event)

    def _connect_once(self) -> None:
        if self._connected:
            return

        self.registry.connect(self.bus)
        self._connected = True
