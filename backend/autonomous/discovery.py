# backend/autonomous/discovery.py

import logging
import asyncio
import urllib.request
import urllib.error
import json
from backend import config
from backend.autonomous.universe import universe_manager, UniverseTier

logger = logging.getLogger(__name__)

class DiscoveryEngine:
    """
    Periodically scans the market for top movers (gainers/losers) 
    and promotes the best candidates to the DISCOVERY universe tier.
    """
    def __init__(self, interval_seconds: int = 900): # Default 15 minutes
        self.interval_seconds = interval_seconds
        self._is_running = False
        self._task = None
        self._api_key = config.ALPACA_API_KEY
        self._secret_key = config.ALPACA_SECRET_KEY

    def _fetch_market_movers(self):
        """Synchronous standard library REST call to avoid SDK version issues."""
        url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers?top=10"
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
            "Accept": "application/json"
        })
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return data
        except urllib.error.URLError as e:
            logger.warning(f"[DISCOVERY] REST fetch failed safely: {e}")
            return None

    async def _discovery_loop(self):
        logger.info("[DISCOVERY] Engine started. Waiting for first cycle...")
        while self._is_running:
            try:
                # 1. Fetch data in background thread
                data = await asyncio.to_thread(self._fetch_market_movers)
                
                if data and "gainers" in data:
                    gainers = data["gainers"]
                    promoted_count = 0
                    
                    # 2. Deterministic Filtering (Top 2 valid candidates)
                    for stock in gainers:
                        sym = stock.get("symbol")
                        price = float(stock.get("price", 0))
                        volume = int(stock.get("volume", 0))
                        
                        # MVP/Hackathon Check: Ignore strict volume so it works even after hours
                        if price > 2.0:
                            # Skip if already in a higher tier
                            current_state = universe_manager.get_universe_state()
                            if sym in current_state["PORTFOLIO"] or sym in current_state["USER_INTENT"] or sym in current_state["MARKET_CONTEXT"]:
                                continue
                                
                            universe_manager.add(sym, UniverseTier.DISCOVERY)
                            logger.info(f"[DISCOVERY] Promoted {sym} to DISCOVERY tier (Vol: {volume}, Price: {price})")
                            promoted_count += 1
                            
                            if promoted_count >= 2: # Max 2 candidates per cycle
                                break
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DISCOVERY] Cycle failed safely: {e}")
                
            await asyncio.sleep(self.interval_seconds)

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._task = asyncio.create_task(self._discovery_loop())

    def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()

# Global singleton
discovery_engine = DiscoveryEngine(interval_seconds=60) # Fast 60s interval for testing/hackathon