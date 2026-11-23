"""Unit tests for `power_pptx.review` that need neither LibreOffice nor a browser.

The rendering paths are exercised by `tests/integration/test_review.py`.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from power_pptx import Presentation, compose, review
from power_pptx.review import ReviewReport, _clear_previous_run, main, review_presentation
from power_pptx.util import Inches
from power_pptx.validation import ValidationReport


def _deck():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text = "Review me"
    return prs


#: What a four-slide review with references leaves in its output directory.
PREVIOUS_RUN = [
    "presentation.pptx",
    "presentation.pdf",
    "manifest.json",
    "REVIEW.md",
    "index.html",
    "contact-01.png",
    "contact-02.png",
    "slides/slide-00.png",
    "slides/slide-01.png",
    "slides/slide-02.png",
    "slides/slide-03.png",
    "references/slide-00.png",
    "differences/slide-00.png",
    "browser-reference/slide-00.png",
]

#: Files a review never writes, in the places where it writes its own.
CALLERS_FILES = [
    "notes.txt",
    "contact-sheet-draft.png",
    "slide-00.png",
    "slides/slide-00.psd",
    "slides/cover.png",
    "assets/slides/slide-00.png",
]


@pytest.fixture
def reused(tmp_path):
    """An output directory holding an earlier review and some files of the caller's."""
    out = tmp_path / "review"
    for name in PREVIOUS_RUN + CALLERS_FILES:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"from before")
    return out


def _files(directory):
    return sorted(
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    )


class DescribeClearPreviousRun:
    def it_removes_what_an_earlier_review_wrote_and_nothing_else(self, reused):
        _clear_previous_run(reused)

        assert _files(reused) == sorted(CALLERS_FILES)
        # -- folders the review made are gone once empty; one still in use stays --
        assert not (reused / "references").exists()
        assert not (reused / "differences").exists()
        assert not (reused / "browser-reference").exists()
        assert (reused / "slides").is_dir()

    def it_does_nothing_for_a_directory_that_is_not_there_yet(self, tmp_path):
        _clear_previous_run(tmp_path / "absent")

        assert not (tmp_path / "absent").exists()

    def it_does_not_follow_a_linked_folder(self, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "slide-00.png").write_bytes(b"not ours")
        out = tmp_path / "review"
        out.mkdir()
        try:
            (out / "slides").symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symbolic links are not available here")

        _clear_previous_run(out)

        assert (elsewhere / "slide-00.png").read_bytes() == b"not ours"

    def it_removes_a_linked_file_but_not_what_it_links_to(self, tmp_path):
        elsewhere = tmp_path / "elsewhere.png"
        elsewhere.write_bytes(b"not ours")
        out = tmp_path / "review"
        (out / "slides").mkdir(parents=True)
        try:
            (out / "manifest.json").symlink_to(elsewhere)
            (out / "slides" / "slide-00.png").symlink_to(elsewhere)
        except (OSError, NotImplementedError):
            pytest.skip("symbolic links are not available here")

        _clear_previous_run(out)

        assert not (out / "manifest.json").is_symlink()
        assert not (out / "slides").exists()
        assert elsewhere.read_bytes() == b"not ours"

    def it_leaves_folders_that_carry_the_name_of_one_of_its_files(self, tmp_path):
        out = tmp_path / "review"
        for name in ["index.html/kept.txt", "contact-01.png/kept.txt", "slides/slide-00.png/x"]:
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(b"the caller's")
        (out / "references").write_bytes(b"a file where a folder would be")

        _clear_previous_run(out)

        assert _files(out) == [
            "contact-01.png/kept.txt",
            "index.html/kept.txt",
            "references",
            "slides/slide-00.png/x",
        ]

    def it_clears_a_folder_of_its_own_that_it_does_not_read_from(self, tmp_path, reused):
        elsewhere = tmp_path / "references-in"
        elsewhere.mkdir()

        _clear_previous_run(reused, keep=elsewhere)

        assert _files(reused) == sorted(CALLERS_FILES)
        assert _files(elsewhere) == []

    def but_it_keeps_the_folder_it_reads_from_by_whatever_path_it_is_named(self, reused):
        _clear_previous_run(reused, keep=str(reused / "references" / ".." / "references"))

        assert _files(reused / "references") == ["slide-00.png"]
        assert not (reused / "slides" / "slide-00.png").exists()


