from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

# Import humara custom Alpaca client aur naya AI Agent
from backend import alpaca_client
from backend import agent

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
    Receives a message from the UI, sends it to the Gemini Agent, 
    and returns the structured TradeProposal JSON.
    """
    try:
        # Agent ka process_trading_request function async hai, isliye await lagaya
        proposal = await agent.process_trading_request(request.message)
        return {"response": proposal}
    except Exception as e:
        print(f"Agent Error: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Agent failed to process request. Check backend logs."
        )

# Terminal se direct run karne ke liye fallback
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)