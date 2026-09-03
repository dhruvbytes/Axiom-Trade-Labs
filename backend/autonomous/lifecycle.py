# backend/autonomous/lifecycle.py

import logging
import asyncio
from backend.autonomous.fingerprint import FingerprintManager
from backend.autonomous.universe import MarketUniverseManager
from backend.autonomous.trigger import TriggerEngine
from backend.autonomous.scheduler import AccountAdmissionScheduler
from backend.autonomous.worker import ProposalProcessor
from backend.autonomous.daemon import AutonomousDaemon
from backend.autonomous.universe import UniverseTier, universe_manager
from backend.autonomous.discovery import discovery_engine
from backend.autonomous.ui_events import ui_broadcaster
from backend.autonomous.strategy import DecisionCycleStrategy
from backend.autonomous.decision_controller import AuthoritativeContextBuilder, BoundedDecisionController
from backend.autonomous.reconciliation import ReconciliationService
from backend import alpaca_client

import os
from logging.handlers import RotatingFileHandler

# ==========================================
# 📂 AUDIT LOG FILE SETUP
# ==========================================
def setup_autonomous_file_logger():
    """Sets up a file logger with a strict ~10k lines FIFO size limit."""
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    # Use absolute path to ensure matching across reloads
    log_file_path = os.path.abspath(os.path.join(log_dir, "autonomous_audit.log"))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Prevent duplicate handlers by checking exact file path
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == log_file_path for h in root_logger.handlers):
        file_handler = RotatingFileHandler(
            log_file_path, 
            maxBytes=int(1.5 * 1024 * 1024), # 1.5 MB Cap (~10k lines)
            backupCount=1,      #total file backup count               
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG) 
        
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.info(f"📁 Autonomous Audit Logger initialized. File Path: {log_file_path}")

logger = logging.getLogger(__name__)

# ==========================================
# GLOBAL SINGLETONS (The Autonomous State)
# ==========================================

# 1. State Managers
fingerprint_manager = FingerprintManager()

# 2. Evaluation Engine
trigger_engine = TriggerEngine(fingerprint_manager)

# 3. Execution Pipeline
admission_scheduler = AccountAdmissionScheduler()
proposal_processor = ProposalProcessor()

# 3b. Bounded autonomous decision layer. It owns no execution authority.
context_builder = AuthoritativeContextBuilder(
    portfolio_summary_fetcher=alpaca_client.get_portfolio_summary,
    positions_fetcher=alpaca_client.get_current_positions,
    market_facts_fetcher=alpaca_client.get_market_facts,
)
decision_controller = BoundedDecisionController(context_builder=context_builder)
reconciliation_service = ReconciliationService(
    account_fetcher=alpaca_client.get_portfolio_summary,
    positions_fetcher=alpaca_client.get_current_positions,
)
_autonomy_loop = None

# 4. Central Daemon
autonomous_daemon = AutonomousDaemon(
    scheduler=admission_scheduler,
    processor=proposal_processor
)

# ==========================================
# LATE IMPORTS (To prevent circular dependencies)
# ==========================================
def get_streamer():
    from backend.autonomous.streamer import market_streamer
    return market_streamer


def get_decision_controller() -> BoundedDecisionController:
    return decision_controller


def get_autonomy_loop():
    return _autonomy_loop

# ==========================================
# FASTAPI LIFECYCLE HOOKS
# ==========================================

async def start_autonomous_system():
    """Ignites the Autonomous Trading Engine."""
    global _autonomy_loop
    
    # 🚀 START THE FILE LOGGER FIRST
    setup_autonomous_file_logger()
    
    logger.info("Bootstrapping Autonomous Trading Engine...")
    _autonomy_loop = asyncio.get_running_loop()
    
    # Capture main thread event loop for thread-safe UI broadcasting
    ui_broadcaster.attach_main_loop()
    
    # 1. Start the Background Daemon
    await autonomous_daemon.start()
    autonomous_daemon.ensure_worker_running("default_account") # 🚀 YAHAN WORKER ZINDA HOGA!
    await decision_controller.start()
    reconciliation = await reconciliation_service.restore_uncertainty()
    if reconciliation.status != "CLEAR":
        logger.warning("Autonomous account starts frozen: %s", reconciliation.reason)

    if not any(getattr(strategy, "strategy_id", "") == DecisionCycleStrategy.strategy_id for strategy in trigger_engine.strategies):
        trigger_engine.add_strategy(DecisionCycleStrategy())
    
    # 2. Populate Desired Universe (Phase 1)
    logger.info("Populating initial market universe...")
    universe_manager.add("SPY", UniverseTier.MARKET_CONTEXT)
    universe_manager.add("QQQ", UniverseTier.MARKET_CONTEXT)
    
    from backend.autonomous.portfolio_sync import PortfolioSynchronizer
    await PortfolioSynchronizer.sync_now()
    
    # 3. Start the Real-time Data Streamer & Discovery
    logger.info("Igniting Realtime Market Streamer & Discovery Engine...")
    get_streamer().start_streams()
    discovery_engine.start()
    
    logger.info("Autonomous Trading Engine is LIVE.")

async def stop_autonomous_system():
    """Safely shuts down the Autonomous Engine."""
    logger.info("Initiating shutdown of Autonomous Trading Engine...")
    
    # 1. Stop the Data Streamer FIRST (Stop incoming traffic)
    discovery_engine.stop()
    get_streamer().stop_streams()
    
    # 2. Stop the Background Daemon
    await autonomous_daemon.stop()
    await decision_controller.stop()
    
    logger.info("Autonomous Trading Engine safely halted.")
