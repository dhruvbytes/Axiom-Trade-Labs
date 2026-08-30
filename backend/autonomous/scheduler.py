# backend/autonomous/scheduler.py

import asyncio
import time
from typing import Dict
from backend.autonomous.admission import UnifiedProposal
from backend.autonomous.models import ProposalPriority

class QueuedProposal:
    """
    Wrapper class to allow asyncio.PriorityQueue to sort proposals deterministically.
    Uses priority first, then timestamp as a tie-breaker (FIFO for same priority).
    """
    def __init__(self, proposal: UnifiedProposal):
        self.priority = proposal.priority
        self.timestamp = time.time()
        self.proposal = proposal

    def __lt__(self, other):
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority

class AccountAdmissionScheduler:
    """
    Lightweight, in-memory per-account concurrency manager.
    Eliminates global bottlenecks by scoping queues and locks to individual accounts.
    """
    def __init__(self):
        # Maps account_id -> asyncio.PriorityQueue
        self.queues: Dict[str, asyncio.PriorityQueue] = {}
        # Maps account_id -> asyncio.Lock (The critical section for Risk & CORE-X)
        self.locks: Dict[str, asyncio.Lock] = {}

    def _get_or_create_account_infrastructure(self, account_id: str):
        if account_id not in self.queues:
            self.queues[account_id] = asyncio.PriorityQueue()
            self.locks[account_id] = asyncio.Lock()

    async def enqueue_proposal(self, proposal: UnifiedProposal):
        """Pushes a unified proposal into the account's priority queue."""
        self._get_or_create_account_infrastructure(proposal.account_id)
        qp = QueuedProposal(proposal)
        await self.queues[proposal.account_id].put(qp)

    async def dequeue_proposal(self, account_id: str) -> UnifiedProposal:
        """Pops the highest priority proposal for the specific account."""
        self._get_or_create_account_infrastructure(account_id)
        qp = await self.queues[account_id].get()
        return qp.proposal
        
    def get_account_lock(self, account_id: str) -> asyncio.Lock:
        """Returns the specific asyncio.Lock for the given account's critical section."""
        self._get_or_create_account_infrastructure(account_id)
        return self.locks[account_id]