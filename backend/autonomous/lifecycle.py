# backend/autonomous/lifecycle.py

import logging
from backend.autonomous.fingerprint import FingerprintManager
from backend.autonomous.universe import MarketUniverseManager
from backend.autonomous.trigger import TriggerEngine
from backend.autonomous.scheduler import AccountAdmissionScheduler
from backend.autonomous.worker import ProposalProcessor
from backend.autonomous.daemon import AutonomousDaemon

logger = logging.getLogger(__name__)

# ==========================================
# GLOBAL SINGLETONS (The Autonomous State)
# ==========================================

# 1. State Managers
fingerprint_manager = FingerprintManager()
universe_manager = MarketUniverseManager(max_cap=50) 

# 2. Evaluation Engine
trigger_engine = TriggerEngine(fingerprint_manager)

# 3. Execution Pipeline
admission_scheduler = AccountAdmissionScheduler()
proposal_processor = ProposalProcessor()

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

# ==========================================
# FASTAPI LIFECYCLE HOOKS
# ==========================================

async def start_autonomous_system():
    """Ignites the Autonomous Trading Engine."""
    logger.info("Bootstrapping Autonomous Trading Engine...")
    
    # 1. Start the Background Daemon
    await autonomous_daemon.start()
    
    # 2. Start the Real-time Data Streamer
    logger.info("Igniting Realtime Market Streamer...")
    get_streamer().start_streams()
    
    logger.info("Autonomous Trading Engine is LIVE.")

async def stop_autonomous_system():
    """Safely shuts down the Autonomous Engine."""
    logger.info("Initiating shutdown of Autonomous Trading Engine...")
    
    # 1. Stop the Data Streamer FIRST (Stop incoming traffic)
    get_streamer().stop_streams()
    
    # 2. Stop the Background Daemon
    await autonomous_daemon.stop()
    
    logger.info("Autonomous Trading Engine safely halted.")