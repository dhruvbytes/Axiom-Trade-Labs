# test_phase4_critical.py

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.tool_router.schemas import (
    ToolRequest, RouterStatus, BindingProof
)
from backend.tool_router.schema_form import SchemaForm
from backend.tool_router.explicit_validator import explicit_validator

def run_tests():
    print("🚀 Running Phase 4: CRITICAL STRESS TEST for Step 4E...\n")
    
    # --- COMPLEX FINANCIAL MOCK SCHEMA ---
    # Requires an asset, a quantity, and strictly limits allowed assets (Enum)
    # Does NOT allow additional random properties.
    raw_schema = {
        "type": "object",
        "properties": {
            "asset": {"type": "string", "enum": ["AAPL", "NVDA", "MSFT"]},
            "quantity": {"type": "integer", "minimum": 1},
            "options": {
                "type": "object",
                "properties": {"use_margin": {"type": "boolean"}}
            }
        },
        "required": ["asset", "quantity"],
        "additionalProperties": False
    }
    schema_form = SchemaForm("complex_trade_tool", raw_schema, "deploy-local", "gen-1")
    fingerprint = schema_form.fingerprint

    # 1. CRITICAL TEST: The "Tampered Payload" (Proof mismatch)
    # Proof says AAPL, but payload tries to sneak in TSLA.
    proof_asset = BindingProof(json_pointer="/properties/asset", value_provided="AAPL", authority_reference="AUTH-1")
    proof_qty = BindingProof(json_pointer="/properties/quantity", value_provided=10, authority_reference="AUTH-1")
    
    req_tampered = ToolRequest(
        tool_name="complex_trade_tool",
        arguments={"asset": "TSLA", "quantity": 10}, # Payload says TSLA!
        reason="Tamper test",
        fingerprint=fingerprint,
        binding_proofs=[proof_asset, proof_qty],
        authorization_reference="AUTH-1"
    )
    status_tampered = explicit_validator.validate_request(req_tampered, schema_form)
    assert status_tampered == RouterStatus.REJECTED_SCHEMA_MISMATCH
    print("✅ CRITICAL PASSED: Payload Tampering (Proof vs Argument mismatch) is instantly REJECTED.")

    # 2. CRITICAL TEST: Missing Required Field
    # Only providing quantity, missing the required 'asset'
    req_missing = ToolRequest(
        tool_name="complex_trade_tool",
        arguments={"quantity": 10},
        reason="Missing test",
        fingerprint=fingerprint,
        binding_proofs=[proof_qty], # Only proof for qty
        authorization_reference="AUTH-1"
    )
    status_missing = explicit_validator.validate_request(req_missing, schema_form)
    assert status_missing == RouterStatus.REJECTED_SCHEMA_MISMATCH
    print("✅ CRITICAL PASSED: Missing 'required' JSON Schema fields is REJECTED.")

    # 3. CRITICAL TEST: Enum Violation
    # Trying to authorize an asset not in the allowed Enum
    proof_bad_enum = BindingProof(json_pointer="/properties/asset", value_provided="GME", authority_reference="AUTH-1")
    req_enum = ToolRequest(
        tool_name="complex_trade_tool",
        arguments={"asset": "GME", "quantity": 10},
        reason="Enum test",
        fingerprint=fingerprint,
        binding_proofs=[proof_bad_enum, proof_qty],
        authorization_reference="AUTH-1"
    )
    status_enum = explicit_validator.validate_request(req_enum, schema_form)
    assert status_enum == RouterStatus.REJECTED_SCHEMA_MISMATCH
    print("✅ CRITICAL PASSED: Enum Violation (Unauthorized value in JSON Schema) is REJECTED.")

    # 4. CRITICAL TEST: Sneaking in Extra Arguments (Prompt Injection logic bypass)
    # Adding {"is_admin": true} when it's not in the schema.
    proof_admin = BindingProof(json_pointer="/properties/is_admin", value_provided=True, authority_reference="AUTH-1")
    req_injection = ToolRequest(
        tool_name="complex_trade_tool",
        arguments={"asset": "AAPL", "quantity": 10, "is_admin": True},
        reason="Injection test",
        fingerprint=fingerprint,
        binding_proofs=[proof_asset, proof_qty, proof_admin],
        authorization_reference="AUTH-1"
    )
    status_injection = explicit_validator.validate_request(req_injection, schema_form)
    assert status_injection == RouterStatus.REJECTED_SCHEMA_MISMATCH
    print("✅ CRITICAL PASSED: Prompt Injection (Adding extra undeclared arguments) is REJECTED.")

    # 5. CRITICAL TEST: The Perfect Complex Payload
    proof_option = BindingProof(json_pointer="/properties/options", value_provided={"use_margin": False}, authority_reference="AUTH-1")
    req_perfect = ToolRequest(
        tool_name="complex_trade_tool",
        arguments={"asset": "NVDA", "quantity": 50, "options": {"use_margin": False}},
        reason="Perfect test",
        fingerprint=fingerprint,
        binding_proofs=[
            BindingProof(json_pointer="/properties/asset", value_provided="NVDA", authority_reference="AUTH-1"),
            BindingProof(json_pointer="/properties/quantity", value_provided=50, authority_reference="AUTH-1"),
            proof_option
        ],
        authorization_reference="AUTH-1"
    )
    status_perfect = explicit_validator.validate_request(req_perfect, schema_form)
    assert status_perfect == RouterStatus.SUCCESS
    print("✅ CRITICAL PASSED: Perfectly bound complex nested JSON is SUCCESS.")

    print("\n🎯 PHASE 4 CRITICAL STRESS TEST COMPLETE. Step 4E is officially bulletproof.")

if __name__ == "__main__":
    run_tests()