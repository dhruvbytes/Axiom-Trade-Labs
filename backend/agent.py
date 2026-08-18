import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Optional, List

from backend import config
from backend.mcp_client_manager import mcp_manager

# Initialize the NEW official Gemini Client
client = genai.Client(api_key=config.GEMINI_API_KEY)

# ==========================================
# 1. DEFINE THE STRICT PROPOSAL SCHEMA
# ==========================================
class TradeProposal(BaseModel):
    action: str = Field(description="Action to take. Either 'BUY', 'SELL', or 'HOLD'.")
    asset: str = Field(description="The stock ticker symbol, e.g., 'AAPL'. Use 'NONE' if not applicable.")
    quantity: int = Field(description="Number of shares. Use 0 if not applicable.")
    estimated_price: float = Field(description="Estimated price per share based on market data. Use 0.0 if unknown.")
    reasoning_summary: str = Field(description="Concise summary of why this action is recommended.")
    confidence_score: int = Field(description="Confidence from 1 to 10.")
    data_used: List[str] = Field(description="List of data sources or tools used to make this decision.")

# ==========================================
# 2. HELPER: CONVERT MCP TOOLS TO GEMINI FORMAT
# ==========================================
def _mcp_to_gemini_tool(mcp_tool) -> types.FunctionDeclaration:
    """Converts an MCP tool schema into Gemini's FunctionDeclaration format."""
    
    properties = {}
    required = []
    
    # In newer MCP SDKs, the schema might be under mcp_tool.inputSchema as a dict
    # or mcp_tool.inputSchema.properties if it's a model. We handle it safely.
    # We will use getattr to safely get inputSchema and default to an empty dict if not found.
    # Note: Sometimes MCP tools use 'inputSchema' (camelCase) or 'input_schema' (snake_case).
    schema_dict = getattr(mcp_tool, 'inputSchema', getattr(mcp_tool, 'input_schema', {}))
    
    if isinstance(schema_dict, dict):
        required = schema_dict.get("required", [])
        for prop_name, prop_details in schema_dict.get("properties", {}).items():
            prop_type = prop_details.get("type", "string").upper()
            
            # Map common JSON schema types to Gemini types
            if prop_type == "INTEGER": type_enum = types.Type.INTEGER
            elif prop_type == "NUMBER": type_enum = types.Type.NUMBER
            elif prop_type == "BOOLEAN": type_enum = types.Type.BOOLEAN
            elif prop_type == "ARRAY": type_enum = types.Type.ARRAY
            elif prop_type == "OBJECT": type_enum = types.Type.OBJECT
            else: type_enum = types.Type.STRING # Default to string
            
            # Setup the basic schema for this property
            schema_args = {
                "type": type_enum,
                "description": prop_details.get("description", "")
            }
            
            # CRITICAL FIX: If it's an ARRAY, Gemini REQUIRES the 'items' field to know what is inside the array.
            if type_enum == types.Type.ARRAY:
                # We default to assuming it's an array of STRINGS if the MCP tool doesn't specify
                items_type = types.Type.STRING 
                if "items" in prop_details and "type" in prop_details["items"]:
                    # If MCP tells us what type is inside, we map it
                    inner_type = prop_details["items"]["type"].upper()
                    if inner_type == "INTEGER": items_type = types.Type.INTEGER
                    elif inner_type == "NUMBER": items_type = types.Type.NUMBER
                    elif inner_type == "BOOLEAN": items_type = types.Type.BOOLEAN
                
                schema_args["items"] = types.Schema(type=items_type)
            
            properties[prop_name] = types.Schema(**schema_args)

    parameters_schema = types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=required
    )

    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description,
        parameters=parameters_schema,
    )

# ==========================================
# 3. THE CORE AGENT LOOP
# ==========================================
async def process_trading_request(user_prompt: str) -> dict:
    """
    The main Agent workflow. 
    It translates tools, asks Gemini, executes tools if Gemini asks, 
    and forces Gemini to return a strict TradeProposal JSON.
    """
    
    print(f"🤖 Agent received prompt: '{user_prompt}'")
    
    # Ensure MCP is connected
    await mcp_manager.connect()
    
    # 1. Fetch available tools from MCP
    mcp_tools = await mcp_manager.get_available_tools()
    
    # 2. Convert tools for Gemini
    gemini_tools = [_mcp_to_gemini_tool(t) for t in mcp_tools]
    tool_config = types.Tool(function_declarations=gemini_tools)

    # 3. Create a chat session with the model
    # We use 3.6-flash as requested (using 3.5-flash endpoint identifier for stability in current SDK)
    chat = client.chats.create(
        model="gemini-3.5-flash", 
        config=types.GenerateContentConfig(
            tools=[tool_config],
            temperature=0.2, # Keep it deterministic
            system_instruction="You are an AI Trading Assistant. You must use the provided tools to gather real market data and account information before making any recommendations. NEVER make up ticker symbols or prices. If you don't know, use a tool."
        )
    )

    print("🧠 Thinking (Calling Gemini)...")
    
    # 4. First pass: Send prompt to Gemini
    response = chat.send_message(user_prompt)
    
    # 5. Tool execution loop (if Gemini decides it needs tools)
    api_call_count = 0

    while response.function_calls:
        api_call_count += 1
        print(f"\n🧠 [API CALL #{api_call_count}] Agent is thinking and requesting tools...")

        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = function_call.args
            
            print(f"🛠️ Gemini requested tool: {tool_name} with args: {tool_args}")
            
            try:
                # Execute the tool via our local MCP Server
                tool_result = await mcp_manager.execute_tool(tool_name, tool_args)
                
                # Format the result to send back to Gemini
                # We extract text from the MCP CallToolResult. 
                # Using getattr makes it safe across different SDK versions (is_error vs isError)
                is_err = getattr(tool_result, 'is_error', getattr(tool_result, 'isError', False))
                
                if is_err:
                    result_text = f"Error: {tool_result.content}"
                else:
                    # MCP content is usually a list of text/image blocks
                    result_text = " ".join([c.text for c in tool_result.content if getattr(c, 'type', '') == 'text'])
                
                print(f"✅ Tool returned data (length: {len(result_text)} chars)")
                
                # Send the observation back to the chat session
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_text}
                    )
                )
                
            except Exception as e:
                print(f"❌ Tool execution failed: {e}")
                # Tell Gemini the tool failed so it doesn't hallucinate
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"error": str(e)}
                    )
                )

    # 6. Final Pass: Force structured output
    print("📝 Generating final structured proposal...")
    
    # We ask Gemini one last time in the same chat, forcing the Pydantic schema
    final_response = chat.send_message(
        "Based on the data you gathered, generate a final TradeProposal.",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TradeProposal,
            temperature=0.1
        )
    )
    
    # Parse the returned JSON string into a Python dictionary
    try:
        proposal_dict = json.loads(final_response.text)
        return proposal_dict
    except Exception as e:
         return {"error": "Failed to parse Agent output", "details": str(e), "raw": final_response.text}