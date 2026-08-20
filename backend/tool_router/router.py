# backend/tool_router/router.py
from typing import List
import numpy as np

from .schemas import ToolRequest, BindingProof, RouterStatus
from .discovery import tool_registry
from .nlu_semantic import semantic_engine
from .nlu_extractor import asset_extractor
from .schema_form import SchemaForm
from .explicit_validator import explicit_validator

class DynamicRouter:
    async def route_request(self, query: str) -> List[ToolRequest]:
        """ASLI LIVE ROUTER (With 4E Firewall & Safe Argument Checking)"""
        
        # 1. Ensure all AI Models and MCP Tools are loaded
        if not tool_registry.is_loaded: 
            await tool_registry.discover_tools()
        if not semantic_engine.is_loaded: 
            semantic_engine.load()
        if not asset_extractor.is_loaded: 
            asset_extractor.build_index()

        # 2. Entity Extraction (4B)
        entities = asset_extractor.extract(query)
        extracted_args = {}
        for ent in entities:
            if ent.entity_type.value in ["TICKER", "COMPANY_NAME"]:
                extracted_args["symbol"] = ent.value

        # 3. Semantic Ranking (4C) - Find the best tool
        query_emb = semantic_engine.embed(query)
        best_tool = None
        best_score = -1.0

        if tool_registry.capability_documents:
            doc_embs = semantic_engine.embed_batch(tool_registry.capability_documents)
            norms_q = np.linalg.norm(query_emb)
            norms_d = np.linalg.norm(doc_embs, axis=1)
            similarities = np.dot(doc_embs, query_emb) / (norms_d * norms_q + 1e-9)

            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])
            best_tool = tool_registry.tool_names[best_idx]

        if best_score < 0.3 or not best_tool:
            return []

        # 4. Generate Proofs & Fingerprint
        raw_schema = tool_registry.tool_schemas.get(best_tool, {})
        schema_form = SchemaForm(tool_name=best_tool, raw_schema=raw_schema, deployment_identity="local", registry_generation="1")

        # --- THE NEW SAFETY FIX ---
        # Alpaca API aksar "symbols" (plural) maangti hai, jabki hum "symbol" extract karte hain. Safe normalization:
        if "symbols" in raw_schema.get("properties", {}) and "symbol" in extracted_args:
            extracted_args["symbols"] = extracted_args.pop("symbol")
            
        # Agar tool ko zarurat hai, par NLU ne kuch find nahi kiya (e.g. FAKE_COIN)
        required_params = raw_schema.get("required", [])
        if required_params and not extracted_args:
            print(f"⚠️ Router Blocked '{best_tool}': Missing required arguments {required_params}.")
            return [] # Safely skip execution
        # --------------------------

        proofs = []
        for key, val in extracted_args.items():
            proofs.append(BindingProof(json_pointer=f"/properties/{key}", value_provided=val, authority_reference="NLU_EXTRACT"))

        # 5. Build Request
        request = ToolRequest(
            tool_name=best_tool,
            arguments=extracted_args,
            reason=f"Matched via Semantic Engine (Score: {best_score:.2f})",
            fingerprint=schema_form.fingerprint,
            binding_proofs=proofs,
            authorization_reference="USER_INTENT"
        )
        
        # --- 4E FIREWALL VALIDATION ---
        # Ab hum direct pass nahi karenge, pehle 4E Firewall se check karwayenge
        validation_status = explicit_validator.validate_request(request, schema_form)
        if validation_status != RouterStatus.SUCCESS:
            print(f"🛡️ 4E Firewall Blocked Request: {validation_status.value}")
            return []
            
        return [request]

master_router = DynamicRouter()