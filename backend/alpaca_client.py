from alpaca.trading.client import TradingClient
from backend import config

# 1. Initialize official Alpaca client (Paper trading securely loaded from config)
trading_client = TradingClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY,
    paper=config.ALPACA_PAPER
)

def get_portfolio_summary():
    """
    Fetches the account details and returns only buying power and equity.
    """
    try:
        account = trading_client.get_account()
        return {
            "buying_power": str(account.buying_power),
            "portfolio_value": str(account.equity)
        }
    except Exception as e:
        # Catch errors safely without leaking full credential objects
        raise RuntimeError(f"Failed to fetch account info from Alpaca. Details: {str(e)}")

def get_current_positions():
    """
    Fetches all open positions and formats them into a simple dictionary list.
    """
    try:
        raw_positions = trading_client.get_all_positions()
        formatted_positions = []
        
        for pos in raw_positions:
            formatted_positions.append({
                "symbol": pos.symbol,
                "qty": str(pos.qty),
                "market_value": str(pos.market_value),
                "unrealized_pl": str(pos.unrealized_pl)
            })
            
        return formatted_positions
    except Exception as e:
        raise RuntimeError(f"Failed to fetch positions from Alpaca. Details: {str(e)}")

# Yeh block sirf testing ke liye hai. Jab hum directly is file ko run karenge tabhi chalega.
if __name__ == "__main__":
    print("Testing Alpaca Connection...")
    try:
        summary = get_portfolio_summary()
        print(f"\n✅ Connection Successful!")
        print(f"💰 Portfolio Value: ${summary['portfolio_value']}")
        print(f"🛒 Buying Power: ${summary['buying_power']}")
        
        positions = get_current_positions()
        print(f"\n📊 Open Positions: {len(positions)}")
        for p in positions:
            print(f"  - {p['qty']} shares of {p['symbol']} | P&L: ${p['unrealized_pl']}")
            
    except Exception as err:
        print(f"\n❌ Error: {err}")