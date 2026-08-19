# backend/tool_router/discovery.py
from typing import List, Dict, Any
from backend.mcp_client_manager import mcp_manager

class ToolRegistry:
    def __init__(self):
        # Stores the exact raw JSON schemas for Step 4E validation
        self.tool_schemas: Dict[str, Any] = {}
        # Stores the concatenated text paragraphs for Step 4C embedding
        self.capability_documents: List[str] = []
        # Ordered list of tool names (index maps to capability_documents)
        self.tool_names: List[str] = []
        
        self.is_loaded: bool = False

    async def discover_tools(self):
        """
        Dynamically fetches tool metadata from MCP and builds semantic capabilities.
        Fails safely if MCP is unreachable.
        """
        if self.is_loaded:
            return

        # Ensure MCP server is running (Connects via STDIO from Step 2)
        await mcp_manager.connect()
        mcp_tools = await mcp_manager.get_available_tools()

        for tool in mcp_tools:
            name = tool.name
            desc = tool.description or ""
            
            # Safely handle SDK variations (camelCase vs snake_case)
            schema = getattr(tool, 'inputSchema', getattr(tool, 'input_schema', {}))
            
            # 1. Preserve exact schema for Step 4E Validation
            self.tool_schemas[name] = schema
            self.tool_names.append(name)

            # 2. Build the Dense Semantic Capability Document for Step 4C
            required_params = schema.get("required", [])
            req_str = ", ".join(required_params) if required_params else "none"
            
            # Core Document structure matches what we verified in 4C tests
            doc_parts = [f"{name}: Tool description: {desc}. Required parameters: {req_str}."]
            
            # Append dynamic parameter descriptions to give the semantic engine more context
            properties = schema.get("properties", {})
            for p_name, p_details in properties.items():
                p_desc = p_details.get("description", "No description provided")
                doc_parts.append(f"Parameter {p_name}: {p_desc}.")
                
            self.capability_documents.append(" ".join(doc_parts))
            
        self.is_loaded = True

# Singleton instance to be used by the router
tool_registry = ToolRegistry()