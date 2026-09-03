# backend/mcp_client_manager.py
import os
import sys
import shutil
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from backend import config

class AlpacaMCPClientManager:
    def __init__(self):
        self.session = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        if self.session is not None:
            return

        # 1. STRICT ENVIRONMENT
        clean_env = os.environ.copy()
        clean_env.update({
            "ALPACA_API_KEY": str(config.ALPACA_API_KEY),
            "ALPACA_SECRET_KEY": str(config.ALPACA_SECRET_KEY),
            "ALPACA_PAPER_TRADE": str(config.ALPACA_PAPER_TRADE).lower(),
            "ALPACA_TOOLSETS": str(config.ALPACA_TOOLSETS),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1"
        })

        # 2. RESOLVE MCP SERVER EXECUTABLE (Supports venv, Scripts/, and PATH)
        venv_scripts = os.path.dirname(sys.executable)
        exe_name = "alpaca-mcp-server.exe" if sys.platform == "win32" else "alpaca-mcp-server"
        mcp_exec = os.path.join(venv_scripts, exe_name)
        
        if not os.path.exists(mcp_exec):
            alt_exec = os.path.join(venv_scripts, "Scripts", exe_name)
            if os.path.exists(alt_exec):
                mcp_exec = alt_exec
            else:
                which_exec = shutil.which(exe_name) or shutil.which("alpaca-mcp-server")
                if which_exec and os.path.exists(which_exec):
                    mcp_exec = which_exec
                else:
                    raise RuntimeError(f"CRITICAL: Server EXECUTABLE NOT FOUND. Looked at {mcp_exec}, {alt_exec}, and PATH. Please run: python -m pip install alpaca-mcp-server")

        server_params = StdioServerParameters(
            command=mcp_exec,
            args=[],
            env=clean_env
        )

        try:
            stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            self.session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            
            await self.session.initialize()
            print("✅ Successfully connected to local Alpaca MCP Server.")
            
        except Exception as e:
            await self.cleanup()
            raise RuntimeError(f"❌ Failed to start Alpaca MCP Server natively. Error: {str(e)}")

    async def get_available_tools(self):
        if not self.session:
            raise RuntimeError("MCP Session not initialized.")
        response = await self.session.list_tools()
        return response.tools

    async def execute_tool(self, tool_name: str, arguments: dict):
        if not self.session:
            raise RuntimeError("MCP Session not initialized.")
        result = await self.session.call_tool(tool_name, arguments)
        return result

    async def cleanup(self):
        await self._exit_stack.aclose()
        self.session = None

mcp_manager = AlpacaMCPClientManager()