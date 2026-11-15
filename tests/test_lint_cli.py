"""Unit-test suite for `power_pptx.lint_cli` and the `power-pptx lint` command."""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import power_pptx
from power_pptx import Presentation, lint_cli
from power_pptx.__main__ import main as power_pptx_main
from power_pptx.enum.shapes import MSO_SHAPE
from power_pptx.lint import lint_report_to_sarif
from power_pptx.lint_cli import EXIT_CLEAN, EXIT_ISSUES, EXIT_USAGE, main
from power_pptx.util import Inches

# ---------------------------------------------------------------------------
# decks
# ---------------------------------------------------------------------------


def _severities(path: Path) -> list[str]:
    """Severities of every issue the linter itself reports for the deck at `path`."""
    return [
        issue.severity.value
        for slide in Presentation(str(path)).slides
        for issue in slide.lint().issues
    ]


def _overlap(slide, names=("Card A", "Card B")):
    """Add two rectangles that partly overlap: a ShapeCollision warning."""
    for name, offset in zip(names, (0, 1)):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(2 + offset), Inches(2 + offset), Inches(3), Inches(2)
        )
        shape.name = name


@pytest.fixture
def clean_deck(tmp_path: Path) -> Path:
    """A deck the linter has nothing to say about."""
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.slides.add_slide(prs.slide_layouts[6])
    path = tmp_path / "clean.pptx"
    prs.save(str(path))
    assert _severities(path) == []
    return path


@pytest.fixture
def warning_deck(tmp_path: Path) -> Path:
    """A deck whose only issue is a warning."""
    prs = Presentation()
    _overlap(prs.slides.add_slide(prs.slide_layouts[6]))
    path = tmp_path / "warning.pptx"
    prs.save(str(path))
    assert _severities(path) == ["warning"]
    return path


@pytest.fixture
def info_deck(tmp_path: Path) -> Path:
    """A deck whose only issues are informational: two shapes stacked exactly."""
    prs = Presentation()
    for _ in range(2):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(3), Inches(2))
        slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1), Inches(1), Inches(3), Inches(2))
    path = tmp_path / "info.pptx"
    prs.save(str(path))
    assert _severities(path) == ["info", "info"]
    return path


@pytest.fixture
def error_deck(tmp_path: Path) -> Path:
    """A deck with an error `tidy()` can fix on slide 1 and a warning it cannot on slide 3.

    Slide 1 has a title, slide 2 is clean and slide 3 is hidden, so that the
    report has something to say about each.
    """
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[5])
    first.shapes.title.text_frame.text = "Quarterly   review"
    runaway = first.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(9), Inches(3), Inches(3), Inches(1)
    )
    runaway.name = "Runaway"
    prs.slides.add_slide(prs.slide_layouts[6])
    third = prs.slides.add_slide(prs.slide_layouts[6])
    _overlap(third)
    third.hidden = True
    path = tmp_path / "error.pptx"
    prs.save(str(path))
    assert _severities(path) == ["error", "warning"]
    return path


@pytest.fixture
def run(capsys):
    """Run `power-pptx lint` with the given arguments; return (status, stdout, stderr)."""

    def _run(*args):
        capsys.readouterr()
        status = main([str(arg) for arg in args])
        captured = capsys.readouterr()
        return status, captured.out, captured.err

    return _run


def _reports(path: Path, **lint_kwargs):
    return [slide.lint(**lint_kwargs) for slide in Presentation(str(path)).slides]


# ---------------------------------------------------------------------------
# exit status
# ---------------------------------------------------------------------------


