from functools import lru_cache

from py_clob_client_v2 import ClobClient

from void_liquidity.settings import get_settings


@lru_cache(maxsize=1)
def get_clob_client() -> ClobClient:
    settings = get_settings()

    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,  # Polygon mainnet
        key=settings.polymarket.polymarket_pk,
    )

    # Creates new credentials or derives existing ones
    client.create_or_derive_api_key()

    return client
