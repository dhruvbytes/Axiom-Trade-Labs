# backend/tool_router/extractor.py
import json
import os
from flashtext import KeywordProcessor
from .schemas import ExtractedEntity, EntityType

class EntityExtractor:
    def __init__(self):
        # KeywordProcessor O(N) time me text scan karta hai, regex se bohot fast aur safe hai
        self.processor = KeywordProcessor(case_sensitive=False)
        self._load_dictionary()

    def _load_dictionary(self):
        """Loads the Symbology Master (Ticker Dictionary)"""
        current_dir = os.path.dirname(__file__)
        dict_path = os.path.join(current_dir, "ticker_dict.json")
        
        try:
            with open(dict_path, "r") as f:
                ticker_dict = json.load(f)
                
            # FlashText ko batate hain ki "Apple" mile toh "AAPL" nikalna
            for company_name, ticker in ticker_dict.items():
                self.processor.add_keyword(company_name, ticker)
        except Exception as e:
            print(f"⚠️ Warning: Could not load ticker_dict.json - {e}")

    def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """
        Scans the text and returns a list of ExtractedEntity objects.
        """
        # extract_keywords returns matched values along with their positions
        found_keywords = self.processor.extract_keywords(text, span_info=True)
        
        entities = []
        # Duplicate tickers avoid karne ke liye (e.g., if user says "Apple (AAPL)")
        seen_tickers = set()
        
        for matched_value, start_idx, end_idx in found_keywords:
            if matched_value not in seen_tickers:
                raw_word = text[start_idx:end_idx]
                entity = ExtractedEntity(
                    entity_type=EntityType.TICKER,
                    value=matched_value,     # Yeh hamesha standard ticker hoga (e.g., AAPL)
                    raw_text=raw_word        # User ne jo exact word type kiya (e.g., Apple)
                )
                entities.append(entity)
                seen_tickers.add(matched_value)
                
        return entities

# Global instance taaki har request par JSON dobara load na karna pade
extractor = EntityExtractor()