"""Round-trip tests for the slide-show settings (`prs.slide_show`).

`ppt/presProps.xml` used to pass through a load/save cycle as opaque bytes; it
is now parsed, so these guard both the new XML (`p:showPr`) and the content
PowerPoint keeps in the same part against being lost or reordered by
save → open → save.
"""

from __future__ import annotations

import io

import pytest

from power_pptx import Presentation
from power_pptx.enum.slide_show import PP_SLIDE_SHOW_TYPE

from ..unitutil.presprops import (
    POWERPOINT_PRESPROPS_XML,
    PRESPROPS,
    canonical,
    part_bytes,
    part_names,
    saved,
    with_presprops,
    without_presprops,
)
from .round_trip import assert_round_trip, round_trip_diff

_SETTINGS = [
    {"loop": True},
    {"show_type": PP_SLIDE_SHOW_TYPE.KIOSK},
    {"show_type": PP_SLIDE_SHOW_TYPE.WINDOW},
    {"use_timings": False},
    {"show_narration": False},
    {"show_animation": False},
    {
        "loop": True,
        "show_type": PP_SLIDE_SHOW_TYPE.KIOSK,
        "use_timings": False,
        "show_narration": False,
        "show_animation": False,
    },
]
_IDS = ["loop", "kiosk", "window", "use_timings", "show_narration", "show_animation", "all"]


def _default_deck():
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    return prs


def _bare_deck():
    return Presentation(io.BytesIO(without_presprops()))


def _powerpoint_deck():
    return Presentation(io.BytesIO(with_presprops(POWERPOINT_PRESPROPS_XML)))


def _apply(prs, settings):
    for name, value in settings.items():
        setattr(prs.slide_show, name, value)
    return prs


class DescribeSlideShowSettingsRoundTrip:
    @pytest.mark.parametrize("settings", _SETTINGS, ids=_IDS)
    def it_round_trips_each_setting(self, settings):
        assert_round_trip(_apply(_default_deck(), settings))

    @pytest.mark.parametrize("settings", _SETTINGS, ids=_IDS)
    def it_round_trips_a_presProps_part_it_created(self, settings):
        prs = _apply(_bare_deck(), settings)
        assert PRESPROPS in part_names(saved(prs))
        assert_round_trip(prs)

    @pytest.mark.parametrize("settings", _SETTINGS, ids=_IDS)
    def it_round_trips_changes_to_a_show_PowerPoint_set_up(self, settings):
        assert_round_trip(_apply(_powerpoint_deck(), settings))

    @pytest.mark.parametrize("settings", _SETTINGS, ids=_IDS)
    def it_keeps_the_settings_through_the_round_trip(self, settings):
        prs = _apply(_default_deck(), settings)

        twice = Presentation(io.BytesIO(saved(Presentation(io.BytesIO(saved(prs))))))

        for name, value in settings.items():
            assert getattr(twice.slide_show, name) == value, name

    def it_round_trips_a_deck_put_back_to_its_defaults(self):
        prs = _apply(_default_deck(), _SETTINGS[-1])
        _apply(
            prs,
            {
                "loop": False,
                "show_type": "speaker",
                "use_timings": True,
                "show_narration": True,
                "show_animation": True,
            },
        )
        assert_round_trip(prs)


class DescribeUntouchedPresPropsRoundTrip:
    """Parsing the part must not change what a deck nobody edited is saved with."""

    def it_saves_a_PowerPoint_presProps_as_it_was_loaded(self):
        prs = _powerpoint_deck()

        assert canonical(part_bytes(saved(prs), PRESPROPS)) == canonical(POWERPOINT_PRESPROPS_XML)
        assert round_trip_diff(prs) == {}

    def it_saves_the_default_template_presProps_as_it_was_loaded(self):
        import zipfile
        from pathlib import Path

        import power_pptx

        template = Path(power_pptx.__file__).parent / "templates" / "default.pptx"
        with zipfile.ZipFile(template) as zf:
            original = zf.read(PRESPROPS)

        prs = Presentation()

        assert canonical(part_bytes(saved(prs), PRESPROPS)) == canonical(original)
        assert round_trip_diff(prs) == {}

    def it_does_not_alter_a_deck_after_the_settings_are_read(self):
        for factory in (_default_deck, _bare_deck, _powerpoint_deck):
            prs = factory()
            before = saved(prs)

            show = prs.slide_show
            _ = (show.loop, show.show_type, show.use_timings)
            _ = (show.show_narration, show.show_animation, repr(show))

            after = saved(prs)
            assert sorted(part_names(after)) == sorted(part_names(before))
            for name in part_names(before):
                assert part_bytes(after, name) == part_bytes(before, name), name
            assert round_trip_diff(prs) == {}
