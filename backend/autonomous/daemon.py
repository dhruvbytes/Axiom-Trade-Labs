# backend/autonomous/daemon.py

import asyncio
import logging
from typing import Dict
from backend.autonomous.scheduler import AccountAdmissionScheduler
from backend.autonomous.worker import ProposalProcessor

logger = logging.getLogger(__name__)

class AutonomousDaemon:
    """
    The Central Nervous System of the Autonomous Trading Architecture.
    Spawns and manages strictly ordered, isolated background tasks for each account.
    """
    def __init__(self, scheduler: AccountAdmissionScheduler, processor: ProposalProcessor):
        self.scheduler = scheduler
        self.processor = processor
        self.active_workers: Dict[str, asyncio.Task] = {}
        self._is_running = False

    async def start(self):
        """Starts the daemon. Designed to be called during FastAPI startup."""
        self._is_running = True
        logger.info("Autonomous Daemon started. Standing by for proposals.")

    async def stop(self):
        """Gracefully stops the daemon and cancels all running account workers."""
        self._is_running = False
        for acct, task in self.active_workers.items():
            task.cancel()
        self.active_workers.clear()
        logger.info("Autonomous Daemon stopped gracefully.")

    def ensure_worker_running(self, account_id: str):
        """
        Dynamically spawns a dedicated consumer task for an account if one doesn't exist.
        Ensures strict 1-to-1 mapping (1 Account = 1 Task = 1 Queue).
        """
        if account_id not in self.active_workers or self.active_workers[account_id].done():
            logger.info(f"Spawning dedicated priority consumer loop for account: {account_id}")
            self.active_workers[account_id] = asyncio.create_task(self._worker_loop(account_id))

    async def _worker_loop(self, account_id: str):
        """
        The continuous, strictly ordered per-account consumption loop.
        Pulls from the priority queue and pushes through the Risk/CORE-X Critical Section.
        """
        while self._is_running:
            try:
                # 1. Wait for a proposal (Blocks safely until one arrives)
                proposal = await self.scheduler.dequeue_proposal(account_id)
                lock = self.scheduler.get_account_lock(account_id)
                
                logger.info(f"[{account_id}] Dequeued {proposal.priority.name} proposal from {proposal.source}")
                
                # 2. Execute the locked Critical Section (Risk + CORE-X dispatch)
                result = await self.processor.process_critical_section(
                    proposal=proposal, 
                    account_lock=lock
                )
                
                logger.info(f"[{account_id}] Execution Status: {result.get('status')}")
                
            except asyncio.CancelledError:
                logger.info(f"Worker for {account_id} cancelled during shutdown.")
                break
            except Exception as e:
                # 🛡️ FATAL CRASH SHIELD: If one account's worker crashes, don't crash the whole daemon
                logger.error(f"Fatal error in worker loop for {account_id}: {e}")
                await asyncio.sleep(1)  # Prevent infinite tight crash loops that spike CPU