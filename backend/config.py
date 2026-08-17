import os
from dotenv import load_dotenv

# .env file se environment variables load karo
load_dotenv()

# Variables ko fetch karo
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Alpaca MCP V2 Server config expects ALPACA_PAPER_TRADE=true
ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "true").lower() in ("true", "1", "yes")
# Alias for Step 1 compatibility so alpaca_client.py does not break
ALPACA_PAPER = ALPACA_PAPER_TRADE

# Tool filtering: Restrict AI to only account and stock-data initially (Execution disabled)
ALPACA_TOOLSETS = os.getenv("ALPACA_TOOLSETS", "account,stock-data")

# Security Check: Fail fast if ANY required secret is missing
missing_keys = []
if not ALPACA_API_KEY: missing_keys.append("ALPACA_API_KEY")
if not ALPACA_SECRET_KEY: missing_keys.append("ALPACA_SECRET_KEY")
if not GEMINI_API_KEY: missing_keys.append("GEMINI_API_KEY")

if missing_keys:
    raise ValueError(f"CRITICAL ERROR: Missing credentials in .env file: {', '.join(missing_keys)}")