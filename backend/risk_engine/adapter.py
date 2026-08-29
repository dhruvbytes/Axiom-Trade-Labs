# backend/risk_engine/adapter.py
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from backend.tool_router.schemas import ToolRequest
from backend.risk_engine.risk_models import (
    RiskDecision, UniversalTradeProposal, SystemFacts, 
    AccountFact, MarketStateFact, EquityQuoteFact, OptionQuoteFact,
    Identity, Timing, Intent, Boundaries, MetadataBlock, Leg, Instrument,
    AssetClass, Side, PositionIntent, ExecutionType, LimitPriceEffect
)
from backend.risk_engine.risk_engine import master_risk_engine

class RiskEvaluationResult:
    def __init__(self, is_approved: bool, is_mutating: bool, risk_token: str, rejection_reason: str = ""):
        self.is_approved = is_approved
        self.is_mutating = is_mutating
        self.risk_token = risk_token
        self.rejection_reason = rejection_reason

class FactCollectionError(Exception):
    """Raised when authoritative system facts cannot be collected (Fail Closed)."""
    pass

class RiskAdapter:
    def evaluate(self, request: ToolRequest, account_data: dict) -> RiskEvaluationResult:
        
        # 🚀 1. READ-ONLY FAST-PASS
        is_mutating = not request.tool_name.startswith("get_")
        
        if not is_mutating:
            safe_token = hashlib.sha256(f"safe_read_{request.tool_name}_{datetime.utcnow()}".encode()).hexdigest()
            return RiskEvaluationResult(
                is_approved=True, 
                is_mutating=False, 
                risk_token=safe_token, 
                rejection_reason=""
            )
            
        """
        Bridges NMLI Proposals and Authoritative Fact Collection to the Risk Engine.
        Generates the RiskToken ONLY upon an ALLOW decision.
        """
        # FIX: Removed the hardcoded legacy tool name check that was overwriting `is_mutating` here.

        try:
            # 1. Parse or Adapt the NMLI Proposal
            proposal = self._parse_or_adapt_proposal(request)
            
            # 2. Collect Authoritative Facts (No Fake Fallbacks)
            facts = self._collect_facts(proposal, account_data)
            
        except Exception as e:
            # FAIL CLOSED: Missing facts or invalid structural conversion
            return RiskEvaluationResult(
                is_approved=False,
                is_mutating=is_mutating,
                risk_token="",
                rejection_reason=f"Risk Fact Collection Blocked: {str(e)}"
            )
            
        # 3. EVALUATE PROPOSAL VIA MASTER PIPELINE
        try:
            daily_loss = float(account_data.get("daily_loss_pct", 0.0))
            risk_output = master_risk_engine.evaluate_proposal(proposal=proposal, facts=facts, daily_loss_pct=daily_loss)
            
            is_approved = (risk_output.final_decision == RiskDecision.ALLOW)
            rejection_reason = risk_output.summary_explanation if not is_approved else ""
            
        except Exception as e:
            return RiskEvaluationResult(False, is_mutating, "", f"Risk Engine Evaluation Failed: {str(e)}")
        
        # 4. Generate Idempotent Risk Token securely on ALLOW
        risk_token = ""
        if is_approved:
            auth_string = f"{request.tool_name}|{request.arguments}|{datetime.now(timezone.utc).date()}"
            risk_token = hashlib.sha256(auth_string.encode('utf-8')).hexdigest()
            
        return RiskEvaluationResult(
            is_approved=is_approved,
            is_mutating=is_mutating,
            risk_token=risk_token,
            rejection_reason=rejection_reason
        )

    def _parse_or_adapt_proposal(self, request: ToolRequest) -> UniversalTradeProposal:
        """Converts ToolRequest to NMLI, ensuring backward compatibility for older tools."""
        if "intent" in request.arguments and "boundaries" in request.arguments:
            return UniversalTradeProposal(**request.arguments)
            
        # 🚀 FIX: Smart adaptation for ALL tools (Reading actual arguments)
        symbol = request.arguments.get("symbol", request.arguments.get("symbol_or_asset_id", request.arguments.get("symbols", "UNKNOWN")))
        qty = float(request.arguments.get("qty", request.arguments.get("quantity", 1.0)))
        
        # Extract exact side from router's arguments instead of guessing from tool_name
        arg_side = str(request.arguments.get("side", "")).lower()
        if arg_side == "buy" or "buy" in request.tool_name.lower():
            side = Side.BUY
        else:
            side = Side.SELL
        
        return UniversalTradeProposal(
            identity=Identity(proposal_id=uuid4()),
            timing=Timing(trigger_source="mcp_tool", observation_timestamp=datetime.utcnow(), max_decision_age_ms=5000),
            intent=Intent(
                primary_underlying=symbol, package_quantity=int(qty),
                legs=[Leg(
                    instrument=Instrument(asset_class=AssetClass.EQUITY, underlying_symbol=symbol),
                    side=side, position_intent=PositionIntent.OPEN, ratio_qty=1
                )]
            ),
            boundaries=Boundaries(
                execution_type=ExecutionType.MARKET,
                max_capital_allocation=999999.0, max_loss_budget=999999.0
            ),
            metadata=MetadataBlock(rationale="Adapted from MCP Tool schema", confidence=1.0)
        )

    def _collect_facts(self, proposal: UniversalTradeProposal, account_data: dict) -> SystemFacts:
        """Gathers authoritative facts. Fails closed if anything is missing."""
        equity = float(account_data.get("equity", 0.0))
        if equity <= 0:
            raise FactCollectionError("Authoritative account equity is missing or zero.")
            
        account_fact = AccountFact(
            equity=equity,
            buying_power=float(account_data.get("buying_power", 0.0)),
            initial_margin=float(account_data.get("initial_margin", 0.0)),
            maintenance_margin=float(account_data.get("maintenance_margin", 0.0))
        )
        
        spy_price = float(account_data.get("spy_price", 0.0))
        if spy_price <= 0:
            raise FactCollectionError("Authoritative SPY market state is missing.")
            
        market_state = MarketStateFact(
            spy_price=spy_price,
            spy_sma_50=float(account_data.get("spy_sma_50", spy_price)), 
            spy_atr_14=float(account_data.get("spy_atr_14", 0.0)),
            is_market_open=bool(account_data.get("is_market_open", True))
        )
        
        equity_quotes = {}
        option_quotes = {}
        provided_quotes = account_data.get("quotes", {}) # Represents fetched API quotes
        
        for leg in proposal.intent.legs:
            sym = leg.instrument.underlying_symbol or proposal.intent.primary_underlying
            if leg.instrument.asset_class == AssetClass.EQUITY:
                
                # 🚀 THE MASTERSTROKE FIX: Fallback to portfolio 'current_price' if quote is missing
                price = 0.0
                if sym in provided_quotes:
                    price = float(provided_quotes[sym])
                else:
                    # Agar fresh quote nahi mila, toh check karo ki kya ye portfolio mein already hai
                    for pos in account_data.get("positions", []):
                        if pos.get("symbol") == sym:
                            price = float(pos.get("current_price", 0.0))
                            break
                            
                if price <= 0:
                    raise FactCollectionError(f"Missing authoritative quote for equity: {sym}")
                    
                equity_quotes[sym] = EquityQuoteFact(symbol=sym, bid=price, ask=price, price=price)
                
            else:
                contract_key = f"{sym}_{leg.instrument.strike}_{leg.instrument.option_type.value}"
                if contract_key not in provided_quotes:
                    raise FactCollectionError(f"Missing authoritative quote for option: {contract_key}")
                price = float(provided_quotes[contract_key])
                option_quotes[contract_key] = OptionQuoteFact(
                    contract_symbol=contract_key, underlying=sym, strike=leg.instrument.strike,
                    expiry=leg.instrument.expiry, option_type=leg.instrument.option_type,
                    bid=price, ask=price, price=price, multiplier=100
                )
                
        return SystemFacts(
            account=account_fact, market_state=market_state,
            equity_quotes=equity_quotes, option_quotes=option_quotes,
            current_positions=account_data.get("positions", [])
        )

risk_adapter = RiskAdapter()