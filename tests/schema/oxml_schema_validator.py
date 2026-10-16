"""Compatibility imports for the supported, packaged schema validator."""

from power_pptx._schema import (
    assert_schema_valid,
    iter_schema_violations,
    schema_validation_available,
)

__all__ = ["assert_schema_valid", "iter_schema_violations", "schema_validation_available"]