class DescribeLintCommandExitStatus(object):
    """0 clean, 1 issues at or above the fail level, 2 usage error or unreadable file."""

    def it_names_its_three_exit_statuses(self):
        assert (EXIT_CLEAN, EXIT_ISSUES, EXIT_USAGE) == (0, 1, 2)

    def it_exits_0_for_a_clean_deck(self, run, clean_deck):
        assert run(clean_deck)[0] == 0

    def it_exits_1_for_a_deck_with_an_error(self, run, error_deck):
        assert run(error_deck)[0] == 1

    def it_fails_on_errors_only_by_default(self, run, warning_deck):
        assert run(warning_deck)[0] == 0
        assert run(warning_deck, "--fail-on", "error")[0] == 0

    def it_can_fail_on_warnings_too(self, run, warning_deck, error_deck, clean_deck):
        assert run(warning_deck, "--fail-on", "warning")[0] == 1
        assert run(error_deck, "--fail-on", "warning")[0] == 1
        assert run(clean_deck, "--fail-on", "warning")[0] == 0

    def it_never_fails_on_informational_issues(self, run, info_deck):
        assert run(info_deck)[0] == 0
        assert run(info_deck, "--fail-on", "warning")[0] == 0

    def it_can_be_told_never_to_fail(self, run, error_deck):
        status, out, _ = run(error_deck, "--fail-on", "never")
        assert status == 0
        # -- the issues are still reported --
        assert "OffSlide" in out

    def it_does_not_count_issues_below_the_minimum_severity(self, run, warning_deck):
        status, out, _ = run(warning_deck, "--min-severity", "error", "--fail-on", "warning")
        assert status == 0
        assert "ShapeCollision" not in out

    def it_exits_1_if_any_one_of_several_decks_fails(self, run, clean_deck, error_deck):
        assert run(clean_deck, error_deck)[0] == 1
        assert run(error_deck, clean_deck)[0] == 1

    def it_returns_the_status_rather_than_raising_SystemExit(self, clean_deck, capsys):
        assert main([str(clean_deck)]) == 0
        assert main([]) == 2
        assert main(["--help"]) == 0
        capsys.readouterr()

    def it_is_the_exit_status_of_the_installed_command(self, error_deck, clean_deck):
        """`python -m power_pptx` is what the `power-pptx` console script runs."""
        src = str(Path(power_pptx.__file__).parent.parent)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [src, env.get("PYTHONPATH")]))

        def status(*args: str) -> int:
            command = [sys.executable, "-m", "power_pptx", "lint", *args]
            return subprocess.run(command, env=env, capture_output=True, timeout=120).returncode

        assert status(str(clean_deck)) == 0
        assert status(str(error_deck)) == 1
        assert status(str(error_deck), "--fail-on", "never") == 0
        assert status(str(error_deck.with_name("missing.pptx"))) == 2
        assert status("--format", "yaml", str(clean_deck)) == 2


# ---------------------------------------------------------------------------
# usage errors and unreadable decks
# ---------------------------------------------------------------------------


class DescribeLintCommandUsageErrors(object):
    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["--format", "yaml", "deck.pptx"],
            ["--fail-on", "info", "deck.pptx"],
            ["--min-severity", "fatal", "deck.pptx"],
            ["--no-such-option", "deck.pptx"],
        ],
    )
    def it_exits_2_for_a_command_line_it_does_not_understand(self, run, args):
        status, out, err = run(*args)

        assert status == 2
        assert out == ""
        assert "usage: power-pptx lint" in err

    def it_explains_itself_with_help(self, run):
        status, out, err = run("--help")

        assert status == 0
        assert err == ""
        options = ("--format", "--min-severity", "--fail-on", "--fix", "--output", "--in-place")
        for option in options:
            assert option in out
        assert "exit status:" in out

    def it_exits_2_for_a_file_that_is_not_there(self, run, tmp_path):
        missing = tmp_path / "missing.pptx"

        status, out, err = run(missing)

        assert status == 2
        assert out == ""
        assert err == "power-pptx lint: cannot read %s: no such file\n" % missing

    def it_exits_2_for_a_file_that_is_not_a_deck(self, run, tmp_path):
        impostor = tmp_path / "notes.pptx"
        impostor.write_text("not a zip file")

        status, _, err = run(impostor)

        assert status == 2
        assert "cannot read %s: not a .pptx file" % impostor in err

    def it_exits_2_for_a_directory(self, run, tmp_path):
        status, _, err = run(tmp_path)

        assert status == 2
        assert "cannot read %s: it is a directory" % tmp_path in err

    def it_exits_2_for_a_zip_package_that_is_not_a_presentation(self, run, tmp_path):
        import zipfile

        other = tmp_path / "archive.pptx"
        with zipfile.ZipFile(other, "w") as zf:
            zf.writestr("hello.txt", "hello")

        status, _, err = run(other)

        assert status == 2
        assert "cannot read %s" % other in err

    def it_still_reports_the_decks_it_could_read(self, run, tmp_path, error_deck):
        missing = tmp_path / "missing.pptx"

        status, out, err = run(missing, error_deck)

        # -- unreadable outranks "has issues" --
        assert status == 2
        assert "OffSlide" in out
        assert "1 deck checked" in out
        assert "1 deck could not be checked" in out
        assert "cannot read %s" % missing in err

    def it_exits_2_even_when_told_never_to_fail(self, run, tmp_path):
        assert run(tmp_path / "missing.pptx", "--fail-on", "never")[0] == 2

    def it_exits_2_when_a_slide_cannot_be_linted(self, run, clean_deck, monkeypatch):
        from power_pptx.slide import Slide

        def boom(self, **kwargs):
            raise RuntimeError("shape tree\n is corrupt")

        monkeypatch.setattr(Slide, "lint", boom)

        status, out, err = run(clean_deck)

        assert status == 2
        assert out == ""
        assert err == (
            "power-pptx lint: cannot lint %s: RuntimeError: shape tree is corrupt\n" % clean_deck
        )


