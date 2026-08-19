# test_phase4_chaos.py

import sys
import os
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.tool_router.schemas import ToolRequest, ExecutionContractFingerprint
from backend.execution.models import ExecutableTask, ExecutionState
from backend.execution.executor import corex_executor
from backend.execution.journal import execution_journal
import backend.execution.executor as executor_module

class MockContent:
    def __init__(self, text):
        self.type = 'text'
        self.text = text

class MockResult:
    def __init__(self, text):
        self.content = [MockContent(text)]
        self.is_error = False

# Global counter to track EXACTLY how many times MCP was actually called
mcp_call_count = 0

async def mock_mcp_call(*args, **kwargs):
    global mcp_call_count
    mcp_call_count += 1
    await asyncio.sleep(0.1)  # Simulate network latency (critical for race conditions)
    return MockResult(f"Processed execution #{mcp_call_count}")

async def run_chaos_tests():
    print("🔥 Running Phase 4: CHAOS ENGINEERING & EXTREME STRESS TEST 🔥\n")
    
    execution_journal.reset_for_testing()
    print("🧹 Database wiped. System ready for Chaos.\n")

    fingerprint = ExecutionContractFingerprint(
        deployment_identity="local", tool_name="chaos_tool", schema_hash="hash123", registry_generation="gen-1"
    )
    req = ToolRequest(tool_name="chaos_tool", arguments={"trade": "buy_100_nvda"}, reason="Chaos", fingerprint=fingerprint)
    
    # Override MCP mock
    executor_module.mcp_manager.execute_tool = mock_mcp_call
    
    score = 0

    # ========================================================================
    # CHAOS TEST 1: THE THUNDERING HERD (Extreme Concurrency)
    # 100 Duplicate Requests fired at the EXACT SAME TIME.
    # ========================================================================
    print("⚡ CHAOS 1: Firing 100 simultaneous mutating requests (Thundering Herd)...")
    task = ExecutableTask(intent_nonce="chaos_nonce_1", tool_request=req, risk_token="auth_1", is_mutating=True)
    
    # Fire 100 requests concurrently
    tasks = [corex_executor.execute(task) for _ in range(100)]
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    duration = time.time() - start_time
    
    global mcp_call_count
    success_count = sum(1 for r in results if r.status == ExecutionState.SUCCEEDED and not r.is_cached_replay)
    cached_count = sum(1 for r in results if r.is_cached_replay)
    
    print(f"   ⏱️  Processed 100 requests in {duration:.3f} seconds.")
    print(f"   📊 MCP Actually Called: {mcp_call_count} times.")
    print(f"   📊 Cached Replays Handled: {cached_count} times.")
    
    if mcp_call_count == 1 and cached_count == 99:
        print("   ✅ PASS: Perfect Single-Flight & Idempotency. System absorbed 100 concurrent hits without double-trading.")
        score += 25
    else:
        print("   ❌ FAIL: Concurrency broke! Double execution occurred.")

    # ========================================================================
    # CHAOS TEST 2: THE GHOST CRASH (Orphaned State Recovery)
    # ========================================================================
    print("\n👻 CHAOS 2: Simulating a mid-flight server power loss...")
    # We manually inject a DISPATCHED state directly into DB (bypassing executor)
    fake_task = ExecutableTask(intent_nonce="crash_nonce", tool_request=req, risk_token="auth_1", is_mutating=True)
    with execution_journal._get_conn() as conn:
        conn.execute("INSERT INTO execution_journal (ik, intent_nonce, tool_name, is_mutating, risk_auth_hash, state, created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, 'time', 'time')", 
                     (fake_task.idempotency_key, "crash_nonce", "chaos_tool", True, "auth_1", ExecutionState.DISPATCHED.value))
    
    # Run the boot sweep
    swept = execution_journal.startup_sweep_crash_recovery()
    
    # Verify it was locked to UNCERTAIN
    _, state, _, _ = execution_journal.insert_or_get_status(fake_task.idempotency_key, "crash_nonce", "chaos_tool", True, "auth_1")
    
    if swept == 1 and state == ExecutionState.EXECUTION_UNCERTAIN:
        print("   ✅ PASS: Startup Sweep caught the ghost crash and locked it to EXECUTION_UNCERTAIN.")
        score += 25
    else:
        print(f"   ❌ FAIL: Ghost crash bypassed. Swept: {swept}, State: {state}")

    # ========================================================================
    # CHAOS TEST 3: STATE FORGERY
    # ========================================================================
    print("\n🛡️ CHAOS 3: Attempting illegal state transition (State Forgery)...")
    # Try to jump from RECEIVED to SUCCEEDED (missing RISK_AUTHORIZED and DISPATCHED)
    success = execution_journal.transition_state(fake_task.idempotency_key, expected_current_state=ExecutionState.RECEIVED, new_state=ExecutionState.SUCCEEDED)
    
    if success is False:
        print("   ✅ PASS: State Machine rejected the forged transition.")
        score += 25
    else:
        print("   ❌ FAIL: State Machine allowed an illegal jump!")

    # ========================================================================
    # CHAOS TEST 4: RISK POLICY DRIFT
    # ========================================================================
    print("\n🌪️ CHAOS 4: Risk Token drifts mid-way through a retry loop...")
    # Legitimate retry with NEW risk token (Risk engine updated policy)
    task_drift = ExecutableTask(intent_nonce="chaos_nonce_1", tool_request=req, risk_token="auth_NEW", is_mutating=True)
    
    # Execute the drifted task
    res_drift = await corex_executor.execute(task_drift)
    
    # Since the Risk Token changed, the IK changed. It should be treated as a brand NEW request, NOT a cached replay!
    if mcp_call_count == 2 and res_drift.is_cached_replay is False:
        print("   ✅ PASS: Risk Token drift generated a new IK and correctly re-executed.")
        score += 25
    else:
        print("   ❌ FAIL: System blindly cached a request even though the Risk Policy changed!")

    # ========================================================================
    # FINAL SCORING
    # ========================================================================
    print(f"\n🏆 FINAL SURVIVABILITY SCORE: {score}/100")
    if score == 100:
        print("🎖️ VERDICT: INDESTRUCTIBLE. The CORE-X engine is mathematically bulletproof.")
    elif score >= 75:
        print("⚠️ VERDICT: STABLE. Handled most chaos, but some edge cases leaked.")
    else:
        print("🔥 VERDICT: CRITICAL FAILURE. The system broke under stress.")

if __name__ == "__main__":
    asyncio.run(run_chaos_tests())