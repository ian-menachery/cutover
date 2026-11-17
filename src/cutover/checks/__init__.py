"""The check registry. Every check reads a Migration and returns findings; no I/O."""

from . import (
    r1_record_counts,
    r2_key_integrity,
    r3_source_orphans,
    r4_target_orphans,
    r5_control_totals,
    r6_field_diffs,
    r7_unmapped_values,
    r8_referential_integrity,
)
from .base import Check

CHECKS: list[Check] = [
    r1_record_counts.CHECK,
    r2_key_integrity.CHECK,
    r3_source_orphans.CHECK,
    r4_target_orphans.CHECK,
    r5_control_totals.CHECK,
    r6_field_diffs.CHECK,
    r7_unmapped_values.CHECK,
    r8_referential_integrity.CHECK,
]

__all__ = ["CHECKS", "Check"]