# ---------------------------------------------------------------------------
# the default, human-readable report
# ---------------------------------------------------------------------------


class DescribeLintCommandTextReport(object):
    def it_says_so_when_a_deck_is_clean(self, run, clean_deck):
        status, out, err = run(clean_deck)

        assert (status, err) == (0, "")
        assert out == "%s: no issues (2 slides)\n" % clean_deck

    def it_groups_the_issues_by_slide(self, run, error_deck):
        _, out, _ = run(error_deck)
        lines = out.splitlines()

        assert lines[0] == "%s: 2 issues on 2 of 3 slides (1 error, 1 warning)" % error_deck
        first = lines.index("  Slide 1: Quarterly review")
        third = lines.index("  Slide 3 (hidden)")
        assert first < third
        # -- each issue sits under its own slide, severity then code then message --
        assert lines[first + 1].split()[:2] == ["error", "OffSlide"]
        assert lines[third + 1].split()[:2] == ["warning", "ShapeCollision"]
        assert "Runaway" in lines[first + 1]
        assert "Card A" in lines[third + 1]
        # -- and a slide with nothing wrong is not listed --
        assert not any(line.strip().startswith("Slide 2") for line in lines)

    def it_prints_the_linters_own_messages(self, run, error_deck):
        _, out, _ = run(error_deck)

        for report in _reports(error_deck):
            for issue in report.issues:
                assert issue.message in out
                assert issue.code in out

    def it_leaves_out_issues_below_the_minimum_severity(self, run, error_deck):
        _, out, _ = run(error_deck, "--min-severity", "error")

        assert out.splitlines()[0] == "%s: 1 issue on 1 of 3 slides (1 error)" % error_deck
        assert "OffSlide" in out
        assert "ShapeCollision" not in out
        assert "Slide 3" not in out

    def it_reports_each_deck_and_a_total_for_several(
        self, run, clean_deck, warning_deck, error_deck
    ):
        status, out, _ = run(clean_deck, warning_deck, error_deck)
        lines = out.splitlines()

        assert status == 1
        headlines = [line for line in lines if line and not line.startswith(" ")]
        assert headlines == [
            "%s: no issues (2 slides)" % clean_deck,
            "%s: 1 issue on 1 of 1 slide (1 warning)" % warning_deck,
            "%s: 2 issues on 2 of 3 slides (1 error, 1 warning)" % error_deck,
            "3 decks checked: 3 issues (1 error, 2 warnings)",
        ]

    def it_counts_informational_issues_too(self, run, info_deck):
        _, out, _ = run(info_deck)

        assert out.splitlines()[0] == "%s: 2 issues on 2 of 2 slides (2 info)" % info_deck
        assert run(info_deck, "--min-severity", "warning")[1] == (
            "%s: no issues (2 slides)\n" % info_deck
        )

    def it_handles_a_deck_with_no_slides(self, run, tmp_path):
        path = tmp_path / "empty.pptx"
        Presentation().save(str(path))

        status, out, _ = run(path)

        assert status == 0
        assert out == "%s: no slides\n" % path

    def it_survives_a_console_that_cannot_print_a_shape_name(self, tmp_path, monkeypatch):
        prs = Presentation()
        _overlap(prs.slides.add_slide(prs.slide_layouts[6]), names=("Größe", "図形"))
        path = tmp_path / "names.pptx"
        prs.save(str(path))
        raw = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii"))

        status = main([str(path)])
        sys.stdout.flush()

        assert status == 0
        text = raw.getvalue().decode("ascii")
        assert "ShapeCollision" in text
        assert "Gr\\xf6\\xdfe" in text


