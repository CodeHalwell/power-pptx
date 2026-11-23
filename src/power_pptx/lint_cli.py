"""``power-pptx lint`` — run the layout linter on decks from the command line.

A front end to :meth:`Slide.lint() <power_pptx.slide.Slide.lint>` for use in CI,
where a deck built by one job has to be checked by another without writing
Python::

    power-pptx lint deck.pptx                     # report, grouped by slide
    power-pptx lint build/*.pptx --fail-on warning
    power-pptx lint deck.pptx --format sarif > lint.sarif
    power-pptx lint deck.pptx --fix --output tidied.pptx
    power-pptx lint deck.pptx --fail-on-unmeasured   # no unchecked text either

The exit status is ``0`` when no issue at or above ``--fail-on`` was found,
``1`` when one was, and ``2`` for a usage error or a deck that could not be read
or written.

Only the linter's public surface is used: ``slide.lint()``, ``slide.tidy()``,
the report it returns and :func:`power_pptx.lint.lint_report_to_sarif`.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence, TextIO, cast

if TYPE_CHECKING:
    from power_pptx.presentation import Presentation as PresentationT
    from power_pptx.slide import Slide

#: No issue at or above the ``--fail-on`` level.
EXIT_CLEAN = 0
#: At least one issue at or above the ``--fail-on`` level.
EXIT_ISSUES = 1
#: The command line was wrong, or a deck could not be read or written.
EXIT_USAGE = 2

# -- most severe first, which is also the order the linter reports in --
_SEVERITIES: tuple[str, ...] = ("error", "warning", "info")
_RANK: dict[str, int] = {"info": 0, "warning": 1, "error": 2}

_PROG = "power-pptx lint"

_EPILOG = """\
exit status:
  0  no issue at or above the --fail-on level
  1  at least one issue at or above the --fail-on level, or, with
     --fail-on-unmeasured, text that could not be checked for overflow
  2  usage error, or a deck that could not be read or written

