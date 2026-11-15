# pyright: reportPrivateUsage=false

"""Unit-test suite for `power_pptx.slide_show` module and `Presentation.slide_show`."""

from __future__ import annotations

import io

import pytest
from lxml import etree

import power_pptx
from power_pptx.enum.slide_show import PP_SLIDE_SHOW_TYPE
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.slide_show import SlideShowSettings

from .unitutil.presprops import (
    POWERPOINT_PRESPROPS_XML,
    PRESPROPS,
    blank_deck_bytes,
    canonical,
    part_bytes,
    part_names,
    presprops_root,
    reopened,
    saved,
    with_presprops,
    without_presprops,
)

_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = {"p": _P, "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

SPEAKER = PP_SLIDE_SHOW_TYPE.SPEAKER
WINDOW = PP_SLIDE_SHOW_TYPE.WINDOW
KIOSK = PP_SLIDE_SHOW_TYPE.KIOSK

# -- (property, a value other than the default, the default) --
SETTINGS = [
    ("loop", True, False),
    ("show_type", KIOSK, SPEAKER),
    ("show_type", WINDOW, SPEAKER),
    ("use_timings", False, True),
    ("show_narration", False, True),
    ("show_animation", False, True),
]
SETTING_IDS = ["loop", "kiosk", "window", "use_timings", "show_narration", "show_animation"]


def _open(blob: bytes):
    return power_pptx.Presentation(io.BytesIO(blob))


def _show_pr(prs):
    """Return the `p:showPr` element `prs` would be saved with, or None."""
    found = presprops_root(saved(prs)).findall("p:showPr", _NS)
    assert len(found) <= 1
    return found[0] if found else None


def _presprops(prs) -> bytes:
    """Return the canonical `ppt/presProps.xml` `prs` would be saved with."""
    return canonical(part_bytes(saved(prs), PRESPROPS))


def _settings(prs) -> dict:
    show = prs.slide_show
    return {
        "loop": show.loop,
        "show_type": show.show_type,
        "use_timings": show.use_timings,
        "show_narration": show.show_narration,
        "show_animation": show.show_animation,
    }


DEFAULTS = {
    "loop": False,
    "show_type": SPEAKER,
    "use_timings": True,
    "show_narration": True,
    "show_animation": True,
}


@pytest.fixture
def prs():
    """A deck built on the default template, whose presProps.xml has no `p:showPr`."""
    deck = power_pptx.Presentation()
    deck.slides.add_slide(deck.slide_layouts[6])
    return deck


@pytest.fixture
def bare_prs():
    """A deck from a tool that writes no presentation-properties part."""
    return _open(without_presprops())


@pytest.fixture
def powerpoint_prs():
    """A deck whose looping kiosk show was set up in PowerPoint."""
    return _open(with_presprops(POWERPOINT_PRESPROPS_XML))


class DescribePresentation_slide_show(object):
    """`Presentation.slide_show` is the way in."""

    def it_provides_access_to_its_slide_show_settings(self, prs):
        assert isinstance(prs.slide_show, SlideShowSettings)

    def it_reports_what_PowerPoint_assumes_for_a_deck_that_does_not_say(self, prs):
        assert _settings(prs) == DEFAULTS
        assert all(type(v) is bool for k, v in _settings(prs).items() if k != "show_type")

    def and_for_a_deck_with_no_presProps_part_at_all(self, bare_prs):
        assert _settings(bare_prs) == DEFAULTS

    def it_has_a_repr_that_shows_every_setting(self, prs):
        prs.slide_show.loop = True
        prs.slide_show.show_type = "kiosk"
        assert repr(prs.slide_show) == (
            "<SlideShowSettings loop=True show_type=KIOSK use_timings=True "
            "show_narration=True show_animation=True>"
        )


class DescribeSlideShowSettings_reading(object):
    """Reading must work on PowerPoint's files and must never modify the deck."""

    def it_does_not_modify_a_deck_that_is_only_read(self, prs):
        before = saved(prs)

        _settings(prs)
        repr(prs.slide_show)

        after = saved(prs)
        assert _presprops(prs) == canonical(part_bytes(before, PRESPROPS))
        assert sorted(part_names(after)) == sorted(part_names(before))
        assert _show_pr(prs) is None

    def and_it_does_not_add_the_part_to_a_deck_that_has_none(self, bare_prs):
        _settings(bare_prs)
        repr(bare_prs.slide_show)

        blob = saved(bare_prs)
        assert PRESPROPS not in part_names(blob)
        assert b"presProps" not in part_bytes(blob, "ppt/_rels/presentation.xml.rels")
        assert b"presProps" not in part_bytes(blob, "[Content_Types].xml")

    def and_it_does_not_modify_a_deck_PowerPoint_set_up(self, powerpoint_prs):
        _settings(powerpoint_prs)
        assert _presprops(powerpoint_prs) == canonical(POWERPOINT_PRESPROPS_XML)

    def it_reads_the_settings_PowerPoint_saved(self, powerpoint_prs):
        assert _settings(powerpoint_prs) == {
            "loop": True,
            "show_type": KIOSK,
            "use_timings": True,
            "show_narration": True,
            "show_animation": True,
        }

    @pytest.mark.parametrize(
        ("show_pr", "expected"),
        [
            # -- PowerPoint, "Show without narration" ticked: the attribute is left out --
            ("<p:showPr><p:present/><p:sldAll/></p:showPr>", {"show_narration": False}),
            # -- an empty element is narration off too, by the schema default --
            ("<p:showPr/>", {"show_narration": False}),
            ('<p:showPr showNarration="1"><p:present/></p:showPr>', {}),
            ('<p:showPr showNarration="true" loop="true"/>', {"loop": True}),
            ('<p:showPr showNarration="1" loop="0"/>', {}),
            (
                '<p:showPr showNarration="1" useTimings="0" showAnimation="false"/>',
                {"use_timings": False, "show_animation": False},
            ),
            (
                '<p:showPr showNarration="1"><p:browse showScrollbar="0"/></p:showPr>',
                {"show_type": WINDOW},
            ),
            (
                '<p:showPr showNarration="1"><p:kiosk restart="60000"/></p:showPr>',
                {"show_type": KIOSK},
            ),
            # -- a slide range with no show-type element is still a speaker show --
            ('<p:showPr showNarration="1"><p:sldRg st="2" end="4"/></p:showPr>', {}),
        ],
    )
    def it_reads_each_form_the_element_can_take(self, show_pr: str, expected: dict):
        xml = '<p:presentationPr xmlns:p="%s">%s</p:presentationPr>' % (_P, show_pr)
        prs = _open(with_presprops(xml))

        assert _settings(prs) == dict(DEFAULTS, **expected)
        # -- and reading left it exactly as it was --
        assert _presprops(prs) == canonical(xml)


class DescribeSlideShowSettings_writing(object):
    """Each setting can be changed, and the change is in the saved file."""

    @pytest.mark.parametrize(("name", "value", "_default"), SETTINGS, ids=SETTING_IDS)
    def it_can_change_a_setting(self, prs, name, value, _default):
        setattr(prs.slide_show, name, value)

        assert getattr(prs.slide_show, name) == value
        assert _settings(prs) == dict(DEFAULTS, **{name: value})
        # -- and it survives a save and a fresh load --
        assert _settings(reopened(prs)) == dict(DEFAULTS, **{name: value})

    @pytest.mark.parametrize(
        ("name", "value", "expected_xml"),
        [
            ("loop", True, '<p:showPr xmlns:p="%s" loop="1" showNarration="1"/>'),
            ("use_timings", False, '<p:showPr xmlns:p="%s" useTimings="0" showNarration="1"/>'),
            (
                "show_animation",
                False,
                '<p:showPr xmlns:p="%s" showAnimation="0" showNarration="1"/>',
            ),
            ("show_narration", False, '<p:showPr xmlns:p="%s" showNarration="0"/>'),
            (
                "show_type",
                "kiosk",
                '<p:showPr xmlns:p="%s" showNarration="1"><p:kiosk/></p:showPr>',
            ),
            (
                "show_type",
                "window",
                '<p:showPr xmlns:p="%s" showNarration="1"><p:browse/></p:showPr>',
            ),
        ],
        ids=SETTING_IDS,
    )
    def it_writes_the_showPr_element_for_it(self, prs, name, value, expected_xml):
        setattr(prs.slide_show, name, value)

        show_pr = _show_pr(prs)
        assert show_pr is not None
        assert canonical(etree.tostring(show_pr)) == canonical(expected_xml % _P)

    def it_keeps_narration_playing_when_it_adds_the_element(self, prs):
        """A bare `<p:showPr loop="1"/>` would silence narration (schema default: false)."""
        prs.slide_show.loop = True

        assert _show_pr(prs).get("showNarration") == "1"
        assert prs.slide_show.show_narration is True
        assert reopened(prs).slide_show.show_narration is True

    def it_adds_the_element_where_the_schema_wants_it(self, prs):
        # -- the default template's presProps.xml holds only `p:extLst`, which must stay last --
        prs.slide_show.loop = True
        root = presprops_root(saved(prs))
        assert [child.tag.rpartition("}")[2] for child in root] == ["showPr", "extLst"]

    def it_can_change_several_settings_independently(self, prs):
        show = prs.slide_show
        show.loop = True
        show.show_type = "kiosk"
        show.use_timings = False
        show.show_animation = False
        show.show_narration = False

        expected = {
            "loop": True,
            "show_type": KIOSK,
            "use_timings": False,
            "show_narration": False,
            "show_animation": False,
        }
        assert _settings(prs) == expected
        assert _settings(reopened(prs)) == expected

        show.use_timings = True
        assert _settings(prs) == dict(expected, use_timings=True)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (PP_SLIDE_SHOW_TYPE.SPEAKER, SPEAKER),
            (PP_SLIDE_SHOW_TYPE.WINDOW, WINDOW),
            (PP_SLIDE_SHOW_TYPE.KIOSK, KIOSK),
            ("speaker", SPEAKER),
            ("window", WINDOW),
            ("kiosk", KIOSK),
            ("Kiosk", KIOSK),
            (" KIOSK ", KIOSK),
            # -- the element names, so a value read from the XML can be passed back --
            ("present", SPEAKER),
            ("browse", WINDOW),
        ],
    )
    def it_accepts_a_member_or_a_plain_string_for_show_type(self, prs, value, expected):
        # -- start from a different type so that the assignment has to do something --
        prs.slide_show.show_type = WINDOW if expected is not WINDOW else KIOSK

        prs.slide_show.show_type = value

        assert prs.slide_show.show_type is expected
        assert reopened(prs).slide_show.show_type is expected

    @pytest.mark.parametrize("value", ["fullscreen", "", "loop", None, 3, True, 2.0, b"kiosk"])
    def but_it_rejects_anything_else_for_show_type(self, prs, value):
        with pytest.raises(ValueError, match="show_type must be 'speaker', 'window', 'kiosk'"):
            prs.slide_show.show_type = value
        assert _show_pr(prs) is None

    @pytest.mark.parametrize("name", ["loop", "use_timings", "show_narration", "show_animation"])
    @pytest.mark.parametrize("value", ["false", "yes", 1, 0, None, 1.0])
    def it_rejects_a_value_that_is_not_a_bool(self, prs, name, value):
        with pytest.raises(TypeError, match="%s must be True or False" % name):
            setattr(prs.slide_show, name, value)
        assert _show_pr(prs) is None

    def it_can_switch_between_show_types(self, prs):
        show = prs.slide_show
        for value in (KIOSK, WINDOW, KIOSK, SPEAKER, WINDOW):
            show.show_type = value
            assert show.show_type is value
            show_pr = _show_pr(prs)
            children = [] if show_pr is None else [c.tag.rpartition("}")[2] for c in show_pr]
            assert children == ([] if value is SPEAKER else [value.xml_value])


