import os
from dotenv import load_dotenv

# Load env variables (Useful for local dev, Railway injects them automatically)
load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🚀 DEMO SECURITY TOKEN
DEMO_ACCESS_TOKEN = os.getenv("DEMO_ACCESS_TOKEN")
if not DEMO_ACCESS_TOKEN:
    print("WARNING: DEMO_ACCESS_TOKEN not set. Defaulting to 'axiom-demo' for local testing.")
    DEMO_ACCESS_TOKEN = "axiom-demo"

# 🚀 STRICT PAPER TRADING LOCK (Fails closed if not explicitly True)
ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "false").lower() in ("true", "1", "yes")
ALPACA_PAPER = ALPACA_PAPER_TRADE

if not ALPACA_PAPER_TRADE:
    raise ValueError("CRITICAL SECURITY ERROR: ALPACA_PAPER_TRADE must be set to 'True' in production. Live trading is STRICTLY PROHIBITED in this deployment.")

# 🚀 RAILWAY PERSISTENT VOLUME MOUNT
AXIOM_DATA_DIR = os.getenv("AXIOM_DATA_DIR", ".")
os.makedirs(AXIOM_DATA_DIR, exist_ok=True)
SQLITE_DB_PATH = os.path.join(AXIOM_DATA_DIR, "decision_journal.db")

ALPACA_TOOLSETS = os.getenv("ALPACA_TOOLSETS", "account,stock-data,trading,options")
AUTONOMOUS_ALLOW_OPTIONS = os.getenv("AUTONOMOUS_ALLOW_OPTIONS", "true").lower() in ("true", "1", "yes")

# Security Check
missing_keys = []
if not ALPACA_API_KEY: missing_keys.append("ALPACA_API_KEY")
if not ALPACA_SECRET_KEY: missing_keys.append("ALPACA_SECRET_KEY")
if not GEMINI_API_KEY: missing_keys.append("GEMINI_API_KEY")

if missing_keys:
    raise ValueError(f"CRITICAL ERROR: Missing credentials: {', '.join(missing_keys)}")