# ---------------------------------------------------------------------------
# --format json
# ---------------------------------------------------------------------------


class DescribeLintCommandJsonReport(object):
    def it_writes_one_json_document(self, run, error_deck):
        status, out, err = run(error_deck, "--format", "json")
        document = json.loads(out)

        assert (status, err) == (1, "")
        assert sorted(document) == [
            "counts",
            "decks",
            "exit_code",
            "fail_on",
            "issue_count",
            "min_severity",
        ]
        assert document["exit_code"] == 1
        assert document["fail_on"] == "error"
        assert document["min_severity"] == "info"
        assert document["issue_count"] == 2
        assert document["counts"] == {"error": 1, "warning": 1, "info": 0}

    def it_describes_each_deck_slide_by_slide(self, run, error_deck):
        _, out, _ = run(error_deck, "--format", "json")
        (deck,) = json.loads(out)["decks"]

        assert deck["path"] == str(error_deck)
        assert deck["slide_count"] == 3
        assert deck["issue_count"] == 2
        assert deck["counts"] == {"error": 1, "warning": 1, "info": 0}
        assert deck["has_errors"] is True
        assert [
            (s["index"], s["number"], s["title"], s["hidden"], s["issue_count"])
            for s in deck["slides"]
        ] == [(0, 1, "Quarterly review", False, 1), (1, 2, None, False, 0), (2, 3, None, True, 1)]

    def it_reuses_the_lint_reports_own_serialisation(self, run, error_deck):
        _, out, _ = run(error_deck, "--format", "json")
        (deck,) = json.loads(out)["decks"]

        for slide, report in zip(deck["slides"], _reports(error_deck)):
            expected = json.loads(report.to_json())
            assert {key: slide[key] for key in expected} == expected

    def it_applies_the_minimum_severity(self, run, error_deck):
        _, out, _ = run(error_deck, "--format", "json", "--min-severity", "warning")
        document = json.loads(out)
        (deck,) = document["decks"]

        assert document["min_severity"] == "warning"
        for slide, report in zip(deck["slides"], _reports(error_deck, min_severity="warning")):
            assert slide["issues"] == json.loads(report.to_json())["issues"]

    def it_records_the_fail_level_and_the_resulting_status(self, run, warning_deck):
        relaxed = json.loads(run(warning_deck, "--format", "json")[1])
        strict = json.loads(run(warning_deck, "--format", "json", "--fail-on", "warning")[1])

        assert (relaxed["fail_on"], relaxed["exit_code"]) == ("error", 0)
        assert (strict["fail_on"], strict["exit_code"]) == ("warning", 1)

    def it_keeps_the_document_valid_when_a_deck_cannot_be_read(self, run, tmp_path, clean_deck):
        missing = tmp_path / "missing.pptx"

        status, out, err = run(missing, clean_deck, "--format", "json")
        document = json.loads(out)

        assert status == 2
        assert document["exit_code"] == 2
        assert document["decks"][0] == {
            "path": str(missing),
            "error": "cannot read %s: no such file" % missing,
        }
        assert document["decks"][1]["path"] == str(clean_deck)
        assert document["decks"][1]["issue_count"] == 0
        assert "cannot read" in err


# ---------------------------------------------------------------------------
# --format sarif
# ---------------------------------------------------------------------------


