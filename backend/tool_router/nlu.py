# backend/tool_router/nlu.py
import string
from rank_bm25 import BM25Okapi

class IntentClassifier:
    def __init__(self):
        # Yeh humara 'training data' hai (bina kisi AI ke).
        # Humne algorithm ko bata diya ki kis intent ka kya matlab hota hai.
        self.intents = {
            "ACCOUNT_STATE": [
                "buying power", "balance", "how much cash", "portfolio", 
                "positions", "equity", "afford", "can i buy", "my account"
            ],
            "MARKET_DATA": [
                "price", "quote", "trading at", "how much is", "current value", 
                "market price", "cost"
            ],
            "NEWS": [
                "news", "happening", "headlines", "latest on", "articles", "why is it moving"
            ],
            "HISTORICAL_DATA": [
                "trend", "historical", "past week", "last month", "chart", "history"
            ]
        }
        
        self.corpus = []
        self.intent_labels = []
        
        # Dataset ko BM25 ke samajhne layag banate hain
        for intent, phrases in self.intents.items():
            for phrase in phrases:
                tokens = self._tokenize(phrase)
                self.corpus.append(tokens)
                self.intent_labels.append(intent)
                
        # Engine Start!
        self.bm25 = BM25Okapi(self.corpus)

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer: Sabko lowercase karta hai aur symbols (.?!) hata deta hai"""
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        return text.split()

    def classify(self, query: str) -> tuple[str, float]:
        """Returns a tuple of (Detected_Intent, Score)"""
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        best_score = max(scores) if len(scores) > 0 else 0.0
        
        # Agar koi bhi word match nahi kiya (score 0), toh matlab out-of-context baat hai
        if best_score <= 0.0:
            return "UNKNOWN", 0.0
            
        best_idx = scores.tolist().index(best_score)
        return self.intent_labels[best_idx], round(best_score, 2)

# Global instance
classifier = IntentClassifier()