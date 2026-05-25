# Architecture

## Direction

`void-liquidity` is moving toward a small event-driven research platform.
The goal is not a heavy framework. The goal is a repo where new capabilities
can be added without rewriting existing pipelines.

## Layers

```text
core
  Framework-neutral runtime contracts.

pipeline
  Provider-neutral pipeline contracts and business language.

adapters
  External systems and provider-specific pipeline implementations. Polymarket
  HTTP APIs and Polymarket whale discovery live here.

bindings
  Runtime connectors. A binding maps a pipeline event to a concrete adapter or
  provider implementation and publishes follow-up events.

workflows
  Runnable process composition roots. A workflow installs bindings into the
  runtime and publishes the first pipeline event.

data
  Persistence infrastructure: SQLAlchemy base, engine creation, migrations.
```

## Event Flow

```text
DomainEvent
  -> EventBus
  -> BindingRegistry
  -> Binding.handle()
  -> DomainEvent
```

Bindings declare what they consume and produce through `BindingSpec`. The runtime
connects registered bindings to the bus. This keeps the next step independent
from the previous step.

Example:

```text
pipeline.discovery.whales.requested
  -> polymarket.discovery.whales
  -> pipeline.discovery.whales.started
  -> pipeline.discovery.whales.completed
  -> polymarket.discovery.whales.discovered
```

## Extension Rule

When adding a new capability:

1. Put pipeline event contracts in `pipeline/<capability>/`.
2. Put source-specific IO and pipeline implementations in `adapters/<source>/`.
3. Connect pipeline events to adapters through `bindings/<source>/`.
4. Emit a domain event when a durable milestone happens.
5. Keep direct imports between pipeline steps out of the hot path.

## Current Boundary

The active stage is whale discovery. The current Polymarket implementation
is `adapters/polymarket/discovery/whales`. It produces qualified whale
signals and emits a Polymarket-specific whale event for later market discovery.
It does not derive markets, place orders, score trades, or decide execution.