Issues below --min-severity are neither reported nor counted. With --fix the
report, and the exit status, describe what is left after fixing.
"""


@dataclass
class _SlideResult:
    """What the linter found on one slide."""

    index: int
    title: str | None
    hidden: bool
    report: Any  # a `power_pptx.lint.SlideLintReport`
    fixes: list[str] = field(default_factory=list[str])

    @property
    def issues(self) -> list[Any]:
        return list(self.report.issues)


@dataclass
class _DeckResult:
    """What the linter found in one deck, or why the deck could not be checked."""

    path: Path
    slides: list[_SlideResult] = field(default_factory=list[_SlideResult])
    #: Why this deck could not be read, linted or written; |None| when it could.
    error: str | None = None
    #: Where the tidied copy was written, when one was.
    output: Path | None = None

    @property
    def checked(self) -> bool:
        """True when this deck was linted, even if its tidied copy could not be written."""
        return self.error is None or bool(self.slides)

    @property
    def issues(self) -> list[Any]:
        return [issue for slide in self.slides for issue in slide.issues]

    @property
    def fix_count(self) -> int:
        return sum(len(slide.fixes) for slide in self.slides)


def _severity(issue: Any) -> str:
    """The severity of `issue` as one of "error", "warning" or "info"."""
    severity = issue.severity
    return str(getattr(severity, "value", severity)).lower()


def _counts(issues: Sequence[Any]) -> dict[str, int]:
    """Number of `issues` at each severity, most severe first."""
    counts = dict.fromkeys(_SEVERITIES, 0)
    for issue in issues:
        severity = _severity(issue)
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _plural(count: int, noun: str, plural: str | None = None) -> str:
    """Like "1 issue" or "3 issues"; `plural` for a noun that does not just take an "s"."""
    return "%d %s" % (count, noun if count == 1 else (plural or noun + "s"))


def _breakdown(counts: dict[str, int]) -> str:
    """Like "1 error, 2 warnings, 3 info", leaving out the severities with none."""
    return ", ".join(
        _plural(n, severity, "info" if severity == "info" else None)
        for severity, n in counts.items()
        if n
    )


def _slide_title(slide: Slide) -> str | None:
    """The text of the title placeholder of `slide` on one line, or |None|."""
    try:
        title = slide.shapes.title
        text = "" if title is None else title.text_frame.text
    except Exception:  # -- a label is not worth failing the run for --
        return None
    text = " ".join(text.split())
    if not text:
        return None
    return text if len(text) <= 60 else text[:57] + "..."


# ---------------------------------------------------------------------------
# linting
# ---------------------------------------------------------------------------


def _lint_presentation(prs: PresentationT, *, min_severity: str, fix: bool) -> list[_SlideResult]:
    """Lint every slide of `prs`, applying the safe automatic fixes first when `fix`."""
    results: list[_SlideResult] = []
    for index, slide in enumerate(prs.slides):
        fixes = list(slide.tidy()) if fix else []
        results.append(
            _SlideResult(
                index=index,
                title=_slide_title(slide),
                hidden=slide.hidden,
                report=slide.lint(min_severity=min_severity),
                fixes=fixes,
            )
        )
    return results


def _write_presentation(prs: PresentationT, target: Path) -> None:
    """Save `prs` as `target` without ever leaving a half-written file there.

    The deck is saved beside the target and then moved into place, so a failure
    at any point leaves an existing `target` as it was. The file it is saved to
    first ends in the target's extension, which is what chooses the kind of
    package written: a ``.potx`` stays a template and a ``.ppsx`` a slide show.
    """
    if target.is_symlink():
        # -- write through a link rather than replace it with a regular file --
        target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(".%s.%d.tmp%s" % (target.stem, os.getpid(), target.suffix))
    try:
        prs.save(str(scratch))
        if target.exists():
            shutil.copymode(str(target), str(scratch))
        os.replace(str(scratch), str(target))
    finally:
        if scratch.exists():
            scratch.unlink()


def _check_deck(path: Path, *, min_severity: str, fix: bool, output: Path | None) -> _DeckResult:
    """Lint the deck at `path`, writing a tidied copy to `output` when `fix`."""
    from power_pptx import Presentation

    result = _DeckResult(path)
    problem = _not_a_deck(path)
    if problem is not None:
        result.error = "cannot read %s: %s" % (path, problem)
        return result
    try:
        prs = Presentation(str(path))
    except Exception as exc:
        result.error = "cannot read %s: %s" % (path, _reason(exc))
        return result

    try:
        result.slides = _lint_presentation(prs, min_severity=min_severity, fix=fix)
    except Exception as exc:
        result.error = "cannot lint %s: %s" % (path, _reason(exc))
        return result

    if not fix or output is None:
        return result
    # -- a deck fixed in place is only rewritten when a fix changed it; a copy
    # -- asked for by name is always written, so that it is there to pick up --
    if _same_file(output, path) and not result.fix_count:
        return result
    try:
        _write_presentation(prs, output)
    except Exception as exc:
        result.error = "cannot write %s: %s" % (output, _reason(exc))
        return result
    result.output = output
    return result


def _not_a_deck(path: Path) -> str | None:
    """Why `path` cannot be a deck, where that can be told without opening it as one.

    The library reports every one of these as "Package not found", which is
    not much help when the file is there but is not a presentation.
    """
    if not path.exists():
        return "no such file"
    if path.is_dir():
        return "it is a directory"
    try:
        is_zip = zipfile.is_zipfile(str(path))
    except OSError as exc:
        return _reason(exc)
    return None if is_zip else "not a .pptx file (it is not a zip package)"


def _reason(exc: BaseException) -> str:
    """A one-line description of `exc` for an error message."""
    text = " ".join(str(exc).split())
    return "%s: %s" % (type(exc).__name__, text) if text else type(exc).__name__


def _same_file(a: Path, b: Path) -> bool:
    """True when `a` and `b` name the same file, whether or not either exists."""
    with contextlib.suppress(OSError):
        if a.exists() and b.exists():
            return a.samefile(b)
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------


def _deck_headline(deck: _DeckResult, *, fixed: bool) -> str:
    """The one-line summary of `deck` that heads its section of the text report."""
    slide_count = len(deck.slides)
    issues = deck.issues
    affected = sum(1 for slide in deck.slides if slide.issues)
    if not slide_count:
        found = "no slides"
    elif not issues:
        found = "no issues%s (%s)" % (" left" if fixed else "", _plural(slide_count, "slide"))
    else:
        found = "%s%s on %d of %s (%s)" % (
            _plural(len(issues), "issue"),
            " left" if fixed else "",
            affected,
            _plural(slide_count, "slide"),
            _breakdown(_counts(issues)),
        )
    if fixed:
        found = "%s applied, %s" % (_plural(deck.fix_count, "fix", "fixes"), found)
    if deck.output is not None:
        found += "; written to %s" % deck.output
    return "%s: %s" % (deck.path, found)


def _format_text(decks: Sequence[_DeckResult], *, fixed: bool) -> str:
    """The human-readable report: one section per deck, issues grouped by slide."""
    lines: list[str] = []
    checked = [deck for deck in decks if deck.checked]
    for deck in checked:
        if lines:
            lines.append("")
        lines.extend(_deck_section(deck, fixed=fixed))
    if len(decks) > 1:
        lines.extend(["", _run_total(decks, checked)])
    return "\n".join(lines) + "\n" if lines else ""


def _deck_section(deck: _DeckResult, *, fixed: bool) -> list[str]:
    """The text report's lines for `deck`: its headline, then each slide with something to say."""
    lines = [_deck_headline(deck, fixed=fixed)]
    width = max((len(str(issue.code)) for issue in deck.issues), default=0)
    for slide in deck.slides:
        if not slide.issues and not slide.fixes:
            continue
        lines.append("")
        lines.append("  " + _slide_label(slide))
        for description in slide.fixes:
            lines.append("    %-7s  %s" % ("fixed", description))
        for issue in slide.issues:
            lines.append(
                "    %-7s  %-*s  %s" % (_severity(issue), width, issue.code, issue.message)
            )
    return lines


