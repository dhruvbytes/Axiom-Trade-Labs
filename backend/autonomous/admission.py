# backend/autonomous/admission.py

import logging
from typing import Dict, Any, Optional
from backend.autonomous.models import ProposalPriority
from backend.autonomous.nmli_validator import AutonomousNMLIValidator

logger = logging.getLogger(__name__)

class UnifiedProposal:
    """
    The converged, uniform representation of a trading proposal.
    Ready to be queued into the Per-Account Priority Scheduler.
    """
    def __init__(self, raw_dict: Dict[str, Any], source: str, priority: ProposalPriority):
        self.data = raw_dict
        self.source = source
        self.priority = priority
        # Defaulting to single account for laptop MVP
        self.account_id = "default_account" 

class SharedAdmissionBoundary:
    """
    The logical convergence point for Human and Autonomous proposals.
    Assigns strict priority tags and formats them uniformly.
    """
    
    @staticmethod
    def submit_human_proposal(
        validated_human_data: Dict[str, Any], 
        is_risk_reduction: bool = False
    ) -> Optional[UnifiedProposal]:
        """Entry point for Human proposals (already validated upstream by SCSV)."""
        if not validated_human_data:
            return None
            
        # P2 for Close/Reduce, P4 for New Risk
        priority = ProposalPriority.P2_HUMAN_EXIT if is_risk_reduction else ProposalPriority.P4_HUMAN_NEW_RISK
        
        return UnifiedProposal(
            raw_dict=validated_human_data,
            source="HUMAN_SCSV",
            priority=priority
        )

    @staticmethod
    def submit_autonomous_proposal(
        raw_autonomous_data: Dict[str, Any], 
        is_risk_reduction: bool = False
    ) -> Optional[UnifiedProposal]:
        """Entry point for Autonomous proposals (validates structure here)."""
        # 1. Structural Validation (Strictly bypasses NLP router)
        validated_data = AutonomousNMLIValidator.validate(raw_autonomous_data)
        if not validated_data:
            logger.error("Admission blocked: Autonomous proposal failed structural validation.")
            return None
            
        # P3 for Auto Stop-loss/Close, P5 for Auto New Strategy
        priority = ProposalPriority.P3_AUTO_RISK_REDUCTION if is_risk_reduction else ProposalPriority.P5_AUTO_OPPORTUNITY
        
        return UnifiedProposal(
            raw_dict=validated_data,
            source="AUTONOMOUS_TRIGGER",
            priority=priority
        )