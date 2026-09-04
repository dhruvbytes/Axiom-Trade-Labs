# Axiom Trade Labs: Hybrid Autonomous System

An autonomous paper-trading platform for **US Stocks and Options** that combines bounded AI decision-making with strict, deterministic financial controls.

**1. Create and Activate Virtual Environment**

```bash
python -m venv venv

# Activate on Windows:
venv\Scripts\activate

# Activate on macOS/Linux:
source venv/bin/activate

```

**2. Install Dependencies**

```bash
python -m pip install -r requirements.txt

```

**3. Configure Environment Variables**
Create a `.env` file in your project root and add your API keys exactly as shown below:

```env
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_PAPER=True
GEMINI_API_KEY=your_gemini_api_key_here

```

**4. Run the Application**

```bash
# Start your backend server and open index.html

```

**System Overview & Capabilities**

* **Proprietary Engines:** Built entirely from scratch, featuring an **SCSV Router** for deterministic intent parsing, an authoritative **Risk Engine** for safety, and an isolated **CORE-X Execution** boundary.
* **Hybrid Autonomy:** The system continuously observes the market, builds context, compares hypotheses, and independently proposes a **STOCK**, **OPTION**, or **NO_TRADE** action.
* **Options Integration (Completed):** Options decision intelligence is fully connected to the autonomous pipeline. *(Note: Because of the free tier account, options are not working well as Alpaca restricts real-time OPRA feeds for automated live execution).*
* **Deterministic Safety:** AI reasoning never holds execution authority. Every proposal must pass rigorous mathematical gates in the Risk Engine before CORE-X formats the broker order.
* **Outcome-Based Learning:** The system evaluates mature trade outcomes, updating Bayesian preference ledgers to adapt its strategy across different market regimes without loosening safety constraints.