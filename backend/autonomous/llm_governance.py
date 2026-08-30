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
        """
        Executes the LLM function safely. 
        llm_callable must be an async function that takes a MarketBrief and returns a string.
        """
        # 1. Global Rate Budget Check
        if not await self._check_global_rate_limit():
            logger.warning("LLM Global Rate Limit exceeded. Defaulting to NO_ACTION.")
            return None

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