def _slide_label(slide: _SlideResult) -> str:
    """Like "Slide 3: Quarterly results (hidden)", heading the slide's lines in the report."""
    label = "Slide %d" % (slide.index + 1)
    if slide.title:
        label += ": %s" % slide.title
    if slide.hidden:
        label += " (hidden)"
    return label


def _run_total(decks: Sequence[_DeckResult], checked: Sequence[_DeckResult]) -> str:
    """The line ending the report on several decks: what was found in all of them."""
    issues = [issue for deck in checked for issue in deck.issues]
    total = "%s checked: %s" % (
        _plural(len(checked), "deck"),
        "%s (%s)" % (_plural(len(issues), "issue"), _breakdown(_counts(issues)))
        if issues
        else "no issues",
    )
    unread = len(decks) - len(checked)
    if unread:
        total += "; %s could not be checked" % _plural(unread, "deck")
    return total


def _deck_to_dict(deck: _DeckResult, *, fixed: bool) -> dict[str, Any]:
    """The JSON form of `deck`; each slide is the lint report's own `to_dict()`."""
    if not deck.checked:
        return {"path": str(deck.path), "error": deck.error}
    slides: list[dict[str, Any]] = []
    for slide in deck.slides:
        entry: dict[str, Any] = {
            "index": slide.index,
            "number": slide.index + 1,
            "title": slide.title,
            "hidden": slide.hidden,
        }
        entry.update(slide.report.to_dict())
        if fixed:
            entry["fixes"] = list(slide.fixes)
        slides.append(entry)
    issues = deck.issues
    counts = _counts(issues)
    payload: dict[str, Any] = {
        "path": str(deck.path),
        "slide_count": len(deck.slides),
        "issue_count": len(issues),
        "counts": counts,
        "has_errors": bool(counts["error"]),
        "slides": slides,
    }
    if fixed:
        payload["fix_count"] = deck.fix_count
        payload["output"] = None if deck.output is None else str(deck.output)
    if deck.error is not None:
        payload["error"] = deck.error
    return payload


