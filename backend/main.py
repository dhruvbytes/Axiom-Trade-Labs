from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

# Import humara custom Alpaca client aur naya AI Agent
from backend import alpaca_client
from backend import agent
from backend.risk_engine import master_risk_engine

app = FastAPI(title="AI Trading Lab API")

# --- CORS Settings (Frontend ko allow karne ke liye) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For learning lab, we allow all origins.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models (Data formatting strictness ke liye) ---
class PositionModel(BaseModel):
    symbol: str
    qty: str
    market_value: str
    unrealized_pl: str

class PortfolioResponse(BaseModel):
    buying_power: str
    portfolio_value: str
    positions: List[PositionModel]

# Pydantic model for incoming chat requests
class ChatRequest(BaseModel):
    message: str
    
# --- API Endpoints ---

@app.get("/api/health")
def health_check():
    """Simple endpoint to verify backend is running."""
    return {"status": "ok"}

@app.get("/api/portfolio", response_model=PortfolioResponse)
def get_portfolio():
    """
    Combines account summary and positions into a single safe JSON response.
    Never exposes raw Alpaca objects or keys.
    """
    try:
        # Fetch data from our client
        summary = alpaca_client.get_portfolio_summary()
        positions = alpaca_client.get_current_positions()
        
        # Combine into the Pydantic model format
        return {
            "buying_power": summary["buying_power"],
            "portfolio_value": summary["portfolio_value"],
            "positions": positions
        }
    except Exception as e:
        # Catch internal errors and return a safe HTTP 500 error to the frontend
        print(f"Backend Internal Error: {e}") # This prints to console for us
        raise HTTPException(
            status_code=500, 
            detail="Failed to fetch Alpaca account data. Check backend logs."
        )

@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Receives a message, gets AI proposal, and runs it through the Risk Engine.
    """
    try:
        # 1. Get AI Proposal
        proposal = await agent.process_trading_request(request.message)
        
        # If agent failed/hallucinated, return early
        if "error" in proposal:
            return {"proposal": proposal, "risk_evaluation": None}
            
        # 2. Fetch real account state for the Risk Engine
        # Call the methods on the actual trading_client instance
        account = alpaca_client.trading_client.get_account()
        positions = alpaca_client.trading_client.get_all_positions()
        
        account_equity = float(account.equity)
        buying_power = float(account.buying_power)
        last_equity = float(account.last_equity)
        
        # Calculate actual daily drawdown
        daily_loss_pct = 0.0
        if last_equity > 0 and account_equity < last_equity:
            daily_loss_pct = (last_equity - account_equity) / last_equity
            
        formatted_positions = [{"symbol": p.symbol, "market_value": float(p.market_value)} for p in positions]

        # 3. Run the Risk Engine Pipeline
        # Note: For this MVP, we use static fallback values for SPY Market Data 
        # to keep the endpoint fast and avoid complex historical API rate limits.
        evaluation = master_risk_engine.evaluate_proposal(
            proposal=proposal,
            account_equity=account_equity,
            buying_power=buying_power,
            daily_loss_pct=daily_loss_pct,
            current_positions=formatted_positions,
            spy_price=550.0,    # DEMO DEFAULT (Mocked)
            spy_sma_50=540.0,   # DEMO DEFAULT (Mocked Trend is UP)
            spy_atr_14=5.0,     # DEMO DEFAULT (Mocked Low Volatility)
            asset_bars_14d=None # Bypasses ATR check for MVP speed
        )
        
        # 4. Return both Proposal AND Risk Evaluation
        return {
            "proposal": proposal,
            "risk_evaluation": evaluation.model_dump()
        }
        
    except Exception as e:
        print(f"Agent/Risk Error: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to process request. Check backend logs."
        )

# Terminal se direct run karne ke liye fallback
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)