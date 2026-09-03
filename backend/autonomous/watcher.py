# backend/autonomous/watcher.py

import logging
from typing import Dict, Any, Optional
from backend.autonomous.models import AutonomousEvent, MarketEventSource
from pydantic import ValidationError

logger = logging.getLogger(__name__)

class MarketWatcherBoundary:
    """
    Boundary layer for all incoming market data.
    Ensures strict compliance with Alpaca Basic/Paper tier (IEX/Crypto only).
    Normalizes raw data into AutonomousEvent. Fails safely on malformed data.
    """
    
    @staticmethod
    def normalize_stream_event(raw_data: Dict[str, Any], is_crypto: bool = False) -> Optional[AutonomousEvent]:
        """Normalizes incoming WebSocket streaming data."""
        try:
            # 🛡️ SECURITY & TIER CHECK: Block SIP/OPRA strictly
            feed = raw_data.get("feed", "").lower()
            if feed in ["sip", "opra"]:
                logger.warning(f"Blocked unsupported premium feed '{feed}'. Enforcing Basic Tier.")
                return None

            # Alpaca typically sends symbol in 'S' or 'symbol'
            symbol = raw_data.get("S") or raw_data.get("symbol")
            if not symbol:
                return None

            # Determine event type based on Alpaca WS prefixes (T=Trade, q=Quote, b=Bar)
            msg_type = raw_data.get("T", "unknown")
            event_type_map = {"t": "trade", "q": "quote", "b": "bar"}
            event_type = event_type_map.get(msg_type.lower(), "custom_stream")

            # Extract price safely (p for trade, c for bar, mid of bp/ap for quote)
            price_raw = raw_data.get("p") or raw_data.get("c")
            if price_raw is None:
                bp = float(raw_data.get("bp") or 0.0)
                ap = float(raw_data.get("ap") or 0.0)
                if bp > 0 and ap > 0:
                    price_raw = (bp + ap) / 2.0
                elif bp > 0:
                    price_raw = bp
                elif ap > 0:
                    price_raw = ap
            price = float(price_raw) if price_raw is not None else None

            source = MarketEventSource.WEBSOCKET_CRYPTO if is_crypto else MarketEventSource.WEBSOCKET_IEX

            return AutonomousEvent(
                symbol=symbol,
                event_type=event_type,
                price=price,
                source=source,
                raw_data=raw_data
            )
        except ValidationError as ve:
            logger.error(f"Malformed stream event rejected by Pydantic: {ve}")
            return None
        except Exception as e:
            # 🛡️ FATAL EXCEPTION SHIELD: Never crash the autonomous controller
            logger.error(f"Watcher boundary safely caught exception: {e}")
            return None

    @staticmethod
    def normalize_rest_event(symbol: str, raw_data: Dict[str, Any], event_type: str = "rest_snapshot") -> Optional[AutonomousEvent]:
        """Normalizes data fetched via on-demand or periodic REST polling."""
        try:
            price_raw = raw_data.get("price") or raw_data.get("close")
            price = float(price_raw) if price_raw is not None else None

            return AutonomousEvent(
                symbol=symbol,
                event_type=event_type,
                price=price,
                source=MarketEventSource.REST_POLLING_IEX,
                raw_data=raw_data
            )
        except ValidationError as ve:
            logger.error(f"Malformed REST event rejected by Pydantic: {ve}")
            return None
        except Exception as e:
            logger.error(f"Watcher boundary safely caught REST exception: {e}")
            return None