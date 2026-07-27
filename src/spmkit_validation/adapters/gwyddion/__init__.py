"""Legacy and headless Gwyddion reference adapters."""

from .format import (
    GwyddionReferenceOutputError,
    deterministic_gwy_bytes,
    strict_json_object,
    validate_reference_output,
)
from .library_runner import (
    GwyddionLibraryExecutionError,
    GwyddionLibraryExecutionResult,
    execute_gwyddion_library_reference,
)

__all__ = [
    "GwyddionReferenceOutputError",
    "GwyddionLibraryExecutionError",
    "GwyddionLibraryExecutionResult",
    "deterministic_gwy_bytes",
    "execute_gwyddion_library_reference",
    "strict_json_object",
    "validate_reference_output",
]
