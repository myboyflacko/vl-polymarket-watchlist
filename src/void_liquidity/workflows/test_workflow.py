import asyncio

from void_liquidity.bindings.polymarket.discovery.whales import PolymarketWhaleDiscoveryBinding

from void_liquidity.adapters.polymarket.discovery.whales.events import POLYMARKET_WHALES_DISCOVERED

from void_liquidity.core import (
    Runtime, 
    EventBus,
    DomainEvent,
    BindingRegistry
)

from dataclasses import asdict

from void_liquidity.logging.log import VoidLogger

from void_liquidity.pipeline.discovery.whales import WHALE_DISCOVERY_REQUESTED

logger = VoidLogger("track_whales.workflow")


profile_path = "../adapters/polymarket/discovery/whales/profiles/whale_tracking_profile_quality.json"




def log_domain_event(event: DomainEvent):
    logger.log_event(
        event.event_type,
        **asdict(event)
    )

def build_track_whales_event() -> DomainEvent:
    payload = {}

    payload["profile_path"] = str(profile_path)

    return DomainEvent.create(
        event_type=WHALE_DISCOVERY_REQUESTED,
        source="workflow.track_whales",
        payload=payload,
    )


def create_runtime(bus: EventBus) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(PolymarketWhaleDiscoveryBinding())
    return runtime

 
async def main():
    bus = EventBus()
    
    bus.subscribe(EventBus.WILDCARD, log_domain_event)
    
    runtime = create_runtime(bus=bus)
    
    await runtime.publish(build_track_whales_event())
    

    
if __name__ == "__main__":
    asyncio.run(main())