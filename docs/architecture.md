# Architecture

## Direction

`void-liquidity` is moving toward a small event-driven research platform.
The goal is not a heavy framework. The goal is a repo where new capabilities
can be added without rewriting existing pipelines.

## Layers

```text
core
  Framework-neutral runtime contracts.

features
  Feature contracts and business language. In the current stage this is the
  qualified-whales contract.

adapters
  External systems and concrete collectors. Polymarket HTTP APIs and the
  Polymarket whale collector live here.

plugins
  Runtime connectors. A plugin maps a feature event to a concrete adapter or
  collector and publishes follow-up events.

data
  Persistence infrastructure: SQLAlchemy base, engine creation, migrations.
```

## Event Flow

```text
DomainEvent
  -> EventBus
  -> PluginRegistry
  -> Plugin.handle()
  -> DomainEvent
```

Plugins declare what they consume and produce through `PluginSpec`. The runtime
connects registered plugins to the bus. This keeps the next step independent
from the previous step.

Example:

```text
whales.collection.requested
  -> polymarket.whale_collector
  -> whales.collection.started
  -> whales.collection.completed
```

## Extension Rule

When adding a new capability:

1. Put feature event contracts in `features/<capability>/`.
2. Put source-specific IO and collectors in `adapters/<source>/`.
3. Connect feature events to adapters through `plugins/<source>/`.
4. Emit a domain event when a durable milestone happens.
5. Keep direct imports between feature steps out of the hot path.

## Current Boundary

The active stage is whale collection. It produces qualified whale snapshots and
does not derive markets, place orders, score trades, or decide execution.
