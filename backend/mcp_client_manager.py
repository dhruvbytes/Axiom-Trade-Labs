import os
import contextlib
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from backend import config

class AlpacaMCPClientManager:
    def __init__(self):
        self.session = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        """
        Starts the official Alpaca MCP server via 'uvx' as a subprocess on STDIO.
        Secures it with read-only toolsets.
        """
        if self.session is not None:
            return # Already connected

        # Setup server parameters according to official Alpaca MCP guidelines
        server_params = StdioServerParameters(
            command="uvx",
            args=["alpaca-mcp-server"],
            env={
                **os.environ,  # Keep base environment
                "ALPACA_API_KEY": config.ALPACA_API_KEY,
                "ALPACA_SECRET_KEY": config.ALPACA_SECRET_KEY,
                "ALPACA_PAPER_TRADE": str(config.ALPACA_PAPER_TRADE).lower(),
                "ALPACA_TOOLSETS": config.ALPACA_TOOLSETS,
                "PATH": os.environ.get("PATH", "") # Required for subprocess to find uvx
            }
        )

        try:
            # Context manager flow for STDIO client
            stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            
            # Start the session
            self.session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            
            # Initialize connection to the server
            await self.session.initialize()
            print("✅ Successfully connected to local Alpaca MCP Server.")
            
        except Exception as e:
            await self.cleanup()
            raise RuntimeError(f"❌ Failed to start Alpaca MCP Server. Ensure 'uvx' is installed. Error: {str(e)}")

    async def get_available_tools(self):
        """Fetches the list of tools currently exposed by the MCP server."""
        if not self.session:
            raise RuntimeError("MCP Session not initialized. Call connect() first.")
        
        response = await self.session.list_tools()
        return response.tools

    async def execute_tool(self, tool_name: str, arguments: dict):
        """Calls a specific tool on the MCP server and returns the result."""
        if not self.session:
            raise RuntimeError("MCP Session not initialized.")
        
        # print(f"Executing tool: {tool_name}") # Uncomment for deep debugging
        result = await self.session.call_tool(tool_name, arguments)
        return result

    async def cleanup(self):
        """Gracefully closes the MCP server subprocess."""
        await self._exit_stack.aclose()
        self.session = None

# Global instance to be used across FastAPI requests
mcp_manager = AlpacaMCPClientManager()


# ==========================================
# TESTING BLOCK (Run this file directly)
# ==========================================
if __name__ == "__main__":
    import asyncio

    async def run_test():
        print("Starting MCP Client Test...")
        manager = AlpacaMCPClientManager()
        
        try:
            # 1. Test Connection
            await manager.connect()
            
            # 2. Test Fetching Tools
            tools = await manager.get_available_tools()
            print(f"\n✅ Total Tools Loaded: {len(tools)}")
            
            print("\nAvailable Tools:")
            for tool in tools:
                print(f" - {tool.name}: {tool.description[:60]}...")
                
        except Exception as e:
            print(f"\n❌ Test Failed: {e}")
        finally:
            # 3. Clean up
            await manager.cleanup()
            print("\nTest Finished & Cleaned up.")

    # Run the async test
    asyncio.run(run_test())