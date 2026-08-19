# test_step4d.py
import sys
import os
import asyncio
import time

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.tool_router.discovery import tool_registry
from backend.tool_router.nlu_semantic import semantic_engine
from backend.mcp_client_manager import mcp_manager

async def run_discovery_test():
    print("🚀 Running Step 4D: Dynamic MCP Discovery...\n")
    
    # 1. Load Step 4C Engine
    print("Loading 4C Semantic Engine...")
    semantic_engine.load()
    
    # 2. Trigger 4D Discovery
    print("Starting MCP Server and Fetching Tool Metadata...")
    t0 = time.perf_counter()
    try:
        await tool_registry.discover_tools()
        discovery_time = (time.perf_counter() - t0) * 1000
        print(f"✅ Discovered {len(tool_registry.tool_names)} tools dynamically in {discovery_time:.2f} ms.\n")
    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return

    # 3. Display Extracted Metadata
    print("--- DYNAMIC CAPABILITY DOCUMENTS (For 4C) ---")
    for idx, name in enumerate(tool_registry.tool_names):
        doc = tool_registry.capability_documents[idx]
        print(f"\n[{name}]\n{doc[:150]}...") # Truncate for terminal readability
        
    print("\n--- SCHEMA VALIDATION DICTIONARY (For 4E) ---")
    sample_tool = tool_registry.tool_names[0]
    print(f"Keys available for validation ({sample_tool}): {list(tool_registry.tool_schemas[sample_tool].keys())}")

    # 4. End-to-End Compatibility Test with 4C
    print("\n--- 4C + 4D INTEGRATION TEST ---")
    print("Embedding dynamic documents...")
    t1 = time.perf_counter()
    dynamic_embeddings = semantic_engine.embed_batch(tool_registry.capability_documents)
    embed_time = (time.perf_counter() - t1) * 1000
    
    print(f"✅ Matrix shape: {dynamic_embeddings.shape} | Batch Embed Time: {embed_time:.2f} ms")
    
    # Clean up subprocess
    await mcp_manager.cleanup()

if __name__ == "__main__":
    asyncio.run(run_discovery_test())