class DescribeReviewPresentationReuse:
    def it_replaces_the_previous_run_even_when_this_one_cannot_render(self, reused):
        report = review_presentation(_deck(), out_dir=reused, soffice_bin="/absent/soffice")

        assert report.has_errors
        assert report.manifest["slides"] == []
        # -- the earlier run's pages, sheets, comparison and PDF are gone ... --
        assert _files(reused) == sorted(
            CALLERS_FILES + ["presentation.pptx", "manifest.json", "REVIEW.md", "index.html"]
        )
        # -- ... and what remains is this run's, not a leftover of the same name --
        assert json.loads((reused / "manifest.json").read_text())["passed"] is False
        assert (reused / "presentation.pptx").read_bytes() != b"from before"
        assert (reused / "notes.txt").read_bytes() == b"from before"

    def but_it_never_removes_the_references_it_was_given(self, reused):
        # -- an earlier run's pages handed back in as this run's references --
        references = reused / "slides"

        report = review_presentation(
            _deck(),
            out_dir=reused,
            reference_dir=references,
            soffice_bin="/absent/soffice",
        )

        assert report.has_errors
        assert sorted(p.name for p in references.iterdir()) == [
            "cover.png",
            "slide-00.png",
            "slide-00.psd",
            "slide-01.png",
            "slide-02.png",
            "slide-03.png",
        ]
        assert not (reused / "differences").exists()


class DescribeReviewCli:
    def it_keeps_the_last_review_when_the_input_cannot_be_read(self, reused, tmp_path):
        missing = tmp_path / "missing.pptx"

        assert main([str(missing), "--out-dir", str(reused)]) == 1

        # -- nothing was reviewed, so nothing of the earlier review is discarded --
        assert _files(reused) == sorted(PREVIOUS_RUN + CALLERS_FILES)
        assert json.loads((reused / "manifest.json").read_text())["passed"] is False
        assert (reused / "slides" / "slide-03.png").read_bytes() == b"from before"

    def it_never_removes_an_input_that_lives_in_the_output_directory(self, tmp_path):
        out = tmp_path / "review"
        out.mkdir()
        source = out / "presentation.pptx"
        _deck().save(source)
        original = source.read_bytes()

        assert main([str(source), "--out-dir", str(out)]) == 1

        assert source.read_bytes() == original
        assert "overwrite" in json.loads((out / "manifest.json").read_text())["error"]


def _png(path, color="#204060", size=(64, 36)):
    Image.new("RGB", size, color).save(path)
    return path


@pytest.fixture
def fake_render(monkeypatch):
    """Render each slide as a plain PNG instead of through LibreOffice."""
    calls = []

    def render(prs, directory, *, dpi, soffice_bin, timeout, font_dirs=None):
        calls.append(
            {"dpi": dpi, "soffice_bin": soffice_bin, "timeout": timeout, "font_dirs": font_dirs}
        )
        target = directory / "slides"
        target.mkdir()
        return [_png(target / f"slide-{i:02d}.png") for i in range(len(prs.slides))]

    monkeypatch.setattr(review, "_render", render)
    return calls


def _validation(**fields):
    defaults = {"slide_count": 1, "schema_checked": True, "roundtrip_checked": True}
    return ValidationReport(**{**defaults, **fields})


@pytest.fixture
def validation(monkeypatch):
    """Make `review_presentation()` see the validation report `state["report"]`."""
    state = {"report": _validation(), "calls": []}

    def validate(data, **kwargs):
        state["calls"].append(kwargs)
        return state["report"]

    monkeypatch.setattr(review, "validate_presentation", validate)
    return state


