# backend/autonomous/portfolio_sync.py

import asyncio
import logging
import re
from typing import List
from backend import alpaca_client
from backend.autonomous.universe import UniverseTier, universe_manager

logger = logging.getLogger(__name__)

class PortfolioSynchronizer:
    """
    Authoritative synchronization between Alpaca REST portfolio and the UniverseManager.
    Parses complex OCC Option symbols into streamable underlying equity roots.
    """
    
    # Matches OCC Options Format: e.g., AAPL250117C00150000 -> extracts 'AAPL'
    OCC_REGEX = re.compile(r"^([A-Z]+)\d{6}[PC]\d{8}$")

    @classmethod
    async def sync_now(cls):
        """
        Fetches current open positions safely.
        Adds parsed underlying symbols to PORTFOLIO tier.
        Does NOT block or crash if Alpaca REST fails.
        """
        logger.info("[PORTFOLIO_SYNC] Initiating authoritative REST synchronization...")
        try:
            # Reusing existing alpaca_client method via asyncio.to_thread to avoid blocking event loop
            positions = await asyncio.to_thread(alpaca_client.get_current_positions)
            underlying_symbols = set()
            
            for pos in positions:
                raw_symbol = pos.get("symbol", "").upper()
                if not raw_symbol:
                    continue
                    
                # Parse Option OCC symbol to underlying equity
                match = cls.OCC_REGEX.match(raw_symbol)
                if match:
                    underlying = match.group(1)
                    underlying_symbols.add(underlying)
                else:
                    # Regular Equity symbol
                    underlying_symbols.add(raw_symbol)
            
            # Feed to UniverseManager as PORTFOLIO tier (Non-evictable)
            for sym in underlying_symbols:
                universe_manager.add(sym, UniverseTier.PORTFOLIO)
                
            logger.info(f"[PORTFOLIO_SYNC] Synced {len(underlying_symbols)} underlying positions to universe.")
            
        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Synchronization failed safely: {e}")
            # Fails open: Previous universe state remains intact.