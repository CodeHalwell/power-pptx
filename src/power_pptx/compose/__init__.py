"""High-level composition entry points.

This package collects the cross-presentation operations introduced over
Phases 2 and 7: JSON-driven authoring (:func:`from_spec`), styled HTML
section capture (:func:`from_html`), single-slide
import across decks (:func:`import_slide`), and bulk template re-pointing
(:func:`apply_template`).

The implementations live in private submodules (``from_spec`` here, plus
``power_pptx._slide_importer`` and ``power_pptx._template_applier``); this package is
deliberately just a tidy public surface so callers can do::

    from power_pptx.compose import from_spec, import_slide, apply_template

without having to remember three different module paths.

``import_slide`` and ``apply_template`` are the function forms of
``Presentation.import_slide`` and ``Presentation.apply_template`` and
take the destination presentation first::

    import_slide(dst, src.slides[3], merge_master="dedupe")
    apply_template(dst, "brand-template.potx")

They accept the |Presentation| / |Slide| objects themselves or their
underlying ``Part`` objects, and ``apply_template`` takes the template as a
path, a file-like object or an open |Presentation|.
"""

from __future__ import annotations

from power_pptx._slide_importer import import_slide
from power_pptx._template_applier import apply_template
from power_pptx.compose.from_html import from_html
from power_pptx.compose.from_spec import from_spec, from_yaml

__all__ = ["apply_template", "from_html", "from_spec", "from_yaml", "import_slide"]