class DescribeLintCommandSarifReport(object):
    def it_writes_the_linters_own_sarif_for_the_deck(self, run, error_deck):
        status, out, err = run(error_deck, "--format", "sarif")
        document = json.loads(out)

        assert (status, err) == (1, "")
        expected = lint_report_to_sarif(_reports(error_deck))
        assert document["version"] == expected["version"] == "2.1.0"
        assert document["$schema"] == expected["$schema"]
        (run_,) = document["runs"]
        (expected_run,) = expected["runs"]
        assert run_["tool"] == expected_run["tool"]
        assert run_["results"] == expected_run["results"]
        assert [r["ruleId"] for r in run_["results"]] == ["OffSlide", "ShapeCollision"]
        assert [r["level"] for r in run_["results"]] == ["error", "warning"]

    def it_adds_only_the_name_of_the_deck(self, run, error_deck):
        _, out, _ = run(error_deck, "--format", "sarif")
        (run_,) = json.loads(out)["runs"]
        (expected_run,) = lint_report_to_sarif(_reports(error_deck))["runs"]

        added = {key: value for key, value in run_.items() if key not in expected_run}
        name = error_deck.as_posix()
        assert added == {
            "automationDetails": {"id": "power-pptx-lint/%s/" % name.lstrip("/")},
            "properties": {"deck": name},
        }

    def it_has_a_run_for_each_deck(self, run, clean_deck, warning_deck, error_deck):
        status, out, _ = run(clean_deck, warning_deck, error_deck, "--format", "sarif")
        document = json.loads(out)

        assert status == 1
        assert [r["properties"]["deck"] for r in document["runs"]] == [
            clean_deck.as_posix(),
            warning_deck.as_posix(),
            error_deck.as_posix(),
        ]
        assert [len(r["results"]) for r in document["runs"]] == [0, 1, 2]
        ids = [r["automationDetails"]["id"] for r in document["runs"]]
        assert len(set(ids)) == 3

    def it_applies_the_minimum_severity(self, run, error_deck):
        _, out, _ = run(error_deck, "--format", "sarif", "--min-severity", "error")
        (run_,) = json.loads(out)["runs"]
        assert [r["ruleId"] for r in run_["results"]] == ["OffSlide"]

    def it_is_still_a_sarif_log_when_nothing_could_be_read(self, run, tmp_path):
        status, out, err = run(tmp_path / "missing.pptx", "--format", "sarif")
        document = json.loads(out)

        assert status == 2
        assert document["version"] == "2.1.0"
        assert document["runs"] == []
        assert "cannot read" in err


# ---------------------------------------------------------------------------
# --fix
# ---------------------------------------------------------------------------


