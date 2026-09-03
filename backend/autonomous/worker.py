import logging
import asyncio
import time
import re
from typing import Dict, Any, Optional
from backend.autonomous.admission import UnifiedProposal
from backend.autonomous.uncertainty import uncertainty_gate
from backend.autonomous.ui_events import ui_broadcaster, UIActivityEvent, UIEventCategory, UIEventStatus, SafeEventMetadata

# 🚀 REAL IMPORTS (No more mocks!)
from backend import alpaca_client
from backend.risk_engine.adapter import risk_adapter
from backend.execution.executor import corex_executor
from backend.execution.models import ExecutableTask, ExecutionState
from backend.tool_router.schemas import ToolRequest
from backend.autonomous.decision_ledger import decision_ledger

logger = logging.getLogger(__name__)

class RiskDecision:
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"

class ProposalProcessor:
    """
    The single-threaded worker per account that safely bridges the Priority Scheduler 
    with the authoritative Risk Engine and CORE-X execution layer.
    """
    def __init__(self):
        pass

    async def fetch_authoritative_facts(self, account_id: str, symbols: Optional[list[str]] = None) -> Optional[Dict[str, Any]]:
        """Fetches REAL account balance and positions from Alpaca."""
        logger.debug(f"Fetching authoritative Alpaca facts for {account_id}...")
        try:
            summary, positions, market_facts = await asyncio.gather(
                asyncio.to_thread(alpaca_client.get_portfolio_summary),
                asyncio.to_thread(alpaca_client.get_current_positions),
                alpaca_client.get_market_facts(symbols or []),
            )
            facts = {
                "buying_power": float(summary["buying_power"]),
                "equity": float(summary["portfolio_value"]),
                "positions": positions,
                "daily_loss_pct": 0.0,
            }
            facts.update(market_facts)
            return facts
        except Exception as e:
            logger.error(f"Failed to fetch live facts: {e}")
            return None

    async def evaluate_risk(self, proposal: UnifiedProposal, facts: Dict[str, Any]) -> str:
        """Passes the proposal to the REAL Risk Engine."""
        tool_req = ToolRequest(
            tool_name=proposal.data.get("tool_name", ""),
            arguments=proposal.data.get("arguments", {}),
            reason="Bounded autonomous decision submitted for independent risk evaluation.",
        )
        
        # Call the real Risk Adapter
        risk_result = risk_adapter.evaluate(tool_req, facts)
        
        if risk_result.is_approved:
            # Store the token safely for CORE-X execution
            proposal.data["risk_token"] = risk_result.risk_token
            proposal.data["is_mutating"] = risk_result.is_mutating
            return RiskDecision.ALLOW
        else:
            logger.warning(f"Risk Engine rejected proposal: {risk_result.rejection_reason}")
            # Attach reason for the UI broadcast
            proposal.data["rejection_reason"] = risk_result.rejection_reason
            return RiskDecision.BLOCK

    async def dispatch_to_corex(self, proposal: UnifiedProposal) -> Any:
        """Bridges the validated proposal to the existing REAL CORE-X executor."""
        tool_req = ToolRequest(
            tool_name=proposal.data.get("tool_name", ""),
            arguments=proposal.data.get("arguments", {}),
            reason="Risk-authorized bounded autonomous decision dispatched to CORE-X.",
        )
        
        task = ExecutableTask(
            intent_nonce=f"auto_{proposal.priority.name}_{int(time.time())}",
            tool_request=tool_req,
            risk_token=proposal.data.get("risk_token"),
            is_mutating=proposal.data.get("is_mutating", True)
        )
        
        # Execute the real trade via Alpaca MCP -> CORE-X
        return await corex_executor.execute(task)

    async def process_critical_section(
        self, 
        proposal: UnifiedProposal, 
        account_lock: asyncio.Lock
    ) -> Dict[str, Any]:
        """
        The locked critical section. Prevents race conditions around Buying Power.
        The lock is ONLY released after CORE-X durably journals the terminal state.
        """
        async with account_lock:
            # 1. Uncertainty Check
            decision_id = proposal.data.get("metadata", {}).get("decision_id")
            if not uncertainty_gate.can_admit_proposal(proposal.account_id, proposal.priority):
                result = {"status": "DEFERRED", "reason": "Account is UNCERTAIN. Awaiting P1_RECONCILIATION."}
                await self._record_terminal(decision_id, result)
                return result

            # 2. Authoritative Fact Refresh
            tool_name = proposal.data.get("tool_name", "")
            raw_sym = proposal.data.get("arguments", {}).get("symbol")
            meta = proposal.data.get("metadata", {})
            is_option = (tool_name == "place_option_order")

            underlying = meta.get("underlying_symbol")
            if not underlying and raw_sym:
                occ_m = re.match(r"^([A-Z]+)\d{6}[PC]\d{8}$", str(raw_sym).upper())
                if occ_m:
                    underlying = occ_m.group(1)

            equity_symbol = underlying if (is_option and underlying) else raw_sym
            symbols = [equity_symbol] if isinstance(equity_symbol, str) and equity_symbol else []
            facts = await self.fetch_authoritative_facts(proposal.account_id, symbols)
            if not facts:
                result = {"status": "FAILED", "reason": "Authoritative facts unavailable or stale."}
                await self._record_terminal(decision_id, result)
                return result

            # If option order, enrich facts with real contract quote
            if is_option and raw_sym:
                try:
                    option_quotes = await alpaca_client.get_option_quotes([str(raw_sym)])
                    opt_q = option_quotes.get(str(raw_sym))
                    opt_price = opt_q.get("mid", 0.0) if opt_q else float(meta.get("contract_mid", 0.0) or 0.0)
                except Exception:
                    opt_price = float(meta.get("contract_mid", 0.0) or 0.0)

                if opt_price > 0:
                    facts.setdefault("quotes", {})[str(raw_sym)] = opt_price
                    strike = meta.get("strike")
                    opt_type = meta.get("option_type")
                    if underlying and strike is not None and opt_type:
                        contract_key = f"{underlying}_{strike}_{opt_type}"
                        facts["quotes"][contract_key] = opt_price

            # 3. Risk Engine Integration
            decision = await self.evaluate_risk(proposal, facts)

            # 4. Interpret Risk Decision
            if decision == RiskDecision.ALLOW:
                ui_broadcaster.publish(UIActivityEvent(
                    category=UIEventCategory.RISK, status=UIEventStatus.SUCCESS,
                    message="Risk Engine ALLOWED proposal.", 
                    safe_metadata=SafeEventMetadata(reason="Passed safety limits")
                ))
                
                # 5. CORE-X Execution (Inside the lock!)
                result = await self.dispatch_to_corex(proposal)
                
                status = getattr(result, "status", None)
                
                # 6. Apply Uncertainty Gate rule based on durable CORE-X state
                if status == ExecutionState.EXECUTION_UNCERTAIN:
                    logger.critical(f"CORE-X returned UNCERTAIN for {proposal.account_id}. Locking account.")
                    uncertainty_gate.set_uncertainty(proposal.account_id, True)
                    # Reconciliation is evidence-gathering only and cannot clear
                    # durable unknown execution state without a resolved journal.
                    from backend.autonomous.lifecycle import reconciliation_service
                    asyncio.create_task(reconciliation_service.reconcile_observations(proposal.account_id))
                    result = {"status": "EXECUTION_UNCERTAIN", "reason": "Network failure after dispatch."}
                    await self._record_terminal(decision_id, result)
                    return result
                
                # 7. REJECTED: broker/service explicitly refused the dispatched request.
                #    This is a clear terminal answer — no uncertainty, no retry.
                if status == ExecutionState.REJECTED:
                    rejection_reason = getattr(result, "error_message", "Broker rejected the order")
                    ui_broadcaster.publish(UIActivityEvent(
                        category=UIEventCategory.EXECUTION, status=UIEventStatus.BLOCKED,
                        message="CORE-X dispatch rejected by broker/service.",
                        safe_metadata=SafeEventMetadata(
                            symbol=proposal.data.get("arguments", {}).get("symbol"),
                            reason=rejection_reason,
                        )
                    ))
                    result = {"status": "REJECTED", "reason": rejection_reason}
                    await self._record_terminal(decision_id, result)
                    return result

                result = {"status": "EXECUTED", "corex_status": getattr(status, "value", str(status))}
                await self._record_terminal(decision_id, result)
                
                # 🚀 NEW: EXACT EXECUTION LOG FOR UI
                tool_name = proposal.data.get("tool_name", "")
                args = proposal.data.get("arguments", {})
                
                asset_class = "OPTION" if tool_name == "place_option_order" else "STOCK"
                action_side = str(args.get("side", "BUY")).upper()
                quantity = args.get("qty", "1")
                exec_symbol = args.get("symbol", "UNKNOWN")
                
                ui_broadcaster.publish(UIActivityEvent(
                    category=UIEventCategory.EXECUTION, 
                    status=UIEventStatus.SUCCESS,
                    message=f"Successfully Executed: {action_side} {quantity} {asset_class} of {exec_symbol}", 
                    safe_metadata=SafeEventMetadata(
                        symbol=exec_symbol,
                        asset_class=asset_class.lower(),
                        reason=f"CORE-X Status: {result['corex_status']}"
                    )
                ))
                
                return result

                result = {"status": "EXECUTED", "corex_status": getattr(status, "value", str(status))}
                await self._record_terminal(decision_id, result)
                return result
            
            elif decision == RiskDecision.BLOCK:
                reason = proposal.data.get("rejection_reason", "Failed limits/exposure")
                ui_broadcaster.publish(UIActivityEvent(
                    category=UIEventCategory.RISK, status=UIEventStatus.BLOCKED,
                    message="Risk Engine BLOCKED proposal.", 
                    safe_metadata=SafeEventMetadata(reason=reason)
                ))
                result = {"status": "BLOCKED", "reason": reason}
                await self._record_terminal(decision_id, result)
                return result

            result = {"status": "FAILED", "reason": "Unknown Risk Decision."}
            await self._record_terminal(decision_id, result)
            return result

    @staticmethod
    async def _record_terminal(decision_id: Optional[str], result: Dict[str, Any]) -> None:
        await asyncio.to_thread(
            decision_ledger.record_terminal_result,
            decision_id,
            str(result.get("status", "UNKNOWN")),
            str(result.get("reason", result.get("corex_status", ""))),
        )
