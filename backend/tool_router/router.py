# backend/tool_router/router.py
from typing import List
import numpy as np
import re
from .schemas import ToolRequest, BindingProof, RouterStatus
from .discovery import tool_registry
from .nlu_semantic import semantic_engine
from .nlu_extractor import asset_extractor
from .schema_form import SchemaForm
from .explicit_validator import explicit_validator


class DynamicRouter:
    async def route_request(self, query: str) -> List[ToolRequest]:
        """ASLI LIVE ROUTER (With 4E Firewall & Multi-Query Fan-Out)"""
        
        # 1. Ensure all AI Models and MCP Tools are loaded
        if not tool_registry.is_loaded: 
            await tool_registry.discover_tools()
        if not semantic_engine.is_loaded: 
            semantic_engine.load()
        if not asset_extractor.is_loaded: 
            asset_extractor.build_index()

        # 2. Entity Extraction (4B) & Multi-Entity Prep
        entities = asset_extractor.extract(query)
        
        # Preserve extraction order and remove duplicates safely
        extracted_symbols = list(dict.fromkeys(
            [ent.value for ent in entities if ent.entity_type.value in ["TICKER", "COMPANY_NAME"]]
        ))

        # 3. Semantic Ranking (4C) - Find the best tool
        query_emb = semantic_engine.embed(query)
        best_tool = None
        best_score = -1.0

        if tool_registry.capability_documents:
            doc_embs = semantic_engine.embed_batch(tool_registry.capability_documents)
            norms_q = np.linalg.norm(query_emb)
            norms_d = np.linalg.norm(doc_embs, axis=1)
            similarities = np.dot(doc_embs, query_emb) / (norms_d * norms_q + 1e-9)

            # 🛡️ GUARD 1: If the query does not mention options, penalize option tools
            option_keywords = ["option", "contract", "call", "put", "spread", "straddle"]
            if not any(k in query.lower() for k in option_keywords):
                for idx, t_name in enumerate(tool_registry.tool_names):
                    if "option" in t_name.lower():
                       similarities[idx] = -1.0  # Eliminate it from competition
                       
            # 🛡️ GUARD 2: If the query does not mention crypto, penalize crypto tools
            crypto_keywords = ["crypto", "coin", "bitcoin", "btc", "eth"]
            if not any(k in query.lower() for k in crypto_keywords):
                for idx, t_name in enumerate(tool_registry.tool_names):
                    if "crypto" in t_name.lower():
                       similarities[idx] = -1.0  # Eliminate crypto from competition

            # 🛡️ GUARD 3: Disambiguate Options Lifecycle (Open vs Close/Exercise)
            query_lower = query.lower()
            
            # 1. Protect Management Tools: If user wants to close or exercise, DO NOT boost.
            if any(w in query_lower for w in ["close", "liquidate", "exercise"]):
                pass # Native Semantic AI will perfectly route to close_position or exercise_options_position
                
            # 2. Boost Order Tool ONLY for Complex Spreads or Explicit Opens
            elif any(w in query_lower for w in ["spread", "straddle", "open a", "open an"]) or \
                 ("buy" in query_lower and "sell" in query_lower and ("call" in query_lower or "put" in query_lower)):
                for idx, t_name in enumerate(tool_registry.tool_names):
                    if t_name == "place_option_order":
                        similarities[idx] += 1.0  # Safely nudge ONLY when we are sure it's a new complex order

            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])
            best_tool = tool_registry.tool_names[best_idx]
            
            # 🚀 NEW: Add this line to see what the AI is thinking!
            print(f"🧠 [DEBUG] Top Tool: {best_tool} | Score: {best_score:.3f}")

        if best_score < 0.25 or not best_tool:
            return []

        # 4. Generate Proofs & Fingerprint
        raw_schema = tool_registry.tool_schemas.get(best_tool, {})
        schema_form = SchemaForm(tool_name=best_tool, raw_schema=raw_schema, deployment_identity="local", registry_generation="1")

        final_requests = []
        
        # FAN-OUT LOGIC: If multiple symbols exist, create a request for each. 
        # If no symbols exist (e.g., get_account_info), run once with None.
        run_targets = extracted_symbols if extracted_symbols else [None]

        for target_symbol in run_targets:
            extracted_args = {}
            if target_symbol is not None:
                extracted_args["symbol"] = target_symbol

            # Alpaca safe normalization
            if "symbols" in raw_schema.get("properties", {}) and "symbol" in extracted_args:
                extracted_args["symbols"] = extracted_args.pop("symbol")
                
            # 🚀 SCALABLE FIX: Handle 'close_position' mapping for ALL asset classes
            if "symbol_or_asset_id" in raw_schema.get("properties", {}) and "symbol" in extracted_args:
                extracted_args["symbol_or_asset_id"] = extracted_args.pop("symbol")
                
                
            ''' Replaces brittle regex. Maps the closest quantity to the specific ticker being processed.
             🚀 INDUSTRY-STANDARD NLU: PROXIMITY, MULTI-LEG & OCC GENERATOR'''     
            if best_tool == "close_position" or best_tool.startswith("place_"):
                lower_q = query.lower()
                
                # 1. Determine Master Side (Fallback Anchor)
                if "buy" in lower_q:
                    extracted_args["side"] = "buy"
                elif "sell" in lower_q or "close" in lower_q or "liquidate" in lower_q:
                    extracted_args["side"] = "sell"
                    
                # 2. Extract Master Quantity (Ignoring Strike Prices with $)
                extracted_qty = 1.0
                number_matches = [(float(m.group().replace(',', '')), m.start()) for m in re.finditer(r'(?<!\$)\b\d+(?:,\d{3})*(?:\.\d+)?\b', lower_q)]
                
                if number_matches:
                    if len(number_matches) == 1:
                        extracted_qty = number_matches[0][0]
                    elif target_symbol:
                        target_mentions = [e.raw_text.lower() for e in entities if e.value == target_symbol]
                        min_dist = float('inf')
                        for mention in target_mentions:
                            for sym_match in re.finditer(re.escape(mention), lower_q):
                                sym_pos = sym_match.start()
                                for num_val, num_pos in number_matches:
                                    dist = abs(sym_pos - num_pos)
                                    if dist < min_dist:
                                        min_dist = dist
                                        extracted_qty = num_val

                # 3. Dynamic API Defaults
                if best_tool.startswith("place_"):
                    extracted_args["type"] = "market"
                    if best_tool == "place_crypto_order":
                        extracted_args["time_in_force"] = "gtc"
                    else:
                        extracted_args["time_in_force"] = "day"

                # 🧠 4. THE ALPHA QUANT ENGINE (Multi-Leg Options & OCC Formatting)
                if best_tool == "place_option_order" and target_symbol:
                    # Regex: Finds (buy/sell), Strike Price (130, 130.5), Option Type (call/put)
                    leg_matches = list(re.finditer(r'\b(buy|sell)?\s*(?:(?:1|one|\d+)\s+)?\$?(\d+(?:\.\d+)?)\s*(call|put|c|p)\b', lower_q))
                    
                    if len(leg_matches) >= 2:
                        # 🎯 MULTI-LEG SPREAD DETECTED (Max 4 legs supported by Alpaca)
                        legs = []
                        for m in leg_matches[:4]:
                            leg_side = (m.group(1) or "buy").lower()
                            strike = m.group(2)
                            opt_type = m.group(3)
                            
                            # Generate OCC Symbol: TICKER + YYMMDD + C/P + STRIKE*1000
                            # Defaulting expiration to Sept 18, 2026 (260918) for Hackathon simulation
                            strike_int = str(int(float(strike) * 1000)).zfill(8)
                            opt_char = "C" if opt_type.startswith("c") else "P"
                            occ_symbol = f"{target_symbol.upper()}260918{opt_char}{strike_int}"
                            
                            legs.append({
                                "symbol": occ_symbol,
                                "ratio_qty": "1",  # Base ratio per leg
                                "side": leg_side
                            })
                        
                        # Apply strict Multi-Leg Schema rules (Remove parent side/symbol)
                        extracted_args["legs"] = legs
                        extracted_args.pop("side", None)
                        # RISK ENGINE FIX: Assign first leg's OCC symbol to root so Risk Engine can parse
                        extracted_args["symbol"] = legs[0]["symbol"]
                        
                        # Set root quantity as strategy multiplier
                        extracted_args["qty"] = str(int(float(extracted_qty)))
                        
                    elif len(leg_matches) == 1:
                        # 🎯 SINGLE LEG OPTION (Standardized OCC)
                        m = leg_matches[0]
                        strike = m.group(2)
                        opt_type = m.group(3)
                        strike_int = str(int(float(strike) * 1000)).zfill(8)
                        opt_char = "C" if opt_type.startswith("c") else "P"
                        
                        extracted_args["symbol"] = f"{target_symbol.upper()}260918{opt_char}{strike_int}"
                        extracted_args["qty"] = str(int(float(extracted_qty)))
                        if m.group(1):
                            extracted_args["side"] = m.group(1).lower()
                            
                # 5. Fallback Quantity Formatting for Standard Stocks/Crypto
                if "qty" not in extracted_args:
                    if best_tool == "close_position":
                        extracted_args["qty"] = float(extracted_qty)
                    else:
                        extracted_args["qty"] = f"{extracted_qty:g}"
                    

            # Check required parameters for THIS specific target
            required_params = raw_schema.get("required", [])
            if required_params and not extracted_args:
                print(f"⚠️ Router Blocked '{best_tool}' for '{target_symbol}': Missing args.")
                continue # Safely skip this iteration without failing the whole batch

            # Generate strict binding proofs
            proofs = []
            for key, val in extracted_args.items():
                proofs.append(BindingProof(json_pointer=f"/properties/{key}", value_provided=val, authority_reference="NLU_EXTRACT"))

            # 5. Build Individual Request
            request = ToolRequest(
                tool_name=best_tool,
                arguments=extracted_args,
                reason=f"Matched via Semantic Engine (Score: {best_score:.2f})",
                fingerprint=schema_form.fingerprint,
                binding_proofs=proofs,
                authorization_reference="USER_INTENT"
            )
            
            # --- 4E FIREWALL VALIDATION PER TARGET ---
            validation_status = explicit_validator.validate_request(request, schema_form)
            if validation_status != RouterStatus.SUCCESS:
                print(f"🛡️ 4E Firewall Blocked Request for '{target_symbol}': {validation_status.value}")
                continue
                
            final_requests.append(request)
            
        return final_requests

master_router = DynamicRouter()