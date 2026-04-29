"""High-level composition entry points.

This package collects the cross-presentation operations introduced over
Phases 2 and 7: JSON-driven authoring (:func:`from_spec`), single-slide
import across decks (:func:`import_slide`), and bulk template re-pointing
(:func:`apply_template`).

The implementations live in private submodules (``from_spec`` here, plus
``power_pptx._slide_importer`` and ``power_pptx._template_applier``); this package is
deliberately just a tidy public surface so callers can do::

    from power_pptx.compose import from_spec, import_slide, apply_template

without having to remember three different module paths.

``Presentation.import_slide`` and ``Presentation.apply_template`` remain
the recommended entry points for those two operations; the function-level
re-exports here are useful when you have raw ``Part`` references or want
to avoid binding the call to a particular ``Presentation`` instance.
"""

from __future__ import annotations

from power_pptx._slide_importer import import_slide
from power_pptx._template_applier import apply_template
from power_pptx.compose.from_spec import from_spec, from_yaml

__all__ = ["apply_template", "from_spec", "from_yaml", "import_slide"]
