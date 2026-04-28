"""Integration tests for the ``pptx.compose`` package.

These guard the public surface that Phase 7 promises:
``from_spec`` / ``import_slide`` / ``apply_template`` are all importable
from the same module path.  The implementations themselves are exercised
by their own dedicated test suites; this file just locks in re-exports.
"""

from __future__ import annotations

import pptx.compose as compose


class Describe_compose_package:
    def it_reexports_from_spec(self):
        from pptx.compose.from_spec import from_spec

        assert compose.from_spec is from_spec

    def it_reexports_import_slide(self):
        from pptx._slide_importer import import_slide

        assert compose.import_slide is import_slide

    def it_reexports_apply_template(self):
        from pptx._template_applier import apply_template

        assert compose.apply_template is apply_template

    def it_advertises_all_three_in__all__(self):
        assert set(compose.__all__) == {"from_spec", "import_slide", "apply_template"}

    def it_can_drive_from_spec_end_to_end(self):
        prs = compose.from_spec(
            {
                "slides": [
                    {"layout": "title", "title": "Hello", "subtitle": "World"},
                    {"layout": "bullets", "title": "Bullets", "bullets": ["a", "b"]},
                ]
            }
        )
        assert len(prs.slides) == 2