class DescribeLintCommandFix(object):
    def it_writes_a_tidied_copy_and_leaves_the_input_alone(self, run, error_deck, tmp_path):
        original = error_deck.read_bytes()
        tidied = tmp_path / "out" / "tidied.pptx"

        status, out, err = run(error_deck, "--fix", "--output", tidied)

        # -- the error was fixable, so only the warning is left --
        assert (status, err) == (0, "")
        assert error_deck.read_bytes() == original
        assert _severities(tidied) == ["warning"]
        lines = out.splitlines()
        assert lines[0] == (
            "%s: 1 fix applied, 1 issue left on 1 of 3 slides (1 warning); written to %s"
            % (error_deck, tidied)
        )
        first = lines.index("  Slide 1: Quarterly review")
        assert lines[first + 1].split()[0] == "fixed"
        assert "Runaway" in lines[first + 1]
        assert "OffSlide" not in out

    def it_reports_and_judges_what_is_left_after_fixing(self, run, error_deck, tmp_path):
        tidied = tmp_path / "tidied.pptx"

        assert run(error_deck, "--fix", "-o", tidied, "--fail-on", "warning")[0] == 1
        assert run(error_deck, "--fix", "-o", tidied, "--fail-on", "error")[0] == 0

    def it_applies_the_fixes_tidy_applies(self, run, error_deck, tmp_path):
        tidied = tmp_path / "tidied.pptx"
        expected = Presentation(str(error_deck))
        expected_fixes = [slide.tidy() for slide in expected.slides]

        _, out, _ = run(error_deck, "--fix", "--output", tidied, "--format", "json")
        (deck,) = json.loads(out)["decks"]

        assert [slide["fixes"] for slide in deck["slides"]] == expected_fixes
        assert deck["fix_count"] == sum(len(fixes) for fixes in expected_fixes) == 1
        assert deck["output"] == str(tidied)
        actual = Presentation(str(tidied))
        assert [(s.left, s.top) for s in actual.slides[0].shapes] == [
            (s.left, s.top) for s in expected.slides[0].shapes
        ]

    def it_writes_the_copy_even_when_there_was_nothing_to_fix(self, run, clean_deck, tmp_path):
        tidied = tmp_path / "tidied.pptx"

        status, out, _ = run(clean_deck, "--fix", "--output", tidied)

        assert status == 0
        assert out == "%s: 0 fixes applied, no issues left (2 slides); written to %s\n" % (
            clean_deck,
            tidied,
        )
        assert len(Presentation(str(tidied)).slides) == 2

    def it_can_overwrite_the_deck_when_asked_to(self, run, error_deck):
        status, out, _ = run(error_deck, "--fix", "--in-place")

        assert status == 0
        assert _severities(error_deck) == ["warning"]
        assert out.splitlines()[0].endswith("; written to %s" % error_deck)

    def but_it_does_not_rewrite_a_deck_that_needed_no_fixing(self, run, warning_deck):
        original = warning_deck.read_bytes()
        modified = os.stat(str(warning_deck)).st_mtime_ns

        status, out, _ = run(warning_deck, "--fix", "--in-place")

        assert status == 0
        assert warning_deck.read_bytes() == original
        assert os.stat(str(warning_deck)).st_mtime_ns == modified
        assert "written to" not in out

    def it_writes_several_decks_into_an_output_directory(
        self, run, clean_deck, warning_deck, error_deck, tmp_path
    ):
        target = tmp_path / "tidied"

        status, _, err = run(clean_deck, warning_deck, error_deck, "--fix", "--output", target)

        assert (status, err) == (0, "")
        assert sorted(p.name for p in target.iterdir()) == [
            "clean.pptx",
            "error.pptx",
            "warning.pptx",
        ]
        assert _severities(target / "error.pptx") == ["warning"]
        # -- and nothing else was left behind in the directory or beside the inputs --
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "clean.pptx",
            "error.pptx",
            "tidied",
            "warning.pptx",
        ]

    def it_treats_an_existing_directory_as_the_place_for_one_deck_too(
        self, run, error_deck, tmp_path
    ):
        target = tmp_path / "tidied"
        target.mkdir()

        status, _, _ = run(error_deck, "--fix", "--output", target)

        assert status == 0
        assert _severities(target / "error.pptx") == ["warning"]

    def and_a_path_ending_in_a_separator(self, run, error_deck, tmp_path):
        target = tmp_path / "new"

        status, _, _ = run(error_deck, "--fix", "--output", str(target) + os.sep)

        assert status == 0
        assert _severities(target / "error.pptx") == ["warning"]

    def it_writes_through_a_symbolic_link_rather_than_replacing_it(
        self, run, error_deck, tmp_path
    ):
        if os.name == "nt":
            pytest.skip("symbolic links need privileges on Windows")
        link = tmp_path / "link.pptx"
        link.symlink_to(error_deck)

        status, _, _ = run(link, "--fix", "--in-place")

        assert status == 0
        assert link.is_symlink()
        assert _severities(error_deck) == ["warning"]

    def it_keeps_the_permissions_of_a_deck_it_overwrites(self, run, error_deck):
        if os.name == "nt":
            pytest.skip("POSIX permission bits")
        os.chmod(str(error_deck), 0o640)

        run(error_deck, "--fix", "--in-place")

        assert os.stat(str(error_deck)).st_mode & 0o777 == 0o640

    @pytest.mark.parametrize(
        ("extra", "complaint"),
        [
            (["--fix"], "--fix needs somewhere to write the result"),
            (["--fix", "--output", "{deck}"], "--output would overwrite"),
            (["--fix", "--output", "{dir}/./error.pptx"], "--output would overwrite"),
            (["--fix", "--output", "{dir}/x.pptx", "--in-place"], "not both"),
            (["--output", "{dir}/x.pptx"], "only apply with --fix"),
            (["--in-place"], "only apply with --fix"),
        ],
    )
    def it_refuses_a_fix_that_could_overwrite_the_input_by_accident(
        self, run, error_deck, tmp_path, extra, complaint
    ):
        original = error_deck.read_bytes()
        args = [arg.format(deck=error_deck, dir=tmp_path) for arg in extra]

        status, out, err = run(error_deck, *args)

        assert status == 2
        assert out == ""
        assert complaint in err
        assert error_deck.read_bytes() == original
        assert sorted(p.name for p in tmp_path.iterdir()) == ["error.pptx"]

    def it_refuses_to_write_two_decks_of_the_same_name_to_one_directory(
        self, run, error_deck, tmp_path
    ):
        other = tmp_path / "other"
        other.mkdir()
        twin = other / error_deck.name
        twin.write_bytes(error_deck.read_bytes())

        status, _, err = run(error_deck, twin, "--fix", "--output", tmp_path / "out")

        assert status == 2
        assert "different file names" in err
        assert not (tmp_path / "out").exists()

    def it_refuses_a_file_as_the_output_for_several_decks(self, run, clean_deck, error_deck):
        status, _, err = run(clean_deck, error_deck, "--fix", "--output", clean_deck)

        assert status == 2
        assert "a directory is needed" in err

    def it_refuses_an_output_directory_that_holds_an_input(self, run, clean_deck, error_deck):
        original = error_deck.read_bytes()

        status, _, err = run(clean_deck, error_deck, "--fix", "--output", error_deck.parent)

        assert status == 2
        assert "--output would overwrite" in err
        assert error_deck.read_bytes() == original

    def it_exits_2_and_keeps_the_original_when_the_copy_cannot_be_written(
        self, run, error_deck, tmp_path, monkeypatch
    ):
        original = error_deck.read_bytes()

        def no_space(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(lint_cli.os, "replace", no_space)

        status, out, err = run(error_deck, "--fix", "--in-place")

        assert status == 2
        assert "cannot write %s" % error_deck in err
        assert "No space left on device" in err
        assert error_deck.read_bytes() == original
        # -- the findings are still reported, and no scratch file is left behind --
        assert "Slide 1" in out
        assert sorted(p.name for p in tmp_path.iterdir()) == ["error.pptx"]


# ---------------------------------------------------------------------------
# the `power-pptx` entry point and the module's dependencies
# ---------------------------------------------------------------------------


class DescribePowerPptxCommand(object):
    def it_dispatches_the_lint_subcommand(self, capsys, clean_deck, error_deck):
        assert power_pptx_main(["lint", str(clean_deck)]) == 0
        assert power_pptx_main(["lint", str(error_deck)]) == 1
        assert power_pptx_main(["lint", str(error_deck), "--fail-on", "never"]) == 0
        assert power_pptx_main(["lint"]) == 2
        out = capsys.readouterr().out
        assert "%s: no issues (2 slides)" % clean_deck in out

    @pytest.mark.parametrize("args", [[], ["-h"], ["--help"]])
    def it_lists_both_subcommands_in_its_help(self, capsys, args):
        assert power_pptx_main(args) == 0
        out = capsys.readouterr().out
        assert "lint" in out
        assert "review" in out
        assert "power-pptx lint --help" in out

    def it_still_rejects_an_unknown_command(self, capsys):
        assert power_pptx_main(["frobnicate"]) == 2
        assert "Unknown command: frobnicate" in capsys.readouterr().err


class DescribeLintCliModule(object):
    def it_uses_only_the_public_surface_of_the_linter(self):
        """The linter's internals are being reworked; the command must not reach into them."""
        tree = ast.parse(Path(lint_cli.__file__).read_text(encoding="utf-8"))
        imported = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "power_pptx.lint"
            for alias in node.names
        ]
        assert imported == ["lint_report_to_sarif"]
        # -- no `report._issues`, `slide._element` and the like either --
        private = [
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr.startswith("_")
            and not node.attr.endswith("__")
        ]
        assert private == []
