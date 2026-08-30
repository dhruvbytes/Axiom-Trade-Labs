# backend/autonomous/streamer.py

import logging
import asyncio
import threading
from typing import Dict, Any
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed

# Existing imports from your project
from backend import config
from backend.autonomous.watcher import MarketWatcherBoundary
from backend.autonomous.lifecycle import (
    trigger_engine,
    admission_scheduler,
    universe_manager
)
from backend.autonomous.admission import SharedAdmissionBoundary

logger = logging.getLogger(__name__)

class RealtimeMarketStreamer:
    """
    Manages Alpaca WebSocket connections strictly mapped to the IEX feed.
    Routes real-time ticks into the Autonomous Brain's Trigger Engine.
    """
    def __init__(self):
        self.stock_stream = StockDataStream(
            api_key=config.ALPACA_API_KEY, 
            secret_key=config.ALPACA_SECRET_KEY, 
            feed=DataFeed.IEX  
        )
        self._is_running = False
        self._stream_thread = None

    async def _handle_stock_quote(self, raw_msg: Any):
        """Async callback for incoming stock quotes from Alpaca."""
        try:
            raw_dict = {
                "T": "q", 
                "S": getattr(raw_msg, "symbol", ""),
                "bp": getattr(raw_msg, "bid_price", 0.0),
                "ap": getattr(raw_msg, "ask_price", 0.0),
                "feed": "iex" 
            }
            
            event = MarketWatcherBoundary.normalize_stream_event(raw_dict, is_crypto=False)
            if not event:
                return
            
            trigger_result = await trigger_engine.evaluate_event(event)
            if not trigger_result:
                return
                
            logger.info(f"⚡ TRIGGER FIRED: {trigger_result.strategy_id} for {event.symbol} at level {trigger_result.level.name}")
            
            nmli_payload = {
                "tool_name": trigger_result.context.get("target_tool", "place_stock_order"),
                "arguments": trigger_result.context.get("arguments", {"symbol": event.symbol}),
                "metadata": {"source": "AUTONOMOUS_TRIGGER"}
            }
            
            proposal = SharedAdmissionBoundary.submit_autonomous_proposal(
                raw_autonomous_data=nmli_payload,
                is_risk_reduction=(trigger_result.level.value == 1) 
            )
            
            if proposal:
                await admission_scheduler.enqueue_proposal(proposal)
                
        except Exception as e:
            logger.error(f"Error handling stock stream event safely caught: {e}")

    def start_streams(self):
        """Starts the WebSockets in an isolated background thread."""
        if self._is_running:
            return

        self._is_running = True
        
        symbols = universe_manager.get_universe()
        stock_symbols = [s for s in symbols if "/" not in s] 

        if stock_symbols:
            logger.info(f"Subscribing to IEX Stock Stream for: {stock_symbols}")
            self.stock_stream.subscribe_quotes(self._handle_stock_quote, *stock_symbols)
            
            # 🌟 FIX: Isolate the blocking .run() inside a dedicated daemon thread
            self._stream_thread = threading.Thread(target=self.stock_stream.run, daemon=True)
            self._stream_thread.start()

    def stop_streams(self):
        """Gracefully shuts down the WebSockets."""
        self._is_running = False
        try:
            # 🌟 FIX: Only call stop() if the stream was actually started
            if self._stream_thread and self._stream_thread.is_alive():
                self.stock_stream.stop()
                self._stream_thread.join(timeout=2.0)
                logger.info("Realtime Market Streamer stopped.")
        except Exception as e:
            logger.warning(f"Error stopping stream safely caught: {e}")

# Global singleton
market_streamer = RealtimeMarketStreamer()