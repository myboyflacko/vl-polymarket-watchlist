#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

from dotenv import load_dotenv
from nautilus_trader.adapters.polymarket import POLYMARKET
from nautilus_trader.adapters.polymarket import PolymarketDataClientConfig
from nautilus_trader.adapters.polymarket import PolymarketLiveDataClientFactory
from nautilus_trader.adapters.polymarket import get_polymarket_instrument_id
from nautilus_trader.adapters.polymarket.providers import PolymarketInstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.test_kit.strategies.tester_data import DataTester
from nautilus_trader.test_kit.strategies.tester_data import DataTesterConfig


def run_data_tester() -> None:
    load_dotenv()

    condition_id = "0xcccb7e7613a087c132b69cbf3a02bece3fdcb824c1da54ae79acc8d4a562d902"
    token_id = "8441400852834915183759801017793514978104486628517653995211751018945988243154"

    instrument_ids = [
        get_polymarket_instrument_id(condition_id, token_id),
    ]

    load_ids = [str(x) for x in instrument_ids]
    instrument_provider_config = PolymarketInstrumentProviderConfig(load_ids=frozenset(load_ids))

    config_node = TradingNodeConfig(
        trader_id=TraderId("TESTER-001"),
        logging=LoggingConfig(log_level="INFO", use_pyo3=True),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
        ),
        data_clients={
            POLYMARKET: PolymarketDataClientConfig(
                signature_type=2,
                instrument_config=instrument_provider_config,
                compute_effective_deltas=True,
            ),
        },
        timeout_connection=20.0,
        timeout_disconnection=10.0,
        timeout_post_stop=1.0,
    )

    node = TradingNode(config=config_node)

    config_tester = DataTesterConfig(
        instrument_ids=instrument_ids,
        subscribe_book_at_interval=True,
        book_interval_ms=10,
        can_unsubscribe=False,
    )
    tester = DataTester(config=config_tester)

    node.trader.add_actor(tester)
    node.add_data_client_factory(POLYMARKET, PolymarketLiveDataClientFactory)
    node.build()

    try:
        node.run()
    finally:
        node.dispose()


if __name__ == "__main__":
    run_data_tester()
