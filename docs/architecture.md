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
  Business capabilities. This is where whale tracking, market discovery,
  strategy inputs, and later risk logic belong.

adapters
  External systems. Polymarket HTTP APIs, exchange APIs, files, and other
  integration details live here.

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
whales.tracking.requested
  -> polymarket.whale_tracking
  -> whales.tracking.started
  -> whales.tracking.completed
```

## Extension Rule

When adding a new capability:

1. Put business models and orchestration in `features/<capability>/`.
2. Put source-specific IO in `adapters/<source>/`.
3. Connect the feature through a plugin if another step should trigger it.
4. Emit a domain event when a durable milestone happens.
5. Keep direct imports between feature steps out of the hot path.

## Market Discovery Boundary

Wallet-to-market derivation should start as `features/markets/`.

It should not place orders, score trades, or decide execution. Its first job is
to produce normalized market candidates from whale snapshots and expose them as
events for downstream research.
