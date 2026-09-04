# backend/main.py

import os
from fastapi import APIRouter, FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import DEMO_ACCESS_TOKEN
from pydantic import BaseModel
from typing import List
from contextlib import asynccontextmanager
import asyncio
from backend.execution.journal import execution_journal
import logging

# Import humara custom Alpaca client aur naya AI Agent
from backend.tool_router.nlu_semantic import semantic_engine
from backend import alpaca_client
from backend import agent
from backend.mcp_client_manager import mcp_manager
from backend.tool_router.nlu_extractor import asset_extractor

# Autonomous Engine Lifecycles & UI Broadcaster
from backend.autonomous.lifecycle import start_autonomous_system, stop_autonomous_system
from backend.autonomous.ui_events import ui_broadcaster
from backend.autonomous.settings_manager import runtime_policy_manager, RuntimePolicy
from backend.autonomous.uncertainty import uncertainty_gate

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

import sys
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# NEW DIGITAL SWITCH: Event-Driven Ignition
ui_connected_event = asyncio.Event()

# --- [SYSTEM BOOT] INDUSTRY-STANDARD BOOT SEQUENCE ---
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    print("\n" + "="*50)
    print("[SYSTEM BOOT] Initializing Enterprise Trading Backend...")
    print("="*50)
    
    print("[0/5] Bootstrapping CORE-X Execution Journal...")
    execution_journal.bootstrap()
    execution_journal.startup_sweep_crash_recovery()
    
    print("[1/5] Booting Alpaca MCP Subprocess...")
    await mcp_manager.connect()
    
    print("[2/5] Awaiting MCP Tool Discovery & Handshake...")
    tools = []
    for _ in range(20):  # Retry polling only during boot
        tools = await mcp_manager.get_available_tools()
        if tools:
            break
        await asyncio.sleep(0.5)
    print(f"[OK] MCP Server Active. {len(tools)} tools loaded securely.")
    
    print("[3/5] Pre-warming NLU Semantic Engine (ONNX)...")
    semantic_engine.load()
    print("[OK] Semantic Engine loaded.")
    
    print("[4/5] Building Deterministic Asset Trie (Alpaca API)...")
    asset_extractor.build_index()
    print("[OK] Symbology index built successfully.")
    
    # STRICT EVENT-DRIVEN IGNITION (No timers)
    async def wait_for_ui_and_ignite():
        print("[5/5] System paused. Waiting for Frontend UI to connect...")
        try:
            # Waits exactly until UI connects (with a 30s fallback for headless testing)
            await asyncio.wait_for(ui_connected_event.wait(), timeout=30.0)
            print("[EVENT] UI Connection Detected! Igniting Autonomous Brain NOW...")
        except asyncio.TimeoutError:
            print("[INFO] No UI connected within 30s. Igniting in headless mode...")
        
        await start_autonomous_system()
        print("[OK] Autonomous Daemon is LIVE.")

    asyncio.create_task(wait_for_ui_and_ignite())
    
    print("\n[SYSTEM READY] Awaiting Frontend Connection & Autonomous Ignition...\n")
    yield  # Server runs here and accepts the UI connection instantly!
    
    print("\n[SYSTEM SHUTDOWN] Cleaning up resources...")
    # Autonomous Brain Safe Shutdown
    await stop_autonomous_system()
    await mcp_manager.cleanup()

# ==========================================
# YEH LINE DELETE HO GAYI THI! 
app = FastAPI(title="AI Trading Lab API", lifespan=lifespan)
# ==========================================

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

# 🚀 DEMO AUTHENTICATION FUNCTION
async def verify_demo_token(request: Request):
    """Secures all endpoints. Checks header first, fallback to query param for SSE."""
    token = request.headers.get("Authorization")
    if not token:
        token = request.query_params.get("token")
    else:
        token = token.replace("Bearer ", "")
        
    if token != DEMO_ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing Demo Token")

# 🚀 APPLY AUTH TO SETTINGS ROUTER
settings_router = APIRouter(prefix="/api/settings", dependencies=[Depends(verify_demo_token)])

