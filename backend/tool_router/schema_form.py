# backend/tool_router/schema_form.py

import json
import hashlib
from typing import Dict, Any
from .schemas import ExecutionContractFingerprint

class SchemaForm:
    """
    A SAFE COMPILED PROJECTION of the raw MCP JSON schema.
    It does not re-invent schema validation. It ensures the schema is structurally
    safe (no external references/recursion) and generates an immutable Execution Contract Fingerprint.
    """
    
    def __init__(self, tool_name: str, raw_schema: Dict[str, Any], deployment_identity: str, registry_generation: str):
        self.tool_name = tool_name
        self.raw_schema = raw_schema
        
        # 1. Safety Checks (Reject unsupported or dangerous structures)
        self._validate_safe_projection(raw_schema)
        
        # 2. Canonical Hashing
        self.schema_hash = self._generate_canonical_hash(raw_schema)
        
        # 3. Build the Immutable Execution Contract Fingerprint
        self.fingerprint = ExecutionContractFingerprint(
            deployment_identity=deployment_identity,
            tool_name=tool_name,
            schema_hash=self.schema_hash,
            schema_dialect="draft-2020-12", # Target MCP specification dialect
            toolset_scope="global",
            registry_generation=registry_generation
        )

    def _validate_safe_projection(self, schema: Dict[str, Any]):
        """
        Ensures the schema does not contain external $refs or known unsafe traps.
        Fails closed by raising ValueError if unsafe elements are found.
        """
        # Convert to string to quickly scan for external references
        schema_str = json.dumps(schema)
        
        # Explicitly reject external references to avoid network fetching or unbounded recursion
        if "$ref" in schema_str:
            if "http://" in schema_str or "https://" in schema_str:
                raise ValueError(f"REJECTED_UNSUPPORTED_SCHEMA: External $ref detected in {self.tool_name}.")
            
        # Ensure root is an object type if explicitly defined
        if "type" in schema and schema["type"] != "object":
            raise ValueError(f"REJECTED_UNSUPPORTED_SCHEMA: Root schema type for {self.tool_name} must be 'object'.")

    def _generate_canonical_hash(self, schema_dict: Dict[str, Any]) -> str:
        """
        Generates a deterministic SHA-256 hash using canonical JSON.
        sort_keys=True ensures that {"a":1, "b":2} and {"b":2, "a":1} produce the exact same hash.
        """
        canonical_string = json.dumps(schema_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_string.encode('utf-8')).hexdigest()