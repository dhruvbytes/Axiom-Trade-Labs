# backend/risk_engine/payoff_utils.py

from typing import Set
from pydantic import BaseModel
from backend.risk_engine.risk_models import (
    UniversalTradeProposal, SystemFacts, AssetClass, OptionType, Side
)

class PayoffResult(BaseModel):
    is_infinite_risk: bool
    max_theoretical_loss: float  # Expressed as a positive absolute number
    net_premium: float           # Positive = Credit received, Negative = Debit paid

def calculate_payoff_profile(proposal: UniversalTradeProposal, facts: SystemFacts) -> PayoffResult:
    """
    Pure mathematical evaluation of a multi-leg options/equity structure.
    Calculates intrinsic payoff at inflection points to find theoretical max loss.
    """
    net_premium_per_package = 0.0
    strikes: Set[float] = {0.0}  # S=0 is always an extreme inflection point
    
    # 1. Calculate base cashflow and collect inflection points
    for leg in proposal.intent.legs:
        price = 0.0
        multiplier = 1.0
        sym = leg.instrument.underlying_symbol or proposal.intent.primary_underlying
        
        if leg.instrument.asset_class == AssetClass.EQUITY:
            if sym in facts.equity_quotes:
                price = facts.equity_quotes[sym].price
        else:
            contract_key = f"{sym}_{leg.instrument.strike}_{leg.instrument.option_type.value}"
            if contract_key in facts.option_quotes:
                price = facts.option_quotes[contract_key].price
                multiplier = facts.option_quotes[contract_key].multiplier
            if leg.instrument.strike is not None:
                strikes.add(leg.instrument.strike)
            
        # Cash flow: BUY = debit (-), SELL = credit (+)
        cash_flow = leg.ratio_qty * multiplier * price
        if leg.side == Side.BUY:
            net_premium_per_package -= cash_flow
        else:
            net_premium_per_package += cash_flow

    # 2. Infinite Risk Detection (Asymptotic Delta as S -> Infinity)
    asymptotic_delta = 0.0

    # 🚀 MATH FIX: Inject existing inventory delta from the portfolio!
    primary_sym = proposal.intent.primary_underlying
    for pos in facts.current_positions:
        if pos.get("symbol") == primary_sym:
            pos_qty = float(pos.get("qty", 0))
            if pos.get("side", "long") == "long":
                asymptotic_delta += pos_qty
            else:
                asymptotic_delta -= pos_qty

    # Calculate proposal delta impact
    for leg in proposal.intent.legs:
        delta = 0.0
        multiplier = 1.0
        sym = leg.instrument.underlying_symbol or proposal.intent.primary_underlying
        
        if leg.instrument.asset_class == AssetClass.OPTION:
            contract_key = f"{sym}_{leg.instrument.strike}_{leg.instrument.option_type.value}"
            if contract_key in facts.option_quotes:
                multiplier = facts.option_quotes[contract_key].multiplier
        
        qty = leg.ratio_qty * multiplier
        direction = 1 if leg.side == Side.BUY else -1
        
        if leg.instrument.asset_class == AssetClass.EQUITY:
            delta = qty * direction
        elif leg.instrument.asset_class == AssetClass.OPTION:
            if leg.instrument.option_type == OptionType.CALL:
                delta = qty * direction  
                
        asymptotic_delta += delta

    # If the net delta (Inventory + Proposal) is negative, risk is infinite
    is_infinite_risk = (asymptotic_delta < 0)

    # 3. Evaluate Maximum Loss across bounded domains
    max_loss = 0.0
    if not is_infinite_risk:
        for s in strikes:
            payoff_at_s = net_premium_per_package
            
            for leg in proposal.intent.legs:
                multiplier = 1.0
                sym = leg.instrument.underlying_symbol or proposal.intent.primary_underlying
                
                if leg.instrument.asset_class == AssetClass.OPTION:
                    contract_key = f"{sym}_{leg.instrument.strike}_{leg.instrument.option_type.value}"
                    if contract_key in facts.option_quotes:
                        multiplier = facts.option_quotes[contract_key].multiplier
                
                qty = leg.ratio_qty * multiplier
                direction = 1 if leg.side == Side.BUY else -1
                
                intrinsic = 0.0
                if leg.instrument.asset_class == AssetClass.EQUITY:
                    intrinsic = s * qty * direction
                elif leg.instrument.asset_class == AssetClass.OPTION:
                    k = leg.instrument.strike
                    if k is not None:
                        if leg.instrument.option_type == OptionType.CALL:
                            intrinsic = max(0.0, s - k) * qty * direction
                        elif leg.instrument.option_type == OptionType.PUT:
                            intrinsic = max(0.0, k - s) * qty * direction
                        
                payoff_at_s += intrinsic
            
            if payoff_at_s < 0:
                loss = abs(payoff_at_s)
                if loss > max_loss:
                    max_loss = loss

    # 4. Scale to Package Quantity
    total_premium = net_premium_per_package * proposal.intent.package_quantity
    total_max_loss = max_loss * proposal.intent.package_quantity if not is_infinite_risk else float('inf')

    return PayoffResult(
        is_infinite_risk=is_infinite_risk,
        max_theoretical_loss=total_max_loss,
        net_premium=total_premium
    )