def _format_json(
    decks: Sequence[_DeckResult],
    *,
    fixed: bool,
    min_severity: str,
    fail_on: str,
    exit_code: int,
    fail_on_unmeasured: bool = False,
) -> str:
    """The whole run as one JSON document."""
    issues = [issue for deck in decks for issue in deck.issues]
    document = {
        "decks": [_deck_to_dict(deck, fixed=fixed) for deck in decks],
        "issue_count": len(issues),
        "counts": _counts(issues),
        "min_severity": min_severity,
        "fail_on": fail_on,
        "fail_on_unmeasured": fail_on_unmeasured,
        "unmeasured_count": sum(
            1 for issue in issues if getattr(issue, "code", None) == "TextUnmeasured"
        ),
        "exit_code": exit_code,
    }
    return json.dumps(document, indent=2) + "\n"


def _format_sarif(decks: Sequence[_DeckResult]) -> str:
    """The whole run as one SARIF 2.1.0 document, with a run for each deck.

    Each run is the linter's own SARIF for that deck. All this adds is the
    deck's name, which the linter does not know: as the run's
    ``automationDetails.id`` — what keeps the runs apart when several decks
    are uploaded together — and under ``properties.deck``.
    """
    from power_pptx.lint import lint_report_to_sarif

    document: dict[str, Any] | None = None
    for deck in decks:
        if not deck.checked:
            continue
        sarif = dict(lint_report_to_sarif([slide.report for slide in deck.slides]))
        runs = [dict(run) for run in _as_list(sarif.get("runs"))]
        for run in runs:
            name = deck.path.as_posix()
            run["automationDetails"] = {"id": "power-pptx-lint/%s/" % name.lstrip("/")}
            properties = dict(run.get("properties") or {})
            properties["deck"] = name
            run["properties"] = properties
        if document is None:
            document = sarif
            document["runs"] = runs
        else:
            _as_list(document["runs"]).extend(runs)
    if document is None:
        # -- nothing could be read: still a well-formed log, with no runs --
        document = dict(lint_report_to_sarif([]))
        document["runs"] = []
    return json.dumps(document, indent=2) + "\n"


def _as_list(value: Any) -> list[Any]:
    """`value` if it is a list, else an empty one."""
    return cast("list[Any]", value) if isinstance(value, list) else []


def _emit(stream: TextIO, text: str) -> None:
    """Write `text` to `stream`, escaping what its encoding cannot represent.

    Shape names are arbitrary text, and a CI log is not always UTF-8.
    """
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "backslashreplace").decode(encoding))
    stream.flush()


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Check .pptx decks for layout problems: text that overflows its box, "
        "shapes off the slide, unintended overlaps and the rest of what slide.lint() reports.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("decks", nargs="+", type=Path, metavar="DECK", help=".pptx file to check")
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif"),
        default="text",
        help="report format: a readable report grouped by slide (default), one JSON document, "
        "or SARIF 2.1.0 for code-scanning upload",
    )
    parser.add_argument(
        "--min-severity",
        choices=("info", "warning", "error"),
        default="info",
        help="leave issues below this severity out of the report (default: info, i.e. all)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="error",
        help="exit with status 1 if an issue of this severity or worse is found "
        "(default: error); 'never' always exits 0 for a deck that could be read",
    )
    parser.add_argument(
        "--fail-on-unmeasured",
        action="store_true",
        help="also exit with status 1 if a text frame holds text that could not be checked "
        "for overflow (the TextUnmeasured issue, which is only 'info'), so that a deck is "
        "not passed on the strength of text nothing measured; needs --min-severity info",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="apply the safe automatic fixes (slide.tidy()) and report what is left; "
        "needs --output or --in-place",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="with --fix, write the tidied deck here; a directory (created if need be) when "
        "several decks are given or PATH ends with a path separator",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="with --fix, overwrite each deck with its tidied version",
    )
    return parser