@settings_router.get("")
def get_settings():
    policy = runtime_policy_manager.get_current()
    return {
        "active_policy": policy.model_dump(),
        "immutable_protected": [
            "absolute_concentration_cap", 
            "absolute_daily_loss_halt",
            "freeze_timeout_seconds",
            "options_max_spread"
        ],
        "uncertainty_state": uncertainty_gate.get_uncertainty_state("default_account")
    }

@settings_router.put("")
async def apply_settings(new_policy: RuntimePolicy):
    # Validation happens automatically via Pydantic. Out-of-bounds = 422.
    try:
        updated = await runtime_policy_manager.apply_policy(new_policy, source="USER")
        return {"status": "success", "active_policy": updated.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Persistence failed. Old policy remains active.")

@settings_router.post("/reset")
async def reset_settings():
    try:
        default_policy = RuntimePolicy()
        updated = await runtime_policy_manager.apply_policy(default_policy, source="RESET")
        return {"status": "success", "active_policy": updated.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Reset failed. Old policy remains active.")

app.include_router(settings_router)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/activity-stream", dependencies=[Depends(verify_demo_token)])
async def activity_stream(request: Request):
    """
    SSE Endpoint for Live UI Activity Console.
    Includes keep-alive heartbeat, strict disconnect detection, and proper buffering headers.
    """
    ui_connected_event.set()
    
    async def event_generator():
        q = ui_broadcaster.subscribe()
        try:
            while True:
                # 1. Proactive Disconnect Detection (FastAPI Request lifecycle)
                if await request.is_disconnected():
                    break
                    
                try:
                    # 2. Bounded await with a 15-second heartbeat
                    event_json = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {event_json}\n\n"
                except asyncio.TimeoutError:
                    # 3. Idle Heartbeat (SSE comment) to keep connection alive
                    yield ": heartbeat\n\n"
                    
        except asyncio.CancelledError:
            # Normal behavior when browser drops the connection abruptly during yield
            pass
        except Exception as e:
            # Fallback isolation: log internally, do not crash server
            print(f"[SSE Error] Stream interrupted safely: {e}")
        finally:
            # 4. Guaranteed Cleanup
            ui_broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/portfolio", response_model=PortfolioResponse, dependencies=[Depends(verify_demo_token)])
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

@app.post("/api/chat", dependencies=[Depends(verify_demo_token)])
async def chat_with_agent(request: ChatRequest):
    try:
        account = alpaca_client.trading_client.get_account()
        positions = alpaca_client.trading_client.get_all_positions()
        account_data = {
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "daily_loss_pct": 0.0,
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

@app.get("/api/autonomous/state", dependencies=[Depends(verify_demo_token)])
def get_autonomous_state():
    """Exposes public status snapshot of the bounded autonomous decision controller."""
    from backend.autonomous.lifecycle import get_decision_controller
    controller = get_decision_controller()
    return controller.status_snapshot()

@app.get("/api/autonomous/dashboard-state", dependencies=[Depends(verify_demo_token)])
def get_autonomous_dashboard_state():
    from backend.autonomous.lifecycle import get_decision_controller
    from backend.autonomous.decision_ledger import decision_ledger
    from backend.autonomous.uncertainty import uncertainty_gate

    controller = get_decision_controller()
    engine_state = controller.status_snapshot() if controller else {}
    
    # Inject real authoritative uncertainty state
    engine_state["uncertainty"] = uncertainty_gate.get_uncertainty_state("default_account")

    return {
        "engine_state": engine_state,
        "recent_decisions": decision_ledger.get_recent_decisions(30),
        "strategy_preferences": decision_ledger.get_all_preferences(),
        "recent_learning": decision_ledger.get_recent_outcomes(15)
    }

@app.post("/api/admin/reconciliation/check", dependencies=[Depends(verify_demo_token)])
async def trigger_admin_reconciliation():
    """Admin-only trigger for uncertainty reconciliation.

    Logs audit warning and executes fail-closed reconciliation against authoritative facts.
    """
    admin_logger = logging.getLogger("backend.admin")
    admin_logger.warning("AUDIT: Admin reconciliation check manually triggered.")
    from backend.autonomous.lifecycle import reconciliation_service
    result = await reconciliation_service.reconcile_observations()
    return {"status": result.status, "reason": result.reason}

# 🚀 MOUNT FRONTEND (Must be at the very bottom after all API routes)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # 🚀 Railway passes PORT environment variable dynamically
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)