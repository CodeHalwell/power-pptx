"""Design-system helpers layered on top of the low-level python-pptx API.

These modules are additive; they never replace the underlying shape/slide
APIs and never invent OOXML semantics. They exist so callers don't have to
hand-compute EMU geometry for common layouts.
"""

from __future__ import annotations
