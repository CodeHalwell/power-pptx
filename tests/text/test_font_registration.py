"""Bundled font folders, explicit families, weights, tracking, and truncation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from power_pptx.text import (
    clear_registered_fonts,
    measure_text,
    register_font_dir,
    register_font_family,
    registered_font_dirs,
    registered_font_files,
    truncate_text,
)
from power_pptx.text.fonts import (
    FONT_DIRS_ENV,
    FontFiles,
    _Font,
    find_font_file,
    font_face_family,
    font_is_installed,
    resolve_weight,
)
from power_pptx.util import Pt

FONTS = Path(__file__).parents[1] / "fonts"


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    monkeypatch.delenv(FONT_DIRS_ENV, raising=False)
    clear_registered_fonts()
    yield
    clear_registered_fonts()


class DescribeRegisterFontDir:
    def it_finds_each_style_in_a_registered_folder(self):
        assert find_font_file("Outfit", bold=True) is None

        register_font_dir(FONTS)

        assert find_font_file("Outfit") == str(FONTS / "Outfit-Regular.ttf")
        assert find_font_file("Outfit", bold=True) == str(FONTS / "Outfit-Bold.ttf")
        assert font_is_installed("Tektur")
        assert str(FONTS) in registered_font_dirs()

    def it_reads_folders_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(FONT_DIRS_ENV, os.pathsep.join(["/no/such/folder", str(FONTS)]))
        FontFiles.clear_cache()

        assert registered_font_dirs() == (str(FONTS),)
        assert find_font_file("Outfit", bold=True) == str(FONTS / "Outfit-Bold.ttf")

    def it_rejects_a_missing_folder(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            register_font_dir(tmp_path / "missing")

    def it_registers_a_folder_once(self):
        register_font_dir(FONTS)
        register_font_dir(str(FONTS))

        assert registered_font_dirs().count(str(FONTS)) == 1


class DescribeRegisterFontFamily:
    def it_maps_styles_and_weights_to_explicit_files(self):
        register_font_family(
            "Brand Sans",
            regular=FONTS / "Outfit-Regular.ttf",
            bold=FONTS / "Outfit-Bold.ttf",
            weights={"medium": FONTS / "Tektur-Medium.ttf"},
        )

        assert find_font_file("Brand Sans") == str(FONTS / "Outfit-Regular.ttf")
        assert find_font_file("Brand Sans", bold=True) == str(FONTS / "Outfit-Bold.ttf")
        assert find_font_file("Brand Sans", weight=500) == str(FONTS / "Tektur-Medium.ttf")
        assert find_font_file("Brand Sans", weight="bold") == str(FONTS / "Outfit-Bold.ttf")
        assert registered_font_files() == (
            str(FONTS / "Outfit-Regular.ttf"),
            str(FONTS / "Outfit-Bold.ttf"),
            str(FONTS / "Tektur-Medium.ttf"),
        )
        # -- the files' folder is not searched as a whole --
        assert registered_font_dirs() == ()
        assert find_font_file("Tektur") is None

    def it_rejects_missing_files(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            register_font_family("Brand Sans", regular=tmp_path / "nope.ttf")


class DescribeWeights:
    @pytest.mark.parametrize(
        ("weight", "bold", "expected"),
        [
            (None, False, 400),
            (None, True, 700),
            ("medium", False, 500),
            ("SemiBold", False, 600),
            ("semi-bold", False, 600),
            (300, False, 300),
            ("bold", True, 700),
        ],
    )
    def it_resolves_names_and_numbers(self, weight, bold, expected):
        assert resolve_weight(weight, bold) == expected

    @pytest.mark.parametrize("weight", [450, 0, 1000, "chunky", True, 5.0])
    def it_rejects_unknown_weights(self, weight):
        with pytest.raises(ValueError):
            resolve_weight(weight)

    def it_rejects_bold_with_another_weight(self):
        with pytest.raises(ValueError, match="conflicts"):
            resolve_weight("medium", bold=True)

    def it_reads_the_weight_class_and_typographic_family(self):
        with _Font.open(str(FONTS / "Tektur-Medium.ttf")) as font:
            assert font.weight == 500
            assert font.family_name == "Tektur Medium"
            assert font.typographic_family_name == "Tektur"

    def it_finds_exact_faces_by_weight_only(self):
        register_font_dir(FONTS)

        assert find_font_file("Tektur", weight="medium") == str(FONTS / "Tektur-Medium.ttf")
        assert find_font_file("Tektur", weight="semibold") is None
        assert font_face_family(str(FONTS / "Tektur-Medium.ttf")) == "Tektur Medium"


class DescribeTrackedMeasurement:
    def it_adds_letter_spacing_after_every_character(self):
        register_font_dir(FONTS)
        text = "ACTIVE CUSTOMERS"
        plain = measure_text(text, Pt(400), size_pt=9, font_family="Outfit", strict=True)
        tracked = measure_text(
            text, Pt(400), size_pt=9, font_family="Outfit", strict=True, letter_spacing=Pt(1.4)
        )

        assert tracked.width - plain.width == Pt(1.4) * len(text)

    def it_wraps_tracked_text_sooner(self):
        register_font_dir(FONTS)
        kwargs = {"size_pt": 9, "font_family": "Outfit", "strict": True}

        assert len(measure_text("ACTIVE CUSTOMERS", Pt(95), **kwargs).lines) == 1
        assert (
            len(measure_text("ACTIVE CUSTOMERS", Pt(95), letter_spacing=Pt(1.4), **kwargs).lines)
            == 2
        )

    def it_measures_with_the_requested_weight(self):
        register_font_dir(FONTS)
        medium = measure_text("Revenue", Pt(400), font_family="Tektur", weight="medium")

        assert medium.font_file == str(FONTS / "Tektur-Medium.ttf")


class DescribeTruncateText:
    def it_leaves_fitting_text_alone(self):
        register_font_dir(FONTS)

        assert truncate_text("Flat", Pt(60), size_pt=11, font_family="Outfit") == "Flat"

    def it_cuts_on_a_word_with_an_ellipsis(self):
        register_font_dir(FONTS)
        text = "Quarterly revenue grew strongly across all regions"

        result = truncate_text(text, Pt(120), size_pt=11, font_family="Outfit")

        assert result.endswith("…")
        assert text.startswith(result[:-1])
        assert result[-2] != " "
        assert len(measure_text(result, Pt(120), size_pt=11, font_family="Outfit").lines) == 1

    def it_cuts_a_single_long_word(self):
        register_font_dir(FONTS)

        result = truncate_text("Supercalifragilistic", Pt(50), size_pt=11, font_family="Outfit")

        assert result.endswith("…")
        assert len(result) < 20

    def it_honours_a_line_budget(self):
        register_font_dir(FONTS)
        text = "one two three four five six seven eight nine ten eleven twelve"

        result = truncate_text(text, Pt(80), max_lines=2, size_pt=11, font_family="Outfit")

        assert len(measure_text(result, Pt(80), size_pt=11, font_family="Outfit").lines) == 2

    def it_validates_its_line_budget(self):
        with pytest.raises(ValueError):
            truncate_text("x", Pt(80), max_lines=0)


class DescribeTruncateTextFallback:
    def it_raises_in_strict_mode_for_a_missing_font(self):
        with pytest.raises(ValueError, match="fallback metrics"):
            truncate_text("Quarterly revenue", Pt(40), font_family="No Such Font", strict=True)

    def it_warns_when_a_named_font_is_missing(self):
        from power_pptx.exc import FontMetricsWarning

        with pytest.warns(FontMetricsWarning):
            truncate_text("Quarterly revenue", Pt(40), font_family="No Such Font")


class DescribeDrawingFamily:
    def it_keeps_a_family_that_matches_the_file(self):
        from power_pptx.text.fonts import drawing_family

        medium = str(FONTS / "Tektur-Medium.ttf")
        assert drawing_family("Tektur", medium) == "Tektur"
        assert drawing_family("Tektur Medium", medium) == "Tektur Medium"
        assert drawing_family(None, medium) is None

    def it_replaces_an_alias_with_the_files_family(self):
        from power_pptx.text.fonts import drawing_family

        assert drawing_family("Brand Sans", str(FONTS / "Outfit-Regular.ttf")) == "Outfit"


class DescribeRenderedLineHeight:
    # PowerPoint, and LibreOffice opening a .pptx, make a single-spaced line in a
    # shape 1.2 times the point size whatever the font (Outfit, whose ascent and
    # descent are 1.26 em, included) and scale that by the line spacing. Only in
    # a table cell does LibreOffice use the font's own ascent and descent.

    def it_reserves_the_line_spacing_times_a_single_spaced_line(self):
        register_font_dir(FONTS)
        text = "one two three four five six seven eight"

        m = measure_text(text, Pt(80), size_pt=18, font_family="Outfit", strict=True)
        single = measure_text(
            text, Pt(80), size_pt=18, font_family="Outfit", strict=True, line_spacing=None
        )

        assert len(m.lines) > 1
        assert m.height == pytest.approx(Pt(18 * 1.2 * 1.2) * len(m.lines), abs=len(m.lines))
        assert single.height == pytest.approx(Pt(18 * 1.2) * len(m.lines), abs=len(m.lines))

    def it_reserves_the_fonts_own_line_height_in_a_table(self):
        from PIL import ImageFont

        register_font_dir(FONTS)
        ascent, descent = ImageFont.truetype(str(FONTS / "Outfit-Regular.ttf"), 1000).getmetrics()
        text = "one two three four five six seven eight"

        m = measure_text(text, Pt(80), size_pt=18, font_family="Outfit", in_table=True)

        per_line = 18 * 1.2 * (ascent + descent) / 1000 * 12700
        assert m.height == pytest.approx(per_line * len(m.lines), abs=len(m.lines))

    def it_takes_an_exact_line_height(self):
        register_font_dir(FONTS)

        m = measure_text("one\ntwo", Pt(80), size_pt=18, font_family="Outfit", line_spacing=Pt(30))

        assert m.height == Pt(60)

    def it_uses_the_same_lines_when_fitting(self):
        from power_pptx.text.layout import TextFitter

        register_font_dir(FONTS)
        path = str(FONTS / "Outfit-Regular.ttf")
        line = measure_text("Revenue", Pt(400), size_pt=18, font_family="Outfit").height

        # Room for the measured line fits 18pt; 1 EMU less forces a smaller size.
        kwargs = {"min_size": 6, "max_lines": 1, "line_spacing": 1.2}
        assert TextFitter.best_fit_font_size("Revenue", (Pt(400), line), 18, path, **kwargs) == 18
        assert (
            TextFitter.best_fit_font_size("Revenue", (Pt(400), line - 1), 18, path, **kwargs) < 18
        )


class DescribeRegisterFontFamilyCache:
    def it_rescans_so_the_files_real_family_resolves(self):
        assert find_font_file("Outfit") is None  # populates the index first

        register_font_family("Brand Sans", regular=FONTS / "Outfit-Regular.ttf")

        assert find_font_file("Outfit") == str(FONTS / "Outfit-Regular.ttf")


def _collection(*paths: Path) -> bytes:
    """A TrueType collection (.ttc) holding the fonts at `paths`, in that order."""
    import struct

    fonts = [path.read_bytes() for path in paths]
    directories = []
    for data in fonts:
        count = struct.unpack_from(">H", data, 4)[0]
        directories.append(
            (data[:12], [struct.unpack_from(">4sLLL", data, 12 + 16 * i) for i in range(count)])
        )
    header_size = 12 + 4 * len(fonts)
    start = header_size + sum(12 + 16 * len(records) for _, records in directories)
    body, out_directories = b"", []
    for (offset_table, records), data in zip(directories, fonts):
        directory = offset_table
        for tag, checksum, offset, length in records:
            directory += struct.pack(">4sLLL", tag, checksum, start + len(body), length)
            body += data[offset : offset + length] + b"\0" * (-length % 4)
        out_directories.append(directory)
    offsets, position = [], header_size
    for directory in out_directories:
        offsets.append(position)
        position += len(directory)
    header = b"ttcf" + struct.pack(">HHL", 1, 0, len(fonts))
    header += b"".join(struct.pack(">L", offset) for offset in offsets)
    return header + b"".join(out_directories) + body


class DescribeFontCollections:
    def it_finds_every_face_of_a_ttc_collection(self, tmp_path):
        from power_pptx.text.layout import _rendered_size

        path = tmp_path / "pair.ttc"
        path.write_bytes(_collection(FONTS / "Outfit-Regular.ttf", FONTS / "Tektur-Regular.ttf"))
        register_font_dir(tmp_path)

        outfit, tektur = find_font_file("Outfit"), find_font_file("Tektur")

        assert outfit == str(path)
        assert str(tektur) == str(path)
        assert tektur != outfit
        assert getattr(tektur, "face_index", 0) == 1
        assert font_is_installed("Tektur")
        assert font_face_family(tektur) == "Tektur"
        assert _rendered_size("Revenue", 18, tektur) == _rendered_size(
            "Revenue", 18, str(FONTS / "Tektur-Regular.ttf")
        )


class DescribeFontLookup:
    def it_matches_family_names_case_insensitively(self):
        register_font_dir(FONTS)

        assert find_font_file("outfit") == str(FONTS / "Outfit-Regular.ttf")
        assert find_font_file("OUTFIT", bold=True) == str(FONTS / "Outfit-Bold.ttf")
        assert find_font_file("tektur", weight="medium") == str(FONTS / "Tektur-Medium.ttf")

    def and_registered_families_too(self):
        register_font_family("Brand Sans", regular=FONTS / "Outfit-Regular.ttf")

        assert find_font_file("brand sans") == str(FONTS / "Outfit-Regular.ttf")

    def it_notices_a_font_folder_added_to_the_environment_later(self, monkeypatch):
        assert find_font_file("Outfit") is None  # builds the index

        monkeypatch.setenv(FONT_DIRS_ENV, str(FONTS))

        assert find_font_file("Outfit") == str(FONTS / "Outfit-Regular.ttf")

    def it_does_not_search_the_folder_of_a_registered_file(self):
        register_font_family("Brand Sans", regular=FONTS / "Outfit-Regular.ttf")

        assert find_font_file("Tektur") is None
        assert registered_font_dirs() == ()


class DescribeNameTableLanguages:
    def it_prefers_the_English_family_name(self):
        from power_pptx.text.fonts import _NameTable

        name_table = _name_table(
            [(3, 1, 0x0409, "WenQuanYi Zen Hei"), (3, 1, 0x0404, "文泉驛正黑")]
        )

        assert name_table.family_name == "WenQuanYi Zen Hei"
        assert name_table.family_aliases == ["文泉驛正黑"]
        assert isinstance(name_table, _NameTable)


def _name_table(records):
    """A `_NameTable` over a synthetic 'name' table of (platform, name_id, language, text)."""
    import io
    import struct

    from power_pptx.text.fonts import _NameTable, _Stream

    strings, entries = b"", b""
    for platform_id, name_id, language_id, text in records:
        raw = text.encode("utf-16-be")
        entries += struct.pack(
            ">HHHHHH", platform_id, 1, language_id, name_id, len(raw), len(strings)
        )
        strings += raw
    header = struct.pack(">HHH", 0, len(records), 6 + len(entries))
    data = header + entries + strings
    return _NameTable("name", _Stream(io.BytesIO(data)), 0, len(data))
