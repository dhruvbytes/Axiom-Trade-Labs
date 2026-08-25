# backend/agent.py
import uuid
import logging
import json
from typing import List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from backend.mcp_client_manager import mcp_manager
from backend import config
from backend.tool_router.schemas import ToolRequest
from backend.tool_router.router import master_router
from backend.execution.models import ExecutableTask, ExecutionState, ExecutionResult
from backend.execution.executor import corex_executor
from backend.risk_engine.adapter import risk_adapter

logger = logging.getLogger(__name__)

# Initialize the official Gemini Client (Purana wala hi use kar rahe hain)
client = genai.Client(api_key=config.GEMINI_API_KEY)

# ==========================================
# 1. THE ENVELOPE SCHEMA
# ==========================================
class SystemExecutionEnvelope(BaseModel):
    trace_id: str
    original_query: str
    intent_nonce: str
    status: str
    validated_requests: List[ToolRequest] = Field(default_factory=list)
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    risk_rejections: List[str] = Field(default_factory=list)
    reconciliation_required: bool = False

# ==========================================
# 2. STRICT READ-ONLY REPORTER
# ==========================================
class LLMReporter:
    async def generate_response(self, envelope: SystemExecutionEnvelope) -> str:
        prompt = f"""
        You are a read-only reporting AI for a Trading Agent.
        Your ONLY job is to explain the following JSON execution envelope to the user in a natural, professional tone.
        DO NOT invent data. DO NOT suggest new trades. DO NOT hallucinate tickers.
        
        System Status: {envelope.status}
        Reconciliation Required (Critical Timeout): {envelope.reconciliation_required}
        Risk Rejections: {envelope.risk_rejections}
        
        Execution Results (if any):
        {[res.model_dump() for res in envelope.execution_results]}
        
        If 'Reconciliation Required' is True, WARN the user heavily to check their brokerage account manually.
        If 'Risk Rejections' has items, tell the user exactly why the trade was blocked.
        """
        try:
            # Using flash model for fast reporting
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
            )
            return response.text
        except Exception as e:
            return f"System executed with status: {envelope.status}, but AI formatter failed: {str(e)}"

llm_reporter = LLMReporter()

# ==========================================
# 3. DETERMINISTIC ORCHESTRATOR
# ==========================================

async def process_trading_request(query: str, account_data: dict, source: str = "HUMAN") -> dict:
    trace_id = f"trace_{uuid.uuid4().hex[:8]}"
    intent_nonce = f"nonce_{uuid.uuid4().hex[:8]}"
    
    envelope = SystemExecutionEnvelope(
        trace_id=trace_id, original_query=query, intent_nonce=intent_nonce, status="PROCESSING"
    )
    
    try:
        validated_requests = await master_router.route_request(query)
        
        if not validated_requests:
            envelope.status = "NO_ACTION_REQUIRED"
            return await _finalize(envelope, source)
            
        envelope.validated_requests = validated_requests
        
        # ==========================================
        # JIT AUTHORITATIVE FACT INJECTION
        # ==========================================
        from backend.alpaca_client import get_market_facts
        
        symbols_to_fetch = set()
        for req in validated_requests:
            sym_arg = req.arguments.get("symbol") or req.arguments.get("symbols")
            if isinstance(sym_arg, str):
                symbols_to_fetch.add(sym_arg.upper())
            elif isinstance(sym_arg, list):
                for s in sym_arg:
                    if isinstance(s, str):
                        symbols_to_fetch.add(s.upper())
                        
        # Fetch strictly required live facts asynchronously
        market_facts = await get_market_facts(list(symbols_to_fetch))
        account_data.update(market_facts)
        
        # Step 3 & 4F: Sequential Risk & Execution
        for request in validated_requests:
            risk_result = risk_adapter.evaluate(request, account_data)
            
            if not risk_result.is_approved:
                envelope.risk_rejections.append(risk_result.rejection_reason)
                envelope.status = "RISK_REJECTED"
                break # Aage ke tools execute nahi honge
            
            task = ExecutableTask(
                intent_nonce=intent_nonce,
                tool_request=request,
                risk_token=risk_result.risk_token,
                is_mutating=risk_result.is_mutating
            )
            
            exec_result = await corex_executor.execute(task)
            envelope.execution_results.append(exec_result)
            
            if exec_result.status == ExecutionState.EXECUTION_UNCERTAIN:
                envelope.reconciliation_required = True
                envelope.status = "HALTED_UNCERTAIN"
                logger.critical(f"[{trace_id}] HALTING PIPELINE: Execution Uncertain")
                break # HARD STOP
                
        if envelope.status == "PROCESSING":
            envelope.status = "SUCCESS"
            
        return await _finalize(envelope, source)
        
    except Exception as e:
        logger.error(f"[{trace_id}] Exception: {str(e)}")
        envelope.status = "SYSTEM_ERROR"
        return await _finalize(envelope, source)

async def _finalize(envelope: SystemExecutionEnvelope, source: str):
    if source == "AUTONOMOUS":
        return envelope # Future autonomous mode gets raw JSON
        
    llm_text = await llm_reporter.generate_response(envelope)
    return {
        "text_response": llm_text, 
        "debug_envelope": envelope.model_dump()
    }