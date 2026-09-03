# backend/autonomous/streamer.py

import logging
import asyncio
import threading
import time  # 🚀 Added time for strict cooldown
from typing import Dict, Any
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed

# Existing imports from your project
from backend import config
from backend.autonomous.watcher import MarketWatcherBoundary
from backend.autonomous.lifecycle import (
    trigger_engine,
    admission_scheduler,
    universe_manager,
    get_autonomy_loop,
    get_decision_controller,
)
from backend.autonomous.admission import SharedAdmissionBoundary
from backend.autonomous.uncertainty import uncertainty_gate
from backend.autonomous.ui_events import ui_broadcaster, UIActivityEvent, UIEventCategory, UIEventStatus, SafeEventMetadata

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
        
        # Material Event Filter State
        self._last_evaluated_prices: Dict[str, float] = {}
        
        # 🚀 THE NOISE KILLER TRACKER
        self._streamer_cooldowns: Dict[str, float] = {} 
        self.MATERIAL_MOVE_PCT = 0.01  # 🚀 Increased baseline to 1.0%
        
        # Wire dynamic Universe hooks
        universe_manager.on_subscribe_hook = self._dynamic_subscribe
        universe_manager.on_unsubscribe_hook = self._dynamic_unsubscribe

    def _dynamic_subscribe(self, symbol: str):
        if self._is_running and "/" not in symbol:
            logger.info(f"[STREAMER] Dynamically subscribing to: {symbol}")
            self.stock_stream.subscribe_quotes(self._handle_stock_quote, symbol)

    def _dynamic_unsubscribe(self, symbol: str):
        if self._is_running and "/" not in symbol:
            logger.info(f"[STREAMER] Dynamically unsubscribing from: {symbol}")
            self.stock_stream.unsubscribe_quotes(symbol)

    async def _handle_stock_quote(self, raw_msg: Any):
        if not self._is_running:
            return
        
        try:
            raw_dict = {
                "T": "q", 
                "S": getattr(raw_msg, "symbol", ""),
                "bp": getattr(raw_msg, "bid_price", 0.0),
                "ap": getattr(raw_msg, "ask_price", 0.0),
                "feed": "iex" 
            }
            
            event = MarketWatcherBoundary.normalize_stream_event(raw_dict, is_crypto=False)
            if not event or event.price is None or event.price <= 0:
                return

            symbol = event.symbol
            current_price = event.price
            last_price = self._last_evaluated_prices.get(symbol)
            
            if last_price is None:
                self._last_evaluated_prices[symbol] = current_price
                return

            # Backend Math: Calculate move
            signed_change = (current_price - last_price) / last_price
            if abs(signed_change) < self.MATERIAL_MOVE_PCT:
                return

            # Update latest price for next calculation
            self._last_evaluated_prices[symbol] = current_price
            event.raw_data["material_change_pct"] = signed_change

            # ==========================================
            # 🚀 UI SPAM CONTROL (Sirf Logs shant rahenge)
            # ==========================================
            now = time.time()
            if now - self._streamer_cooldowns.get(symbol, 0) >= 10.0:
                self._streamer_cooldowns[symbol] = now 
                logger.info(f"[STREAMER] Material move detected for {symbol}: {current_price}")
                
                ui_broadcaster.publish(UIActivityEvent(
                    category=UIEventCategory.MARKET, status=UIEventStatus.WARNING,
                    message=f"Material price movement detected",
                    safe_metadata=SafeEventMetadata(symbol=symbol, price=current_price)
                ))

            # ==========================================
            # 🚀 BACKEND ALWAYS ACTIVE (Har tick evaluate hoga)
            # ==========================================
            autonomy_loop = get_autonomy_loop()
            current_loop = asyncio.get_running_loop()
            if autonomy_loop is None or autonomy_loop is current_loop:
                await self._process_material_event(event)
            else:
                future = asyncio.run_coroutine_threadsafe(self._process_material_event(event), autonomy_loop)
                future.add_done_callback(self._log_handoff_failure)
                
        except Exception as e:
            logger.error(f"Error handling stock stream event safely caught: {e}")

    @staticmethod
    def _log_handoff_failure(future):
        try:
            future.result()
        except Exception as error:
            logger.error("Autonomous event handoff failed safely: %s", error)

    async def _process_material_event(self, event):
        trigger_result = await trigger_engine.evaluate_event(event)
        if not trigger_result:
            return
        try:
            if uncertainty_gate.is_uncertain("default_account"):
                return # Skip UI broadcast to reduce noise

            result = await get_decision_controller().handle_trigger(event, trigger_result)
            if not result.proposal_payload:
                return

            proposal = SharedAdmissionBoundary.submit_autonomous_proposal(
                raw_autonomous_data=result.proposal_payload,
                is_risk_reduction=result.is_risk_reduction,
            )
            if proposal:
                await admission_scheduler.enqueue_proposal(proposal)
                ui_broadcaster.publish(UIActivityEvent(
                    category=UIEventCategory.SYSTEM,
                    status=UIEventStatus.SUCCESS,
                    message="Bounded autonomous proposal queued for independent risk review.",
                    safe_metadata=SafeEventMetadata(
                        symbol=event.symbol,
                        decision_id=result.receipt.decision_id if result.receipt else None,
                        reason="Admission accepted structurally validated proposal",
                    ),
                ))
        finally:
            cooldown = 45 if trigger_result else 0
            await trigger_engine.fingerprint_manager.release_and_cooldown(trigger_result.fingerprint, cooldown)

    def start_streams(self):
        if self._is_running:
            return

        self._is_running = True
        symbols = universe_manager.get_universe()
        stock_symbols = [s for s in symbols if "/" not in s] 

        if stock_symbols:
            logger.info(f"Subscribing to IEX Stock Stream for: {stock_symbols}")
            self.stock_stream.subscribe_quotes(self._handle_stock_quote, *stock_symbols)
            self._stream_thread = threading.Thread(target=self.stock_stream.run, daemon=True)
            self._stream_thread.start()

    def stop_streams(self):
        self._is_running = False
        try:
            if self._stream_thread and self._stream_thread.is_alive():
                self.stock_stream.stop()
                self._stream_thread.join(timeout=2.0)
                logger.info("Realtime Market Streamer stopped.")
        except Exception as e:
            logger.warning(f"Error stopping stream safely caught: {e}")

# Global singleton
market_streamer = RealtimeMarketStreamer()