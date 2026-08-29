from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from contextlib import asynccontextmanager
import asyncio
from backend.execution.journal import execution_journal

# Import humara custom Alpaca client aur naya AI Agent
from backend import alpaca_client
from backend import agent
from backend.risk_engine.risk_engine import master_risk_engine
from backend.mcp_client_manager import mcp_manager
from backend.tool_router.discovery import tool_registry
from backend.tool_router.nlu_semantic import semantic_engine
from backend.tool_router.nlu_extractor import asset_extractor

# --- 🚀 INDUSTRY-STANDARD BOOT SEQUENCE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*50)
    print("🚀 [SYSTEM BOOT] Initializing Enterprise Trading Backend...")
    print("="*50)
    
    print("⏳ [0/4] Bootstrapping CORE-X Execution Journal...")
    execution_journal.bootstrap()
    execution_journal.startup_sweep_crash_recovery()
    
    print("⏳ [1/4] Booting Alpaca MCP Subprocess...")
    await mcp_manager.connect()
    
    print("⏳ [2/4] Awaiting MCP Tool Discovery & Handshake...")
    tools = []
    for _ in range(20):  # Retry polling only during boot
        tools = await mcp_manager.get_available_tools()
        if tools:
            break
        await asyncio.sleep(0.5)
    print(f"✅ MCP Server Active. {len(tools)} tools loaded securely.")
    
    print("⏳ [3/4] Pre-warming NLU Semantic Engine (ONNX)...")
    semantic_engine.load()
    print("✅ Semantic Engine loaded.")
    
    print("⏳ [4/4] Building Deterministic Asset Trie (Alpaca API)...")
    asset_extractor.build_index()
    print("✅ Symbology index built successfully.")
    
    print("\n🟢 [SYSTEM BOOT COMPLETE] AI Agent is ready to accept orders!\n")
    yield  # Server runs here
    
    print("\n🛑 [SYSTEM SHUTDOWN] Cleaning up resources...")
    await mcp_manager.cleanup()

# Attach the lifespan to FastAPI
app = FastAPI(title="AI Trading Lab API", lifespan=lifespan)

# --- CORS Settings (Frontend ko allow karne ke liye) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PositionModel(BaseModel):
    symbol: str
    qty: str
    market_value: str
    unrealized_pl: str

class PortfolioResponse(BaseModel):
    buying_power: str
    portfolio_value: str
    positions: List[PositionModel]

class ChatRequest(BaseModel):
    message: str

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/portfolio", response_model=PortfolioResponse)
def get_portfolio():
    try:
        summary = alpaca_client.get_portfolio_summary()
        positions = alpaca_client.get_current_positions()
        return {
            "buying_power": summary["buying_power"],
            "portfolio_value": summary["portfolio_value"],
            "positions": positions
        }
    except Exception as e:
        print(f"Backend Internal Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Alpaca account data.")

@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    try:
        account = alpaca_client.trading_client.get_account()
        positions = alpaca_client.trading_client.get_all_positions()
        account_data = {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "daily_loss_pct": 0.0,
            # 🚀 PRODUCTION MODE: Only normal live positions from Alpaca
            "positions": [{
                "symbol": p.symbol, 
                "qty": float(p.qty), 
                "side": "long", 
                "current_price": float(p.current_price),
                "market_value": float(p.market_value)
            } for p in positions]
        }
        
        final_response = await agent.process_trading_request(
            query=request.message, 
            account_data=account_data,
            source="HUMAN"
        )
        return final_response
        
    except Exception as e:
        print(f"Agent Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process request.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)