# backend/tool_router/nlu_extractor.py
import os
import re
import httpx
from typing import List, Set
from flashtext import KeywordProcessor
from .schemas import ExtractedEntity, EntityType

class DynamicAssetExtractor:
    def __init__(self):
        # Dual-Trie architecture based on Aho-Corasick.
        # Complexity: O(L + matches) where L is query length.
        
        # Case-sensitive for tickers (Prevents matching "it" to ticker "IT")
        self.ticker_processor = KeywordProcessor(case_sensitive=True)
        
        # Case-insensitive for company names (Matches "apple", "Apple Inc", etc.)
        self.name_processor = KeywordProcessor(case_sensitive=False)
        
        self.is_loaded = False
        
        # Blacklist of common words that Alpaca registers as company names 
        # which ruin NLU if matched broadly (e.g., "A", "Now", "All")
        self.name_blacklist = {"A", "NOW", "ALL", "IT", "IS", "FOR", "SO", "BE", "CAN", "DO"}

    def build_index(self, api_key: str = None, api_secret: str = None):
        """
        Fetches active US equities from Alpaca and builds the in-memory retrieval Tries.
        Fails loudly if credentials or network fail.
        """
        raw_key = api_key or os.getenv("ALPACA_API_KEY")
        raw_secret = api_secret or os.getenv("ALPACA_SECRET_KEY")
        
        if not raw_key or not raw_secret:
            raise ValueError("Alpaca API credentials missing. Check ALPACA_API_KEY and ALPACA_SECRET_KEY in .env")

        # FIX: Remove any hidden spaces, newlines, or quotes that might come from .env
        key_id = raw_key.strip().strip("'").strip('"')
        secret_key = raw_secret.strip().strip("'").strip('"')

        headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key
        }
        
        # Fetching only active US equities to keep the index relevant and safe
        url = "https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity"
        
        # Use a synchronous client for startup initialization
        with httpx.Client() as client:
            response = client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            assets = response.json()

        # 🚀 NEW: Ignore common trading words that overlap with real company names
        trading_stopwords = {
            "STRATEGY", "POWER", "PORTFOLIO", "ACCOUNT", "STOCK", 
            "SHARE", "SHARES", "PRICE", "BUY", "SELL", "MARKET", "ORDER"
        }

        for asset in assets:
            symbol = asset.get("symbol")
            name = asset.get("name")
            
            if not symbol or not name:
                continue

            # 1. Add Exact Ticker (Case Sensitive) -> AAPL
            self.ticker_processor.add_keyword(symbol, symbol)
            
            # 2. Add Cleaned Company Name (Case Insensitive) -> Apple, Microsoft
            clean_name = self._normalize_company_name(name)
            
            # 🚀 UPDATED: Added trading_stopwords check here!
            if clean_name.upper() not in self.name_blacklist and clean_name.upper() not in trading_stopwords and len(clean_name) > 2:
                self.name_processor.add_keyword(clean_name, symbol)
                
        self.is_loaded = True

    def _normalize_company_name(self, name: str) -> str:
        """
        Standard Symbology Normalizer:
        Removes punctuation, leading articles, web domains, and corporate jargon deterministically.
        """
        # 1. NEW: Safely strip generic web TLDs (.com, .net, .co, etc.) BEFORE punctuation splitting
        clean = re.sub(r'\.(com|net|org|co|us|io)\b', '', name, flags=re.IGNORECASE)
        
        # 2. Fix Regex Trap: Hyphen MUST be at the end of the bracket [,\.\-]
        clean = re.sub(r'[,\.\-]', ' ', clean)
        
        # 3. Truncate at common corporate markers.
        markers = [' inc ', ' corp ', ' corporation ', ' company ', ' co ', ' llc ', ' ltd ', ' plc ']
        clean_padded = ' ' + clean + ' '
        for marker in markers:
            idx = clean_padded.lower().find(marker)
            if idx != -1:
                clean = clean[:idx].strip()
                break
                
        # 4. Strip remaining trailing jargon
        suffixes = r'\b(Holdings|Technologies|Group|Enterprises|Trust|Fund|REIT|Bancorp|Financial|Pharmaceuticals|Therapeutics|Common Stock|Ordinary Shares|Class A|Class B|Class C)\b'
        clean = re.sub(suffixes, '', clean, flags=re.IGNORECASE)
        
        # 5. Strip leading "The "
        clean = re.sub(r'^The\s+', '', clean, flags=re.IGNORECASE)
        
        # 6. Clean up extra spaces
        clean = ' '.join(clean.split())
        return clean
    
    def extract(self, text: str) -> List[ExtractedEntity]:
        """
        Extracts financial entities deterministically from the query.
        Returns empty list if none found.
        """
        if not self.is_loaded:
            raise RuntimeError("Asset index not loaded. Call build_index() first.")

        entities = []
        seen_symbols: Set[str] = set()

        # 1. Extract exact tickers (Case-Sensitive)
        ticker_matches = self.ticker_processor.extract_keywords(text, span_info=True)
        for symbol, start, end in ticker_matches:
            if symbol not in seen_symbols:
                entities.append(ExtractedEntity(
                    entity_type=EntityType.TICKER,
                    value=symbol,
                    raw_text=text[start:end]
                ))
                seen_symbols.add(symbol)

        # 2. Extract company names (Case-Insensitive)
        name_matches = self.name_processor.extract_keywords(text, span_info=True)
        for symbol, start, end in name_matches:
            if symbol not in seen_symbols:
                entities.append(ExtractedEntity(
                    entity_type=EntityType.COMPANY_NAME,
                    value=symbol, # We map the company name directly to its canonical Ticker
                    raw_text=text[start:end]
                ))
                seen_symbols.add(symbol)

        return entities

# Singleton instance ready to be loaded at FastAPI startup
asset_extractor = DynamicAssetExtractor()