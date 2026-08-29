# backend/tool_router/explicit_validator.py

import jsonschema
from jsonschema import Draft202012Validator
from .schemas import ToolRequest, RouterStatus
from .schema_form import SchemaForm

class ExplicitValidator:
    """
    The Deterministic Firewall (Step 4E).
    Enforces Explicit Authority, Binding Proofs, Fingerprint matching, and strict JSON Schema validation.
    Zero semantic guessing is allowed here.
    """
    
    @staticmethod
    def validate_request(request: ToolRequest, schema_form: SchemaForm) -> RouterStatus:
        # 1. Fingerprint & Integrity Check
        if not request.fingerprint or request.fingerprint.schema_hash != schema_form.schema_hash:
            return RouterStatus.REJECTED_FINGERPRINT_MISMATCH
        
        # 2. Check Explicit Authority for Execution (Blocks unauthorized 0-parameter tools)
        if not request.authorization_reference:
            return RouterStatus.NEEDS_CAPABILITY_AUTHORITY

        # 3. BindingProof Verification (Every field MUST have exactly one proof)
        provided_keys = list(request.arguments.keys())
        
        # Ensure we have exactly 1 proof per argument key (No guessed parameters allowed)
        if len(request.binding_proofs) != len(provided_keys):
            return RouterStatus.NEEDS_CAPABILITY_AUTHORITY
            
        provided_proofs = {proof.json_pointer: proof for proof in request.binding_proofs}
        
        for key in provided_keys:
            # We enforce standard JSON pointers for properties
            expected_pointer = f"/properties/{key}"
            
            if expected_pointer not in provided_proofs:
                # Missing explicit authority for this specific field
                return RouterStatus.NEEDS_CAPABILITY_AUTHORITY
                
            # Verify the value in the proof exactly matches the argument payload
            if provided_proofs[expected_pointer].value_provided != request.arguments[key]:
                return RouterStatus.REJECTED_SCHEMA_MISMATCH

        # 4. Strict JSON Schema Validation
        try:
            # Ensure the raw MCP schema itself is a valid Draft 2020-12 schema
            Draft202012Validator.check_schema(schema_form.raw_schema) 
            
            # Validate the explicitly proven arguments against the schema
            validator = Draft202012Validator(schema_form.raw_schema)
            validator.validate(instance=request.arguments)
            
        except jsonschema.exceptions.ValidationError as e:
            # 🚀 HACKATHON DEBUG: Print the exact reason the firewall blocked it
            print(f"\n🔥 [FIREWALL ALERT] Schema Violation Detected!")
            print(f"❌ Failed Field: {e.json_path}")
            print(f"❌ Reason: {e.message}\n")
            return RouterStatus.REJECTED_SCHEMA_MISMATCH
        except jsonschema.exceptions.SchemaError:
            # The MCP schema uses unsupported constraints/recursion
            return RouterStatus.REJECTED_UNSUPPORTED_SCHEMA
            
        # If and only if all proofs, hashes, and schemas perfectly align:
        return RouterStatus.SUCCESS

# Singleton instance
explicit_validator = ExplicitValidator()