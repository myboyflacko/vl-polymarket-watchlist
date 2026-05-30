from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from void_liquidity.core.events import DomainEvent, EventBus


@dataclass(frozen=True)
class BindingSpec:
    name: str
    version: str
    description: str
    consumes: tuple[str, ...] = field(default_factory=tuple)
    produces: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class Binding(Protocol):
    spec: BindingSpec

    async def handle(self, event: DomainEvent, bus: EventBus) -> None:
        """Handle one event emitted through the runtime bus."""


class BindingRegistry:
    def __init__(self) -> None:
        self._bindings: dict[str, Binding] = {}

    def register(self, binding: Binding) -> None:
        if binding.spec.name in self._bindings:
            raise ValueError(f"Binding already registered: {binding.spec.name}")

        self._bindings[binding.spec.name] = binding

    def get(self, name: str) -> Binding:
        return self._bindings[name]

    def all(self) -> tuple[Binding, ...]:
        return tuple(self._bindings.values())

    def connect(self, bus: EventBus) -> None:
        for binding in self._bindings.values():
            for event_type in binding.spec.consumes:
                bus.subscribe(event_type, self._handler_for(binding, bus))

    @staticmethod
    def _handler_for(binding: Binding, bus: EventBus):
        async def handler(event: DomainEvent) -> None:
            await binding.handle(event=event, bus=bus)

        return handler
