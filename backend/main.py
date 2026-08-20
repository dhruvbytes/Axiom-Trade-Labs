from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

# Import humara custom Alpaca client aur naya AI Agent
from backend import alpaca_client
from backend import agent
from backend.risk_engine.risk_engine import master_risk_engine

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

# backend/main.py (Sirf chat_with_agent function replace karna hai)

@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    try:
        # 1. Fetch real account state for the Risk Engine
        account = alpaca_client.trading_client.get_account()
        positions = alpaca_client.trading_client.get_all_positions()
        
        account_data = {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "daily_loss_pct": 0.0,
            "positions": [{"symbol": p.symbol, "market_value": float(p.market_value)} for p in positions]
        }
        
        # 2. Run LIVE Deterministic Agent Pipeline (No Mocks!)
        final_response = await agent.process_trading_request(
            query=request.message, 
            account_data=account_data,
            source="HUMAN"
        )
        
        return final_response
        
    except Exception as e:
        print(f"Agent Error: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to process request. Check backend logs."
        )

# Terminal se direct run karne ke liye fallback
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)