class DescribeSlideShowSettings_tidiness(object):
    """Putting a setting back must not leave anything behind."""

    @pytest.mark.parametrize(("name", "value", "default"), SETTINGS, ids=SETTING_IDS)
    def it_removes_the_element_when_a_setting_goes_back_to_its_default(
        self, prs, name, value, default
    ):
        pristine = _presprops(prs)
        setattr(prs.slide_show, name, value)
        assert _presprops(prs) != pristine

        setattr(prs.slide_show, name, default)

        assert _show_pr(prs) is None
        assert _presprops(prs) == pristine

    def and_only_when_the_last_setting_has_gone_back(self, prs):
        pristine = _presprops(prs)
        show = prs.slide_show
        show.loop = True
        show.show_type = "kiosk"

        show.loop = False
        assert _show_pr(prs) is not None
        assert show.show_type is KIOSK

        show.show_type = "speaker"
        assert _presprops(prs) == pristine

    @pytest.mark.parametrize(("name", "_value", "default"), SETTINGS, ids=SETTING_IDS)
    def it_writes_nothing_when_a_setting_is_assigned_the_value_it_has(
        self, prs, name, _value, default
    ):
        pristine = _presprops(prs)
        setattr(prs.slide_show, name, default)
        assert _presprops(prs) == pristine

    @pytest.mark.parametrize(("name", "value", "default"), SETTINGS, ids=SETTING_IDS)
    def it_removes_a_part_it_added_once_that_is_empty_again(self, bare_prs, name, value, default):
        setattr(bare_prs.slide_show, name, value)
        assert PRESPROPS in part_names(saved(bare_prs))

        setattr(bare_prs.slide_show, name, default)

        blob = saved(bare_prs)
        assert PRESPROPS not in part_names(blob)
        assert b"presProps" not in part_bytes(blob, "ppt/_rels/presentation.xml.rels")
        assert b"presProps" not in part_bytes(blob, "[Content_Types].xml")
        assert sorted(part_names(blob)) == sorted(part_names(without_presprops()))

    @pytest.mark.parametrize(("name", "_value", "default"), SETTINGS, ids=SETTING_IDS)
    def and_it_adds_no_part_for_a_value_the_deck_already_has(self, bare_prs, name, _value, default):
        setattr(bare_prs.slide_show, name, default)
        assert PRESPROPS not in part_names(saved(bare_prs))

    def but_it_keeps_a_part_that_came_with_the_file_even_when_empty(self):
        xml = '<p:presentationPr xmlns:p="%s"/>' % _P
        prs = _open(with_presprops(xml))

        prs.slide_show.loop = True
        prs.slide_show.loop = False

        assert _presprops(prs) == canonical(xml)

    def and_it_keeps_a_part_it_added_after_the_deck_has_been_saved_and_reloaded(self, bare_prs):
        bare_prs.slide_show.loop = True
        prs = reopened(bare_prs)

        prs.slide_show.loop = False

        assert _presprops(prs) == canonical('<p:presentationPr xmlns:p="%s"/>' % _P)

    def it_drops_an_element_that_is_brought_back_to_the_assumed_values(self):
        # -- `<p:showPr/>` means "narration off"; turning it on leaves nothing to say --
        xml = '<p:presentationPr xmlns:p="%s"><p:showPr/><p:extLst/></p:presentationPr>' % _P
        prs = _open(with_presprops(xml))
        assert prs.slide_show.show_narration is False

        prs.slide_show.show_narration = True

        assert prs.slide_show.show_narration is True
        assert _presprops(prs) == canonical(
            '<p:presentationPr xmlns:p="%s"><p:extLst/></p:presentationPr>' % _P
        )


