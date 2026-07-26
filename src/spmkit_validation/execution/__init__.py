"""Public black-box API for PHASE_01C synthetic campaign execution."""

from .ground_truth import analytical_roughness, discrete_roughness
from .issues import CampaignExecutionError, CampaignExecutionIssue
from .runner import CampaignExecutionResult, execute_frozen_campaign
from .synthetic_roughness import (
    CAMPAIGN_ID,
    CASE_SPECS,
    PreparedSyntheticCampaign,
    deterministic_npz_bytes,
    prepare_synthetic_roughness_campaign,
    surface_array,
)
from .tolerance import derive_tolerance_budget

__all__ = [
    "CAMPAIGN_ID",
    "CASE_SPECS",
    "CampaignExecutionError",
    "CampaignExecutionIssue",
    "CampaignExecutionResult",
    "PreparedSyntheticCampaign",
    "analytical_roughness",
    "derive_tolerance_budget",
    "deterministic_npz_bytes",
    "discrete_roughness",
    "execute_frozen_campaign",
    "prepare_synthetic_roughness_campaign",
    "surface_array",
]