def _plan_outputs(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[Path | None]:
    """Return where each deck's tidied copy goes, or exit with a usage error.

    Everything about the destination is settled before a single deck is opened,
    so a mistake in the command cannot leave some decks rewritten and others not.
    """
    decks: list[Path] = args.decks
    if not args.fix:
        if args.output is not None or args.in_place:
            parser.error("--output and --in-place only apply with --fix")
        return [None] * len(decks)
    if args.output is not None and args.in_place:
        parser.error("choose --output or --in-place, not both")
    if args.in_place:
        return list(decks)
    if args.output is None:
        parser.error(
            "--fix needs somewhere to write the result: --output PATH for a tidied copy, "
            "or --in-place to overwrite the deck"
        )

    targets = _output_targets(parser, args.output, decks)
    _refuse_to_overwrite_a_deck(parser, targets, decks)
    return list(targets)


def _output_targets(parser: argparse.ArgumentParser, output: str, decks: list[Path]) -> list[Path]:
    """Where `--output` puts each tidied deck: at `output`, or by name in that directory."""
    path = Path(output)
    if not _is_output_directory(output, decks):
        return [path]
    if path.exists() and not path.is_dir():
        parser.error("--output %s is a file; a directory is needed here" % path)
    names = [deck.name for deck in decks]
    if len(set(names)) != len(names):
        parser.error("decks written to one --output directory must have different file names")
    return [path / name for name in names]


def _is_output_directory(output: str, decks: list[Path]) -> bool:
    """True when `--output` names a directory: for several decks, by its spelling, or as it is."""
    return len(decks) > 1 or output.endswith(("/", os.sep)) or Path(output).is_dir()


def _refuse_to_overwrite_a_deck(
    parser: argparse.ArgumentParser, targets: list[Path], decks: list[Path]
) -> None:
    """Exit with a usage error when a tidied copy would be written over any of the `decks`."""
    for target in targets:
        for deck in decks:
            if _same_file(target, deck):
                parser.error(
                    "--output would overwrite %s; use --in-place if that is what you want" % deck
                )


def _exit_code(decks: Sequence[_DeckResult], fail_on: str, fail_on_unmeasured: bool = False) -> int:
    if any(deck.error is not None for deck in decks):
        return EXIT_USAGE
    if fail_on_unmeasured and any(
        getattr(issue, "code", None) == "TextUnmeasured" for deck in decks for issue in deck.issues
    ):
        return EXIT_ISSUES
    if fail_on == "never":
        return EXIT_CLEAN
    threshold = _RANK[fail_on]
    for deck in decks:
        if any(_RANK.get(_severity(issue), 0) >= threshold for issue in deck.issues):
            return EXIT_ISSUES
    return EXIT_CLEAN


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``power-pptx lint`` with `argv` (default: ``sys.argv[1:]``); return the exit status."""
    parser = _build_parser()
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        if args.fail_on_unmeasured and args.min_severity != "info":
            # -- the issue it looks for is an 'info', which the filter would remove --
            parser.error("--fail-on-unmeasured needs --min-severity info (the default)")
        outputs = _plan_outputs(parser, args)
    except SystemExit as exit_:
        # -- argparse has already printed its message: 0 for --help, 2 for a mistake --
        code = exit_.code
        if code is None:
            return EXIT_CLEAN
        return code if isinstance(code, int) else EXIT_USAGE

    decks = [
        _check_deck(path, min_severity=args.min_severity, fix=args.fix, output=output)
        for path, output in zip(args.decks, outputs)
    ]
    exit_code = _exit_code(decks, args.fail_on, args.fail_on_unmeasured)

    if args.format == "json":
        report = _format_json(
            decks,
            fixed=args.fix,
            min_severity=args.min_severity,
            fail_on=args.fail_on,
            exit_code=exit_code,
            fail_on_unmeasured=args.fail_on_unmeasured,
        )
    elif args.format == "sarif":
        report = _format_sarif(decks)
    else:
        report = _format_text(decks, fixed=args.fix)
    _emit(sys.stdout, report)

    for deck in decks:
        if deck.error is not None:
            _emit(sys.stderr, "%s: %s\n" % (_PROG, deck.error))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