class DescribeReviewPresentationOptions:
    @pytest.mark.parametrize(
        ("options", "message"),
        [
            ({"reference_dir": ".", "reference_html": "a.html"}, "Choose reference_dir or"),
            ({"font_policy": "strict"}, "font_policy must be warn, error, or ignore"),
            ({"dpi": True}, "dpi and timeout must be positive"),
            ({"dpi": 96.0}, "dpi and timeout must be positive"),
            ({"dpi": 0}, "dpi and timeout must be positive"),
            ({"timeout": 0}, "dpi and timeout must be positive"),
            ({"max_mean_error": float("nan")}, "max_mean_error must be between 0 and 1"),
            ({"max_mean_error": float("inf")}, "max_mean_error must be between 0 and 1"),
            ({"max_mean_error": -0.01}, "max_mean_error must be between 0 and 1"),
            ({"max_mean_error": 1.01}, "max_mean_error must be between 0 and 1"),
            ({"reference_dir": "absent"}, "reference_dir must be an existing directory"),
            # -- the first problem found is the one reported --
            (
                {"reference_dir": ".", "reference_html": "a.html", "font_policy": "x", "dpi": 0},
                "Choose reference_dir or",
            ),
            ({"font_policy": "x", "dpi": 0}, "font_policy must be"),
            ({"dpi": 0, "max_mean_error": 2}, "dpi and timeout must be positive"),
            ({"max_mean_error": 2, "reference_dir": "absent"}, "max_mean_error must be"),
        ],
    )
    def it_rejects_an_invalid_option_before_writing_anything(
        self, options, message, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out" / "review"

        with pytest.raises(ValueError, match=message):
            review_presentation(_deck(), out_dir=out, **options)

        assert not (tmp_path / "out").exists()

    def it_refuses_to_overwrite_its_input_before_checking_the_references(self, tmp_path):
        source = tmp_path / "presentation.pptx"
        _deck().save(source)

        with pytest.raises(ValueError, match="cannot overwrite its input"):
            review_presentation(source, out_dir=tmp_path, reference_dir=tmp_path / "absent")

    @pytest.mark.parametrize("limit", [0, 1, 0.5])
    def it_accepts_a_difference_limit_from_0_to_1(self, limit, tmp_path, fake_render):
        report = review_presentation(_deck(), out_dir=tmp_path / "review", max_mean_error=limit)

        assert report.manifest["errors"] == []

    def it_hands_its_settings_to_the_renderer_and_the_validator(
        self, tmp_path, fake_render, validation
    ):
        review_presentation(
            _deck(),
            out_dir=tmp_path / "review",
            dpi=48,
            soffice_bin="/opt/soffice",
            timeout=9,
            font_policy="ignore",
            check_schema=False,
        )

        assert fake_render == [
            {"dpi": 48, "soffice_bin": "/opt/soffice", "timeout": 9, "font_dirs": None}
        ]
        assert validation["calls"] == [{"check_schema": False, "check_fonts": False}]

    def it_registers_its_font_folders_before_refusing_to_overwrite_the_input(
        self, tmp_path, monkeypatch
    ):
        from power_pptx.text import fonts

        registered = []
        monkeypatch.setattr(fonts, "register_font_dir", registered.append)
        source = tmp_path / "presentation.pptx"
        _deck().save(source)

        with pytest.raises(ValueError, match="cannot overwrite its input"):
            review_presentation(source, out_dir=tmp_path, font_dirs=["a", "b"])

        assert registered == ["a", "b"]

    def it_hands_its_font_folders_to_the_renderer(self, tmp_path, fake_render, monkeypatch):
        from power_pptx.text import fonts

        registered = []
        monkeypatch.setattr(fonts, "register_font_dir", registered.append)

        review_presentation(_deck(), out_dir=tmp_path / "review", font_dirs=["a"])

        assert registered == ["a"]
        assert fake_render[0]["font_dirs"] == ["a"]


class DescribeReviewPresentationErrors:
    def it_passes_a_clean_deck_and_lists_what_it_wrote(self, tmp_path, fake_render):
        prs = _deck()
        prs.core_properties.title = "Quarterly"
        prs.slides.add_slide(prs.slide_layouts[6]).shapes.add_textbox(
            Inches(1), Inches(1), Inches(2), Inches(1)
        ).text = "Second"

        report = review_presentation(prs, out_dir=tmp_path / "review")

        manifest = report.manifest
        assert manifest["passed"] is True
        assert manifest["errors"] == []
        assert manifest["title"] == "Quarterly"
        assert manifest["slide_count"] == 2
        assert manifest["slides"] == ["slides/slide-00.png", "slides/slide-01.png"]
        assert manifest["contact_sheets"] == ["contact-01.png"]
        assert manifest["comparisons"] == []
        assert manifest["visual_review"] == "pending"
        assert manifest["dpi"] == 120
        assert json.loads((tmp_path / "review" / "manifest.json").read_text()) == manifest
        assert _files(tmp_path / "review") == [
            "REVIEW.md",
            "contact-01.png",
            "index.html",
            "manifest.json",
            "presentation.pptx",
            "slides/slide-00.png",
            "slides/slide-01.png",
        ]

    def it_records_each_failed_check_in_order(self, tmp_path, fake_render, validation):
        validation["report"] = _validation(
            errors=["Validator error"],
            schema_violations=[("ppt/slides/slide1.xml", "bad")],
            roundtrip_changed_parts=["ppt/slides/slide1.xml"],
            missing_fonts=["Absent"],
            audit={
                "has_errors": True,
                "empty_slides": [1],
                "lint_issues": [{"severity": "error"}],
            },
        )

        report = review_presentation(
            _deck(), out_dir=tmp_path / "review", font_policy="error", fail_on_warnings=True
        )

        assert report.manifest["errors"] == [
            "Validator error",
            "OOXML schema/package validation failed",
            "Save/reopen round-trip changed package parts",
            "Deck audit found errors",
            "Deck contains empty slides",
            "Missing native fonts: Absent",
            "Warnings are configured to fail this review",
        ]
        assert report.manifest["passed"] is False
        assert report.manifest["validation"]["missing_fonts"] == ["Absent"]

    def it_only_warns_about_missing_fonts_by_default(self, tmp_path, fake_render, validation):
        validation["report"] = _validation(missing_fonts=["Absent"])

        report = review_presentation(_deck(), out_dir=tmp_path / "review")

        assert report.manifest["errors"] == []
        assert "Missing native fonts: Absent" in (tmp_path / "review" / "index.html").read_text()

    @pytest.mark.parametrize(
        ("missing_fonts", "severities", "fails"),
        [
            ([], ["error"], False),
            ([], ["warning"], True),
            ([], ["info"], True),
            (["Absent"], [], True),
            ([], [], False),
        ],
    )
    def it_can_fail_on_warnings(
        self, missing_fonts, severities, fails, tmp_path, fake_render, validation
    ):
        validation["report"] = _validation(
            missing_fonts=missing_fonts,
            audit={"lint_issues": [{"severity": severity} for severity in severities]},
        )

        report = review_presentation(_deck(), out_dir=tmp_path / "review", fail_on_warnings=True)

        expected = ["Warnings are configured to fail this review"] if fails else []
        assert report.manifest["errors"] == expected

    def it_records_a_deck_with_no_slides_without_rendering_it(self, tmp_path, fake_render):
        report = review_presentation(Presentation(), out_dir=tmp_path / "review")

        assert report.manifest["errors"] == [
            "Presentation has no slides",
            "ValueError: Presentation has no slides",
        ]
        assert fake_render == []
        assert report.manifest["slides"] == []

    def it_records_a_failed_render(self, tmp_path, monkeypatch):
        def render(*args, **kwargs):
            raise RuntimeError("renderer unavailable")

        monkeypatch.setattr(review, "_render", render)

        report = review_presentation(_deck(), out_dir=tmp_path / "review")

        assert report.manifest["errors"] == ["RuntimeError: renderer unavailable"]
        assert report.manifest["slides"] == []
        assert report.manifest["contact_sheets"] == []


@pytest.fixture
def browser_capture(monkeypatch):
    """Capture HTML references as plain PNGs of `state["color"]`."""
    from power_pptx.design import _html

    state = {"color": "#204060", "calls": []}

    def capture_html(source, **kwargs):
        state["calls"].append((source, kwargs))
        path = _png(Path(str(source) + ".png"), state["color"])
        return [SimpleNamespace(png=path.read_bytes())]

    monkeypatch.setattr(_html, "capture_html", capture_html)
    return state


class DescribeReviewPresentationReferences:
    def it_compares_against_html_captured_in_a_browser(
        self, tmp_path, fake_render, browser_capture
    ):
        html = tmp_path / "deck.html"

        report = review_presentation(
            _deck(),
            out_dir=tmp_path / "review",
            reference_html=html,
            selector="section",
            viewport=(800, 450),
            wait_for_function="ready()",
            browser_path="/opt/chromium",
            max_mean_error=0,
        )

        assert browser_capture["calls"] == [
            (
                html,
                {
                    "selector": "section",
                    "multiple": True,
                    "viewport": (800, 450),
                    "browser_path": "/opt/chromium",
                    "wait_for_function": "ready()",
                },
            )
        ]
        assert report.manifest["errors"] == []
        assert report.manifest["comparisons"] == [
            {"slide": 1, "mean_error": 0.0, "within_tolerance": True}
        ]
        assert sorted(
            path for path in _files(tmp_path / "review") if not path.startswith("slides/")
        ) == [
            "REVIEW.md",
            "browser-reference/slide-00.png",
            "contact-01.png",
            "differences/slide-00.png",
            "index.html",
            "manifest.json",
            "presentation.pptx",
            "references/slide-00.png",
        ]

    def it_fails_when_a_slide_differs_by_more_than_the_limit(
        self, tmp_path, fake_render, browser_capture
    ):
        browser_capture["color"] = "#FFFFFF"

        report = review_presentation(
            _deck(),
            out_dir=tmp_path / "review",
            reference_html=tmp_path / "deck.html",
            max_mean_error=0.01,
        )

        assert report.manifest["errors"] == [
            "Rendered slides exceed the requested reference difference limit"
        ]
        assert report.manifest["comparisons"][0]["within_tolerance"] is False

    def but_only_reports_the_difference_without_a_limit(self, tmp_path, fake_render):
        references = tmp_path / "references-in"
        references.mkdir()
        _png(references / "a.png", "#FFFFFF")

        report = review_presentation(_deck(), out_dir=tmp_path / "review", reference_dir=references)

        assert report.manifest["errors"] == []
        assert report.manifest["comparisons"][0]["within_tolerance"] is None
        assert report.manifest["comparisons"][0]["mean_error"] > 0


@pytest.fixture
def reviews(monkeypatch):
    """Record each `review_presentation()` call `main()` makes, without rendering.

    A review fails when its output folder's name is in `state["failing"]`, and
    raises the exception in `state["raising"]` for that name.
    """
    state = {"calls": [], "failing": set(), "raising": {}}

    def fake(source, **kwargs):
        name = Path(kwargs["out_dir"]).name
        state["calls"].append((source, kwargs))
        if name in state["raising"]:
            raise state["raising"][name]
        return ReviewReport(Path(kwargs["out_dir"]), {"passed": name not in state["failing"]})

    monkeypatch.setattr(review, "review_presentation", fake)
    return state


def _review_options(**overrides):
    """The options `main()` passes to `review_presentation()` by default."""
    options = {
        "reference_dir": None,
        "reference_html": None,
        "browser_path": None,
        "wait_for_function": None,
        "selector": "[data-slide]",
        "dpi": 120,
        "soffice_bin": None,
        "max_mean_error": None,
        "font_policy": "warn",
        "fail_on_warnings": False,
    }
    options.update(overrides)
    return options


class DescribeReviewCliArguments:
    @pytest.mark.parametrize(
        "extra",
        [
            ["--reference-dir", "refs"],
            ["--reference-html", "refs.html"],
        ],
    )
    def it_refuses_explicit_references_for_several_inputs(self, extra, tmp_path, reviews):
        with pytest.raises(SystemExit) as raised:
            main(["a.pptx", "b.pptx", "--out-dir", str(tmp_path / "out"), *extra])

        assert raised.value.code == 2
        assert reviews["calls"] == []

    def it_refuses_inputs_that_share_a_name(self, tmp_path, reviews, capsys):
        with pytest.raises(SystemExit) as raised:
            main(["a/deck.pptx", "b/deck.pptx", "--out-dir", str(tmp_path / "out")])

        assert raised.value.code == 2
        assert "Batch inputs must have distinct basenames" in capsys.readouterr().err

    def it_refuses_a_font_folder_that_is_not_there(self, tmp_path, reviews, capsys):
        with pytest.raises(SystemExit) as raised:
            main(["a.pptx", "--out-dir", str(tmp_path), "--font-dir", str(tmp_path / "absent")])

        assert raised.value.code == 2
        assert "is not a directory" in capsys.readouterr().err
        assert reviews["calls"] == []

    def it_passes_its_options_on_to_the_review(self, tmp_path, reviews, capsys):
        source = tmp_path / "deck.pptx"
        out = tmp_path / "out"

        status = main(
            [
                str(source),
                "--out-dir",
                str(out),
                "--reference-dir",
                str(tmp_path / "refs"),
                "--browser-path",
                "/opt/chromium",
                "--ready",
                "ready()",
                "--selector",
                "section",
                "--dpi",
                "48",
                "--soffice-bin",
                "/opt/soffice",
                "--max-error",
                "0.25",
                "--font-policy",
                "error",
                "--fail-on-warnings",
            ]
        )

        assert status == 0
        assert reviews["calls"] == [
            (
                source,
                _review_options(
                    out_dir=out,
                    reference_dir=tmp_path / "refs",
                    browser_path="/opt/chromium",
                    wait_for_function="ready()",
                    selector="section",
                    dpi=48,
                    soffice_bin="/opt/soffice",
                    max_mean_error=0.25,
                    font_policy="error",
                    fail_on_warnings=True,
                ),
            )
        ]
        assert capsys.readouterr().out == "deck.pptx: PASS — %s\n" % (out / "index.html")


class DescribeReviewCliSources:
    def it_builds_a_deck_from_html_and_captures_its_own_references(
        self, tmp_path, reviews, monkeypatch
    ):
        calls = []
        built = Presentation()

        def from_html(path, **kwargs):
            calls.append((path, kwargs))
            return built

        monkeypatch.setattr(compose, "from_html", from_html)
        source = tmp_path / "deck.HTML"

        assert main([str(source), "--out-dir", str(tmp_path / "out"), "--mode", "hybrid"]) == 0

        ((path, kwargs),) = calls
        reference = kwargs["reference_dir"]
        assert path == source
        assert kwargs == {
            "mode": "hybrid",
            "browser_path": None,
            "selector": "[data-slide]",
            "wait_for_function": None,
            "reference_dir": reference,
            "allow_network": True,
        }
        assert reference.name == "reference"
        assert reviews["calls"] == [
            (built, _review_options(out_dir=tmp_path / "out", reference_dir=reference))
        ]

    @pytest.mark.parametrize(
        "extra",
        [["--reference-dir", "refs"], ["--reference-html", "refs.html"]],
    )
    def but_not_when_it_is_given_references(self, extra, tmp_path, reviews, monkeypatch):
        calls = []
        monkeypatch.setattr(
            compose, "from_html", lambda path, **kwargs: calls.append(kwargs) or Presentation()
        )

        assert main([str(tmp_path / "deck.htm"), "--out-dir", str(tmp_path), *extra]) == 0

        assert calls[0]["reference_dir"] is None
        _, options = reviews["calls"][0]
        assert options["reference_dir"] == (Path("refs") if "--reference-dir" in extra else None)
        assert options["reference_html"] == (
            Path("refs.html") if "--reference-html" in extra else None
        )

    @pytest.mark.parametrize("suffix", [".json", ".JSON"])
    def it_builds_a_deck_from_a_json_spec(self, suffix, tmp_path, reviews, monkeypatch):
        specs = []
        monkeypatch.setattr(
            compose, "from_spec", lambda spec, **options: specs.append(spec) or "deck"
        )
        source = tmp_path / ("brief" + suffix)
        source.write_text(json.dumps({"slides": []}), encoding="utf-8")

        assert main([str(source), "--out-dir", str(tmp_path / "out")]) == 0

        assert specs == [{"slides": []}]
        assert reviews["calls"][0][0] == "deck"

    @pytest.mark.parametrize("suffix", [".yaml", ".yml"])
    def it_builds_a_deck_from_a_yaml_spec(self, suffix, tmp_path, reviews, monkeypatch):
        paths = []
        monkeypatch.setattr(
            compose, "from_yaml", lambda path, **options: paths.append(path) or "deck"
        )
        source = tmp_path / ("brief" + suffix)

        assert main([str(source), "--out-dir", str(tmp_path / "out")]) == 0

        assert paths == [source]
        assert reviews["calls"][0][0] == "deck"

    def it_fails_an_input_of_another_kind(self, tmp_path, reviews, capsys):
        out = tmp_path / "out"

        assert main([str(tmp_path / "notes.txt"), "--out-dir", str(out)]) == 1

        failure = {
            "input": str(tmp_path / "notes.txt"),
            "passed": False,
            "error": "Input must be PPTX, HTML, JSON, or YAML",
        }
        assert json.loads((out / "manifest.json").read_text()) == failure
        assert (out / "index.html").read_text() == (
            '<!doctype html><meta charset="utf-8"><title>Review failed</title>'
            "<h1>notes.txt</h1><p>Input must be PPTX, HTML, JSON, or YAML</p>"
            '<a href="manifest.json">Failure details</a>'
        )
        assert capsys.readouterr().err == (
            "notes.txt: FAIL — Input must be PPTX, HTML, JSON, or YAML\n"
        )
        assert reviews["calls"] == []


class DescribeReviewCliConsoleEncoding:
    """The summary lines contain a dash; an ASCII-only console must not break a review."""

    @staticmethod
    def _ascii_console(monkeypatch):
        streams = {
            name: io.TextIOWrapper(io.BytesIO(), encoding="ascii") for name in ("out", "err")
        }
        monkeypatch.setattr(sys, "stdout", streams["out"])
        monkeypatch.setattr(sys, "stderr", streams["err"])
        return streams

    @staticmethod
    def _text(stream):
        stream.flush()
        return stream.buffer.getvalue().decode("ascii")

    def it_records_a_finished_review_once_and_escapes_the_dash(
        self, tmp_path, reviews, monkeypatch
    ):
        console = self._ascii_console(monkeypatch)
        deck = tmp_path / "deck.pptx"
        out = tmp_path / "out"

        assert main([str(deck), "--out-dir", str(out)]) == 0

        assert len(reviews["calls"]) == 1
        assert self._text(console["out"]).startswith("deck.pptx: PASS \\u2014 ")
        assert self._text(console["err"]) == ""

    def and_it_still_reports_a_review_that_raised(self, tmp_path, reviews, monkeypatch):
        console = self._ascii_console(monkeypatch)
        # -- a single input is reviewed straight into --out-dir --
        reviews["raising"] = {"out": RuntimeError("cannot read it")}
        deck = tmp_path / "deck.pptx"

        assert main([str(deck), "--out-dir", str(tmp_path / "out")]) == 1

        assert self._text(console["err"]) == "deck.pptx: FAIL \\u2014 cannot read it\n"


class DescribeReviewCliBatch:
    def it_reviews_each_input_into_its_own_folder_and_indexes_them(self, tmp_path, reviews, capsys):
        reviews["failing"] = {"second"}
        reviews["raising"] = {"third": RuntimeError("cannot <read> it")}
        inputs = [tmp_path / "first.pptx", tmp_path / "second.pptx", tmp_path / "third.pptx"]
        out = tmp_path / "out"

        assert main([*map(str, inputs), "--out-dir", str(out)]) == 1

        assert [kwargs["out_dir"] for _, kwargs in reviews["calls"]] == [
            out / "first",
            out / "second",
            out / "third",
        ]
        assert json.loads((out / "batch.json").read_text()) == [
            {"input": str(inputs[0]), "passed": True, "directory": str(out / "first")},
            {"input": str(inputs[1]), "passed": False, "directory": str(out / "second")},
            {"input": str(inputs[2]), "passed": False, "error": "cannot <read> it"},
        ]
        assert (out / "index.html").read_text() == (
            '<!doctype html><meta charset="utf-8"><title>Deck reviews</title>'
            "<h1>Deck reviews</h1><ul>"
            '<li><a href="first/index.html">first.pptx</a>: PASS</li>'
            '<li><a href="second/index.html">second.pptx</a>: FAIL</li>'
            '<li><a href="third/index.html">third.pptx</a>: FAIL</li>'
            '</ul><a href="batch.json">Batch results</a>'
        )
        assert (out / "third" / "index.html").read_text() == (
            '<!doctype html><meta charset="utf-8"><title>Review failed</title>'
            "<h1>third.pptx</h1><p>cannot &lt;read&gt; it</p>"
            '<a href="manifest.json">Failure details</a>'
        )
        captured = capsys.readouterr()
        assert captured.out == (
            "first.pptx: PASS — %s\nsecond.pptx: FAIL — %s\n"
            % (out / "first" / "index.html", out / "second" / "index.html")
        )
        assert captured.err == "third.pptx: FAIL — cannot <read> it\n"

    def it_exits_0_when_every_review_passes(self, tmp_path, reviews):
        inputs = [str(tmp_path / "a.pptx"), str(tmp_path / "b.pptx")]

        assert main([*inputs, "--out-dir", str(tmp_path / "out")]) == 0

    def it_writes_no_batch_index_for_a_single_input(self, tmp_path, reviews):
        out = tmp_path / "out"

        assert main([str(tmp_path / "a.pptx"), "--out-dir", str(out)]) == 0

        assert out.is_dir()
        assert not (out / "batch.json").exists()
        assert not (out / "index.html").exists()


class DescribeReviewCommandSafeMode:
    """``--safe`` is for reviewing a spec or page somebody else wrote."""

    @pytest.fixture
    def spec_calls(self, monkeypatch):
        from power_pptx import compose

        calls = []
        monkeypatch.setattr(
            compose, "from_spec", lambda spec, **options: calls.append(("spec", options))
        )
        monkeypatch.setattr(
            compose, "from_yaml", lambda path, **options: calls.append(("yaml", options))
        )
        return calls

    def _args(self, *argv):
        from power_pptx.review import _build_parser

        return _build_parser().parse_args(["input", "--out-dir", "out", *argv])

    def it_builds_a_spec_as_trusted_by_default(self, spec_calls, tmp_path):
        from power_pptx.review import _deck_from_spec

        spec = tmp_path / "deck.json"
        spec.write_text('{"slides": []}')

        _deck_from_spec(spec, ".json", self._args())
        _deck_from_spec(tmp_path / "deck.yaml", ".yaml", self._args())

        assert spec_calls == [
            ("spec", {"safe": False, "base_dir": None}),
            ("yaml", {"safe": False, "base_dir": None}),
        ]

    def it_confines_a_spec_to_the_base_directory_when_asked(self, spec_calls, tmp_path):
        from power_pptx.review import _deck_from_spec

        spec = tmp_path / "deck.json"
        spec.write_text('{"slides": []}')
        args = self._args("--safe", "--base-dir", str(tmp_path))

        _deck_from_spec(spec, ".json", args)
        _deck_from_spec(tmp_path / "deck.yml", ".yml", args)

        assert spec_calls == [
            ("spec", {"safe": True, "base_dir": tmp_path}),
            ("yaml", {"safe": True, "base_dir": tmp_path}),
        ]

    def it_refuses_a_file_outside_the_base_directory(self, tmp_path):
        from power_pptx.compose.from_spec import SpecError
        from power_pptx.review import _deck_from_spec

        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "secret.png"
        outside.write_bytes(b"not really a png")
        spec = base / "deck.json"
        spec.write_text(
            json.dumps({"slides": [{"layout": "figure", "title": "t", "figure": str(outside)}]})
        )

        with pytest.raises(SpecError, match="outside base_dir"):
            _deck_from_spec(spec, ".json", self._args("--safe", "--base-dir", str(base)))

    @pytest.mark.parametrize(("argv", "allowed"), [((), True), (("--safe",), False)])
    def it_captures_an_html_input_offline_when_asked(self, monkeypatch, tmp_path, argv, allowed):
        from power_pptx import compose
        from power_pptx.review import _review_source

        seen = {}
        monkeypatch.setattr(compose, "from_html", lambda path, **options: seen.update(options))
        page = tmp_path / "brief.html"
        page.write_text("<section data-slide>x</section>")

        _review_source(page, self._args(*argv), tmp_path)

        assert seen["allow_network"] is allowed
