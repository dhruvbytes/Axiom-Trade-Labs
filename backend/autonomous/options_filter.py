# backend/autonomous/options_filter.py

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class OptionsDataFilter:
    """
    Enforces the Hackathon MVP rule: Never send massive option chains to the LLM.
    Narrows down any given options chain to a maximum of 5 strikes closest to the money.
    """
    
    @staticmethod
    def get_near_the_money_strikes(
        raw_chain: List[Dict[str, Any]], 
        underlying_price: float, 
        max_strikes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Filters an options chain to return only the 'max_strikes' number of 
        contracts that are closest to the current underlying price.
        """
        if not raw_chain:
            return []
        
        # 1. Ensure each contract is valid and has a strike_price
        valid_chain = []
        for contract in raw_chain:
            try:
                # Alpaca's API might return it as 'strike_price'
                strike = float(contract.get('strike_price', 0))
                if strike > 0:
                    valid_chain.append((strike, contract))
            except (ValueError, TypeError):
                continue
                
        if not valid_chain:
            logger.warning("No valid strike prices found in the options chain.")
            return []

        # 2. Sort by absolute distance to the current underlying price
        sorted_by_distance = sorted(
            valid_chain, 
            key=lambda x: abs(x[0] - underlying_price)
        )
        
        # 3. Take the top N closest strikes
        narrowed_tuples = sorted_by_distance[:max_strikes]
        
        # 4. Re-sort them sequentially by strike price for readable presentation to the LLM
        narrowed_sorted = sorted(narrowed_tuples, key=lambda x: x[0])
        
        logger.info(f"Narrowed options chain from {len(raw_chain)} down to {len(narrowed_sorted)} strictly bounded strikes.")
        
        # Return just the original dictionaries
        return [item[1] for item in narrowed_sorted]