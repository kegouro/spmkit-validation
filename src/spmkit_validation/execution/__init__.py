"""Public black-box API for PHASE_01C synthetic campaign execution."""

from .continuity import verify_protocol_continuity
from .cumulative_protocol import (
    CUMULATIVE_CAMPAIGN_ID,
    SOFTWARE_CASE_ID,
    SOFTWARE_TEST_RUN_ID,
    PreparedCumulativeCampaign,
    export_software_test_suite,
    prepare_cumulative_verification_campaign,
)
from .ground_truth import analytical_roughness, discrete_roughness
from .issues import CampaignExecutionError, CampaignExecutionIssue
from .population import (
    compare_campaign_repetition,
    normalized_scientific_record,
    populate_result_bundle,
)
from .receipt import ExecutionReceipt, write_execution_receipt
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
from .verification import verify_result_snapshot

__all__ = [
    "CAMPAIGN_ID",
    "CASE_SPECS",
    "CUMULATIVE_CAMPAIGN_ID",
    "CampaignExecutionError",
    "CampaignExecutionIssue",
    "CampaignExecutionResult",
    "ExecutionReceipt",
    "PreparedSyntheticCampaign",
    "PreparedCumulativeCampaign",
    "SOFTWARE_CASE_ID",
    "SOFTWARE_TEST_RUN_ID",
    "analytical_roughness",
    "compare_campaign_repetition",
    "derive_tolerance_budget",
    "deterministic_npz_bytes",
    "discrete_roughness",
    "execute_frozen_campaign",
    "export_software_test_suite",
    "normalized_scientific_record",
    "populate_result_bundle",
    "prepare_synthetic_roughness_campaign",
    "prepare_cumulative_verification_campaign",
    "surface_array",
    "verify_protocol_continuity",
    "verify_result_snapshot",
    "write_execution_receipt",
]
