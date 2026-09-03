# backend/autonomous/llm_governance.py

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class LLMGovernance:
    """
    Strict boundary for LLM interaction.
    Enforces maximum concurrency, timeouts, global rate limits, and JSON validation.
    Any failure immediately defaults to NO_ACTION (None) without crashing.
    """
    def __init__(self, max_concurrent: int = 2, max_calls_per_minute: int = 10, timeout_seconds: float = 10.0):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_cpm = max_calls_per_minute
        self.timeout_seconds = timeout_seconds
        
        # State for rate limiting
        self.call_timestamps = []
        self._rate_limit_lock = asyncio.Lock()

    async def _check_global_rate_limit(self) -> bool:
        """Returns True if within budget, False if rate limited."""
        async with self._rate_limit_lock:
            now = datetime.now(timezone.utc).timestamp()
            # Keep only timestamps from the last 60 seconds
            self.call_timestamps = [ts for ts in self.call_timestamps if now - ts < 60]
            
            if len(self.call_timestamps) >= self.max_cpm:
                return False
                
            self.call_timestamps.append(now)
            return True

    async def invoke_llm_safely(self, llm_callable: Callable, brief: Any) -> Optional[Dict[str, Any]]:
        # 2. Concurrency Limit (Max 2 concurrent calls)
        async with self.semaphore:
            try:
                # 3. Timeout Enforcement
                raw_output = await asyncio.wait_for(llm_callable(brief), timeout=self.timeout_seconds)
                
                # 4. Handle explicit NO_ACTION string
                if not raw_output or "NO_ACTION" in raw_output:
                    return None
                
                # 5. Strict JSON parsing (Must be valid NMLI)
                parsed_nmli = json.loads(raw_output)
                
                # 6. Basic Structural check (must contain 'tool_name' and 'arguments')
                if not isinstance(parsed_nmli, dict) or "tool_name" not in parsed_nmli or "arguments" not in parsed_nmli:
                    logger.error("LLM Output malformed (missing tool_name/arguments). Defaulting to NO_ACTION.")
                    return None
                    
                return parsed_nmli

            except asyncio.TimeoutError:
                logger.error(f"LLM call timed out after {self.timeout_seconds}s. Defaulting to NO_ACTION.")
                return None
            except json.JSONDecodeError:
                logger.error("LLM output is not valid JSON. Defaulting to NO_ACTION.")
                return None
            except Exception as e:
                logger.error(f"LLM call failed safely: {e}. Defaulting to NO_ACTION.")
                return None

    async def invoke_json_evidence_safely(
        self,
        llm_callable: Callable,
        compact_evidence: Any,
        required_keys: tuple[str, ...] = ("summary",),
    ) -> Optional[Dict[str, Any]]:
        """Safely obtain non-authoritative evidence JSON, never an NMLI proposal.

        This method shares the same rate/concurrency/timeout governance as the
        proposal path but intentionally rejects any response carrying execution
        fields.  It is appropriate only for qualified evidence synthesis.
        """
        if not await self._check_global_rate_limit():
            logger.warning("LLM evidence rate limit exceeded. Defaulting to incomplete evidence.")
            return None
        async with self.semaphore:
            try:
                raw_output = await asyncio.wait_for(llm_callable(compact_evidence), timeout=self.timeout_seconds)
                parsed = json.loads(raw_output)
                if not isinstance(parsed, dict) or "tool_name" in parsed or "arguments" in parsed:
                    logger.error("LLM evidence output attempted an execution-shaped payload.")
                    return None
                if any(key not in parsed for key in required_keys):
                    logger.error("LLM evidence output missing required bounded fields.")
                    return None
                return parsed
            except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as error:
                logger.error(f"LLM evidence synthesis failed safely: {error}")
                return None