class DescribeSlideShowSettings_on_a_PowerPoint_deck(object):
    """Everything else in presProps.xml must survive untouched."""

    def _others(self, prs) -> dict[str, bytes]:
        """Canonical XML of everything in presProps.xml the API does not own."""
        root = presprops_root(saved(prs))
        paths = {
            "sldAll": "p:showPr/p:sldAll",
            "penClr": "p:showPr/p:penClr",
            "showPr extLst": "p:showPr/p:extLst",
            "clrMru": "p:clrMru",
            "extLst": "p:extLst",
        }
        result = {}
        for label, path in paths.items():
            found = root.findall(path, _NS)
            assert len(found) == 1, label
            result[label] = canonical(etree.tostring(found[0]))
        return result

    def it_changes_only_the_attribute_it_was_asked_to(self, powerpoint_prs):
        others = self._others(powerpoint_prs)

        powerpoint_prs.slide_show.loop = False

        assert _presprops(powerpoint_prs) == canonical(
            POWERPOINT_PRESPROPS_XML.replace('<p:showPr loop="1" ', "<p:showPr ")
        )
        assert self._others(powerpoint_prs) == others
        assert _settings(powerpoint_prs)["show_type"] is KIOSK

    def it_changes_only_the_show_type_element_it_was_asked_to(self, powerpoint_prs):
        powerpoint_prs.slide_show.show_type = "window"

        assert _presprops(powerpoint_prs) == canonical(
            POWERPOINT_PRESPROPS_XML.replace("<p:kiosk/>", "<p:browse/>")
        )

    def it_removes_only_the_show_type_element_for_a_speaker_show(self, powerpoint_prs):
        powerpoint_prs.slide_show.show_type = "speaker"

        assert _presprops(powerpoint_prs) == canonical(
            POWERPOINT_PRESPROPS_XML.replace("<p:kiosk/>", "")
        )
        assert powerpoint_prs.slide_show.show_type is SPEAKER

    def it_keeps_the_children_in_schema_order_whatever_is_changed(self, powerpoint_prs):
        show = powerpoint_prs.slide_show
        show.show_type = "speaker"
        show.show_type = "window"
        show.use_timings = False
        show.show_animation = False

        root = presprops_root(saved(powerpoint_prs))
        assert [c.tag.rpartition("}")[2] for c in root] == ["showPr", "clrMru", "extLst"]
        show_pr = root.find("p:showPr", _NS)
        assert [c.tag.rpartition("}")[2] for c in show_pr] == [
            "browse",
            "sldAll",
            "penClr",
            "extLst",
        ]

    def it_keeps_the_element_when_PowerPoints_own_content_is_still_in_it(self, powerpoint_prs):
        others = self._others(powerpoint_prs)
        show = powerpoint_prs.slide_show

        show.loop = False
        show.show_type = "speaker"

        assert _settings(powerpoint_prs) == DEFAULTS
        assert self._others(powerpoint_prs) == others
        assert dict(_show_pr(powerpoint_prs).attrib) == {"showNarration": "1"}

    def it_survives_every_setting_being_changed_and_changed_back(self, powerpoint_prs):
        show = powerpoint_prs.slide_show
        show.loop = False
        show.show_type = "window"
        show.use_timings = False
        show.show_animation = False
        show.show_narration = False
        prs = reopened(powerpoint_prs)
        show = prs.slide_show
        show.show_narration = True
        show.show_animation = True
        show.use_timings = True
        show.show_type = "kiosk"
        show.loop = True

        assert _presprops(prs) == canonical(POWERPOINT_PRESPROPS_XML)

    def it_does_not_turn_narration_on_in_a_deck_that_had_it_off(self):
        xml = (
            '<p:presentationPr xmlns:p="%s"><p:showPr><p:present/><p:sldAll/></p:showPr>'
            "</p:presentationPr>" % _P
        )
        prs = _open(with_presprops(xml))

        prs.slide_show.loop = True

        assert prs.slide_show.show_narration is False
        assert _presprops(prs) == canonical(xml.replace("<p:showPr>", '<p:showPr loop="1">'))

    def it_leaves_an_explicit_present_element_alone_for_a_speaker_show(self):
        xml = (
            '<p:presentationPr xmlns:p="%s"><p:showPr showNarration="1"><p:present/></p:showPr>'
            "</p:presentationPr>" % _P
        )
        prs = _open(with_presprops(xml))

        prs.slide_show.show_type = "speaker"

        assert _presprops(prs) == canonical(xml)


