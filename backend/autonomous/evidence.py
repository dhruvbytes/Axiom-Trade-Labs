"""Targeted evidence collection with an optional non-authoritative LLM step."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from backend.autonomous.decision_models import (
    ContextSnapshot,
    EvidenceResult,
    HypothesisAction,
    HypothesisEvaluation,
)
from backend.autonomous.llm_governance import LLMGovernance
from backend.autonomous.options_filter import OptionsDataFilter


class EvidencePlanner:
    """Validates only the facts requested by an approved hypothesis.

    LLM synthesis is opt-in per hypothesis and is never given execution authority.
    The default registry does not require it, keeping the market-event path local.
    """

    def __init__(
        self,
        governance: Optional[LLMGovernance] = None,
        option_chain_fetcher: Optional[Callable[[str, int, int], Awaitable[List[Dict]]]] = None,
        option_quotes_fetcher: Optional[Callable[[List[str]], Awaitable[Dict]]] = None,
    ):
        self.governance = governance or LLMGovernance(max_concurrent=1, max_calls_per_minute=2, timeout_seconds=4.0)
        self.option_chain_fetcher = option_chain_fetcher
        self.option_quotes_fetcher = option_quotes_fetcher

    async def _resolve_option_contract(
        self,
        evaluation: HypothesisEvaluation,
        snapshot: ContextSnapshot,
    ) -> Optional[Dict]:
        if not self.option_chain_fetcher or not self.option_quotes_fetcher:
            return None

        target_type = "call" if evaluation.action == HypothesisAction.BUY_CALL else "put"
        try:
            raw_chain = await self.option_chain_fetcher(snapshot.symbol, 14, 45)
            if not raw_chain:
                return None

            # Filter for requested option type (call or put)
            type_filtered = [
                c for c in raw_chain
                if str(c.get("type", "")).lower() == target_type
            ]
            if not type_filtered:
                return None

            # Narrow down to 5 ATM strikes using existing tested OptionsDataFilter
            narrowed = OptionsDataFilter.get_near_the_money_strikes(
                type_filtered, snapshot.event_price, max_strikes=5
            )
            if not narrowed:
                return None

            # Fetch authoritative quotes for these candidate contracts
            contract_symbols = [str(c["symbol"]) for c in narrowed if c.get("symbol")]
            quotes = await self.option_quotes_fetcher(contract_symbols)

            candidates = []
            today = datetime.utcnow().date()

            for c in narrowed:
                sym = str(c["symbol"])
                quote = quotes.get(sym, {})
                bid = float(quote.get("bid", 0.0) or 0.0)
                ask = float(quote.get("ask", 0.0) or 0.0)
                mid = float(quote.get("mid", 0.0) or 0.0)

                # Fallback to close_price if live quote is empty (offline/closed-market safe)
                if mid <= 0 and float(c.get("close_price", 0.0) or 0.0) > 0:
                    mid = float(c["close_price"])
                    bid = mid
                    ask = mid

                if mid <= 0:
                    continue

                # Spread filter: reject contracts where spread > 10%
                spread_pct = ((ask - bid) / mid) if mid > 0 and ask >= bid else 0.0
                if ask > bid and spread_pct > 0.10:
                    continue

                # Capital check: contract premium must not exceed buying power
                contract_cost = ask * 100.0 if ask > 0 else mid * 100.0
                if contract_cost > snapshot.buying_power:
                    continue

                # Calculate DTE
                exp_str = str(c.get("expiration_date", ""))
                try:
                    exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
                    dte = max(0, (exp_date - today).days)
                except Exception:
                    dte = 30

                strike = float(c["strike_price"])
                distance = abs(strike - snapshot.event_price)
                oi = int(c.get("open_interest", 0) or 0)

                candidates.append({
                    "contract_symbol": sym,
                    "underlying_symbol": snapshot.symbol,
                    "strike": strike,
                    "expiry": exp_str[:10],
                    "option_type": target_type,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread_pct": round(spread_pct, 4),
                    "open_interest": oi,
                    "dte": dte,
                    "distance": distance,
                })

            if not candidates:
                return None

            # Sort: closest to ATM, highest OI, tightest spread
            candidates.sort(key=lambda x: (x["distance"], -x["open_interest"], x["spread_pct"]))
            best = candidates[0]
            del best["distance"]
            return best

        except Exception:
            return None

    async def collect(
        self,
        evaluation: HypothesisEvaluation,
        snapshot: ContextSnapshot,
        llm_callable: Optional[Callable[[dict], Awaitable[str]]] = None,
    ) -> EvidenceResult:
        facts = {
            "fresh_symbol_quote": snapshot.event_price if snapshot.data_fresh else None,
            "fresh_market_state": {
                "spy_price": snapshot.spy_price,
                "spy_sma_50": snapshot.spy_sma_50,
                "spy_atr_14": snapshot.spy_atr_14,
            } if snapshot.data_fresh else None,
            "portfolio_exposure": snapshot.held_quantity(),
        }

        # JIT option contract collection when required
        if "jit_option_contract" in evaluation.evidence_requirements:
            option_fact = await self._resolve_option_contract(evaluation, snapshot)
            facts["jit_option_contract"] = option_fact
        missing = [name for name in evaluation.evidence_requirements if facts.get(name) is None]
        if missing:
            return EvidenceResult(
                complete=False,
                data_fresh=snapshot.data_fresh,
                facts={},
                missing=missing,
                reason="Required authoritative evidence is unavailable.",
            )

        if not evaluation.requires_llm_synthesis:
            return EvidenceResult(
                complete=True,
                data_fresh=snapshot.data_fresh,
                facts={name: facts[name] for name in evaluation.evidence_requirements},
                reason="Required authoritative evidence is complete.",
            )

        if llm_callable is None:
            return EvidenceResult(
                complete=False,
                data_fresh=snapshot.data_fresh,
                facts={},
                missing=["qualified_llm_synthesis"],
                reason="LLM synthesis was required but not configured; defaulting safely to no trade.",
            )

        # This compact payload intentionally excludes raw ticks, account secrets,
        # tool names, quantities, and all execution instructions.
        compact_prompt = {
            "symbol": snapshot.symbol,
            "material_change_pct": snapshot.material_change_pct,
            "market_state": facts["fresh_market_state"],
            "held_quantity": facts["portfolio_exposure"],
            "question": "Summarize evidence quality only. Return JSON, never an order or action.",
        }
        llm_result = await self.governance.invoke_json_evidence_safely(llm_callable, compact_prompt)
        if not llm_result:
            return EvidenceResult(
                complete=False,
                data_fresh=snapshot.data_fresh,
                facts={},
                missing=["qualified_llm_synthesis"],
                llm_used=True,
                reason="LLM evidence failed validation or timed out; defaulting safely to no trade.",
            )
        safe_summary = str(llm_result.get("summary", ""))[:300]
        return EvidenceResult(
            complete=True,
            data_fresh=snapshot.data_fresh,
            facts={name: facts[name] for name in evaluation.evidence_requirements} | {"llm_summary": safe_summary},
            llm_used=True,
            reason="Authoritative evidence and bounded LLM synthesis are complete.",
        )
