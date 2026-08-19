# backend/tool_router/nlu_semantic.py
import os
# Force disable the windows symlinks tracking system warning gracefully
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
from typing import List

class SemanticEngine:
    def __init__(self, model_id: str = "Xenova/all-MiniLM-L6-v2"):
        """
        Initializes the lightweight ONNX-based semantic embedding engine.
        Using Xenova's repo because it hosts pre-exported ONNX weights.
        """
        self.model_id = model_id
        self.tokenizer = None
        self.session = None
        self.is_loaded = False

    def load(self):
        """Downloads (if not cached) and loads the tokenizer and ONNX model."""
        if self.is_loaded:
            return
            
        print(f"Loading Semantic Engine ({self.model_id})...")
        
        # Proper tokenizer to handle lowercasing correctly
        self.tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

        # Force using the quantized model to respect the 25MB RAM limit
        model_path = hf_hub_download(repo_id=self.model_id, filename="onnx/model_quantized.onnx")
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        
        self.is_loaded = True

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Converts a list of strings into a NumPy matrix of semantic vectors."""
        if not self.is_loaded or self.tokenizer is None or self.session is None:
            raise RuntimeError("Semantic model not loaded. Call load() first.")

        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="np",
        )

        graph_inputs = {item.name for item in self.session.get_inputs()}
        required_inputs = {"input_ids", "attention_mask"}

        missing_inputs = required_inputs - graph_inputs
        if missing_inputs:
            raise RuntimeError(
                f"Unexpected ONNX graph: missing required inputs {sorted(missing_inputs)}"
            )

        onnx_inputs = {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
        }

        if "token_type_ids" in graph_inputs:
            onnx_inputs["token_type_ids"] = encoded.get(
                "token_type_ids",
                np.zeros_like(encoded["input_ids"]),
            ).astype(np.int64)

        output_names = {item.name for item in self.session.get_outputs()}
        if "last_hidden_state" not in output_names:
            raise RuntimeError(
                "Unexpected ONNX graph: expected 'last_hidden_state', "
                f"found {sorted(output_names)}"
            )

        last_hidden_state = self.session.run(
            ["last_hidden_state"],
            onnx_inputs,
        )[0]

        if last_hidden_state.ndim != 3 or last_hidden_state.shape[-1] != 384:
            raise RuntimeError(
                "Unexpected embedding tensor shape: "
                f"{last_hidden_state.shape}; expected [batch, sequence, 384]."
            )

        attention_mask = encoded["attention_mask"].astype(np.float32)
        expanded_mask = attention_mask[:, :, np.newaxis]

        pooled = np.sum(
            last_hidden_state.astype(np.float32) * expanded_mask,
            axis=1,
        ) / np.clip(
            np.sum(expanded_mask, axis=1),
            a_min=1e-9,
            a_max=None,
        )

        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        embeddings = pooled / np.clip(norms, a_min=1e-12, a_max=None)

        if not np.isfinite(embeddings).all():
            raise RuntimeError("Semantic embedding contained NaN or infinity.")

        return embeddings.astype(np.float32, copy=False)

    def embed(self, text: str) -> np.ndarray:
        """Convenience method for a single string with safety checking."""
        if not text or not text.strip():
            return np.zeros(384, dtype=np.float32)
            
        embeddings = self.embed_batch([text])
        return embeddings[0] if embeddings.size > 0 else np.zeros(384, dtype=np.float32)

# Singleton instance for the router
semantic_engine = SemanticEngine()