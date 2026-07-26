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
from .runner import (
    CampaignExecutionResult,
    InstalledSUTEnvironment,
    execute_frozen_campaign,
    install_sut_wheel_environment,
)
from .software_verification import (
    JUnitSummary,
    SoftwareTestExecutionResult,
    execute_software_test,
    parse_junit_xml,
    validate_import_probe,
)
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
    "InstalledSUTEnvironment",
    "JUnitSummary",
    "PreparedSyntheticCampaign",
    "PreparedCumulativeCampaign",
    "SOFTWARE_CASE_ID",
    "SOFTWARE_TEST_RUN_ID",
    "SoftwareTestExecutionResult",
    "analytical_roughness",
    "compare_campaign_repetition",
    "derive_tolerance_budget",
    "deterministic_npz_bytes",
    "discrete_roughness",
    "execute_frozen_campaign",
    "execute_software_test",
    "export_software_test_suite",
    "normalized_scientific_record",
    "install_sut_wheel_environment",
    "parse_junit_xml",
    "populate_result_bundle",
    "prepare_synthetic_roughness_campaign",
    "prepare_cumulative_verification_campaign",
    "surface_array",
    "verify_protocol_continuity",
    "verify_result_snapshot",
    "validate_import_probe",
    "write_execution_receipt",
]
