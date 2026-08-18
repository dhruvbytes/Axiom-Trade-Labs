from typing import List, Dict

# ==========================================
# 1. ATR (AVERAGE TRUE RANGE) CALCULATION
# ==========================================
def calculate_atr(bars: List[Dict[str, float]], period: int = 14) -> float:
    """
    Calculates the Simple Average True Range (ATR) over a given period.
    Assumes `bars` is a list of dictionaries sorted oldest to newest:
    [{'high': 150.0, 'low': 148.0, 'close': 149.0}, ...]
    
    Returns 0.0 if there is not enough data.
    """
    # We need at least 'period + 1' bars to calculate 'period' number of True Ranges
    if not bars or len(bars) < period + 1:
        return 0.0
    
    true_ranges = []
    
    for i in range(1, len(bars)):
        high = bars[i]['high']
        low = bars[i]['low']
        prev_close = bars[i-1]['close']
        
        # True Range Formula: max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        true_range = max(tr1, tr2, tr3)
        true_ranges.append(true_range)
    
    # Take the exact 'period' number of the most recent True Ranges
    recent_trs = true_ranges[-period:]
    atr = sum(recent_trs) / period
    
    return round(atr, 4)


# ==========================================
# 2. MARKET REGIME EVALUATION
# ==========================================
def determine_market_regime(spy_price: float, spy_sma_50: float, spy_atr_14: float) -> str:
    """
    Evaluates broad market stress based on SPY (S&P 500) trend and volatility.
    Returns: "Risk-On", "Neutral", or "Risk-Off"
    """
    if spy_price <= 0:
        return "Neutral" # Fallback for bad data

    # 1. Trend Analysis
    trend_is_up = spy_price > spy_sma_50
    
    # 2. Volatility Analysis (Expressed as a % of price)
    volatility_pct = spy_atr_14 / spy_price
    
    # DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE
    # Historically, SPY daily ATR > 1.5% indicates heightened market stress/fear.
    baseline_volatility_threshold = 0.015 
    is_high_volatility = volatility_pct > baseline_volatility_threshold
    
    # 3. Regime Matrix
    if trend_is_up and not is_high_volatility:
        return "Risk-On"
    elif not trend_is_up and is_high_volatility:
        return "Risk-Off"
    else:
        # e.g., Trend is down but volatility is low, or Trend is up but volatility is spiking
        return "Neutral"