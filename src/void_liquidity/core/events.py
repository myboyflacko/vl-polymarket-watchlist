from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

EventPayload = dict[str, Any]
EventHandler = Callable[["DomainEvent"], Awaitable[None] | None]


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    source: str
    payload: EventPayload = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: EventPayload = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        source: str,
        payload: EventPayload | None = None,
        correlation_id: str | None = None,
        metadata: EventPayload | None = None,
    ) -> "DomainEvent":
        return cls(
            event_type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id or uuid4().hex,
            metadata=metadata or {},
        )


class EventBus:
    WILDCARD = "*"

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = [
            *self._handlers.get(event.event_type, []),
            *self._handlers.get(self.WILDCARD, []),
        ]

        for handler in handlers:
            result = handler(event)

            if inspect.isawaitable(result):
                await result