class DescribeSlideShowSettings_on_a_deck_without_presProps(object):
    """The part and its relationship are created on demand."""

    def it_creates_the_part_the_first_time_a_setting_changes(self, bare_prs):
        bare_prs.slide_show.loop = True

        blob = saved(bare_prs)
        assert PRESPROPS in part_names(blob)
        assert canonical(part_bytes(blob, PRESPROPS)) == canonical(
            '<p:presentationPr xmlns:p="%s"><p:showPr loop="1" showNarration="1"/>'
            "</p:presentationPr>" % _P
        )
        rels = part_bytes(blob, "ppt/_rels/presentation.xml.rels").decode("utf-8")
        assert rels.count('Type="%s" Target="presProps.xml"' % RT.PRES_PROPS) == 1
        assert _settings(_open(blob)) == dict(DEFAULTS, loop=True)

    def it_creates_it_only_once(self, bare_prs):
        show = bare_prs.slide_show
        show.loop = True
        show.show_type = "kiosk"
        bare_prs.slide_show.use_timings = False

        blob = saved(bare_prs)
        assert [n for n in part_names(blob) if "presProps" in n] == [PRESPROPS]
        rels = part_bytes(blob, "ppt/_rels/presentation.xml.rels").decode("utf-8")
        assert rels.count(RT.PRES_PROPS) == 1
        assert _settings(_open(blob)) == dict(
            DEFAULTS, loop=True, show_type=KIOSK, use_timings=False
        )

    def it_leaves_the_rest_of_the_package_alone(self, bare_prs):
        before = saved(bare_prs)
        bare_prs.slide_show.loop = True
        after = saved(bare_prs)

        assert sorted(set(part_names(after)) - set(part_names(before))) == [PRESPROPS]
        for name in part_names(before):
            if name in ("[Content_Types].xml", "ppt/_rels/presentation.xml.rels"):
                continue
            assert part_bytes(after, name) == part_bytes(before, name), name


class DescribeSlideShowSettings_on_a_deck_it_cannot_edit(object):
    """A presProps part with the wrong content type is not XML this library loaded."""

    @pytest.fixture
    def untyped_prs(self):
        import zipfile

        from power_pptx.opc.constants import CONTENT_TYPE as CT

        blob = blank_deck_bytes()
        override = '<Override PartName="/ppt/presProps.xml" ContentType="%s"/>' % CT.PML_PRES_PROPS
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(blob)) as zin:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == "[Content_Types].xml":
                        assert override.encode() in data
                        data = data.replace(override.encode(), b"")
                    zout.writestr(item.filename, data)
        return _open(out.getvalue())

    def it_reports_the_assumed_values(self, untyped_prs):
        assert _settings(untyped_prs) == DEFAULTS

    def but_it_raises_rather_than_add_a_second_presProps_part(self, untyped_prs, monkeypatch):
        # -- pin the zip timestamps so two saves of an unchanged deck are equal --
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        before = saved(untyped_prs)

        with pytest.raises(ValueError, match="already has a presentation-properties part"):
            untyped_prs.slide_show.loop = True

        assert saved(untyped_prs) == before
