# backend/risk_engine/adapter.py
import hashlib
from datetime import datetime, timezone
from backend.tool_router.schemas import ToolRequest
from backend.risk_engine.risk_engine import master_risk_engine
from backend.risk_engine.risk_models import RiskDecision

class RiskEvaluationResult:
    def __init__(self, is_approved: bool, is_mutating: bool, risk_token: str, rejection_reason: str = ""):
        self.is_approved = is_approved
        self.is_mutating = is_mutating
        self.risk_token = risk_token
        self.rejection_reason = rejection_reason

class RiskAdapter:
    def evaluate(self, request: ToolRequest, account_data: dict) -> RiskEvaluationResult:
        """
        Bridges the gap between Step 4E (ToolRequest) and the Legacy Risk Engine.
        Generates the RiskToken required by 4F (CORE-X).
        """
        # Determine if it's a mutating action
        is_mutating = request.tool_name in ["buy_stock", "sell_stock", "place_order"]
        action = "HOLD"
        if "buy" in request.tool_name.lower(): action = "BUY"
        elif "sell" in request.tool_name.lower(): action = "SELL"
        
        # Map arguments to old 'proposal' dictionary format
        proposal = {
            "action": action,
            "asset": request.arguments.get("symbol", "NONE"),
            "quantity": request.arguments.get("qty", request.arguments.get("quantity", 0)),
            "estimated_price": request.arguments.get("price", 550.0) # Fallback for MVP
        }
        
        # Call the ACTUAL locked Risk Engine
        risk_output = master_risk_engine.evaluate_proposal(
            proposal=proposal,
            account_equity=account_data.get("equity", 100000.0),
            buying_power=account_data.get("buying_power", 100000.0),
            daily_loss_pct=account_data.get("daily_loss_pct", 0.0),
            current_positions=account_data.get("positions", []),
            spy_price=550.0, spy_sma_50=540.0, spy_atr_14=5.0
        )
        
        is_approved = risk_output.final_decision == RiskDecision.ALLOW
        
        # Generate token ONLY if approved
        risk_token = ""
        if is_approved:
            auth_string = f"{request.tool_name}|{request.arguments}|{datetime.now(timezone.utc).date()}"
            risk_token = hashlib.sha256(auth_string.encode('utf-8')).hexdigest()
            
        return RiskEvaluationResult(
            is_approved=is_approved,
            is_mutating=is_mutating,
            risk_token=risk_token,
            rejection_reason=risk_output.summary_explanation if not is_approved else ""
        )

risk_adapter = RiskAdapter()