"""Invariants the repository documents but nothing else enforces.

`AGENTS.md` asks contributors to keep several things in step by hand: the
shipped skill and its mirror, the packaged schemas and their specification
sources, and the version recorded in three places. Each has drifted in other
projects exactly because it was only a convention, so check them here.

These tests read files outside the installed package. They are skipped when
run from an sdist or an installed copy, where those files are not present.
"""

from __future__ import annotations

import filecmp
import re
from pathlib import Path

import pytest

import power_pptx

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "power_pptx" / "skill"
SKILL_MIRROR = REPO / ".claude" / "skills" / "power-pptx"
PACKAGED_XSD = REPO / "src" / "power_pptx" / "schemas"
SPEC_XSD = REPO / "spec" / "ISO-IEC-29500-4" / "xsd"
SITE_CONFIG = REPO / "site" / "src" / "lib" / "site.ts"
HISTORY = REPO / "HISTORY.rst"


def _require(*paths: Path) -> None:
    missing = [str(p.relative_to(REPO)) for p in paths if not p.exists()]
    if missing:
        pytest.skip("not a repository checkout: missing " + ", ".join(missing))


def _skill_documents(root: Path) -> dict[str, Path]:
    """Map relative path -> file for the Markdown that makes up the skill."""
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*.md"))}


class DescribeTheSkillMirror:
    """`.claude/skills/power-pptx` is what this repo's own sessions load;
    `src/power_pptx/skill` is what ships. They must say the same thing."""

    def it_holds_the_same_documents_as_the_packaged_skill(self):
        _require(SKILL, SKILL_MIRROR)

        packaged, mirror = _skill_documents(SKILL), _skill_documents(SKILL_MIRROR)

        assert sorted(mirror) == sorted(packaged)

    def it_matches_the_packaged_skill_byte_for_byte(self):
        _require(SKILL, SKILL_MIRROR)

        packaged, mirror = _skill_documents(SKILL), _skill_documents(SKILL_MIRROR)
        differing = [
            name
            for name in sorted(set(packaged) & set(mirror))
            if not filecmp.cmp(packaged[name], mirror[name], shallow=False)
        ]

        assert differing == [], (
            "the skill and its mirror differ; copy src/power_pptx/skill/ over "
            ".claude/skills/power-pptx/ for: " + ", ".join(differing)
        )


class DescribeThePackagedSchemas:
    """The XSDs that ship in the wheel are vendored from the ISO sources."""

    def it_ships_every_schema_unchanged_from_the_specification(self):
        _require(PACKAGED_XSD, SPEC_XSD)

        packaged = sorted(p.name for p in PACKAGED_XSD.glob("*.xsd"))
        differing = [
            name
            for name in packaged
            if not (SPEC_XSD / name).exists()
            or not filecmp.cmp(PACKAGED_XSD / name, SPEC_XSD / name, shallow=False)
        ]

        assert packaged, "no schemas are packaged"
        assert differing == []


class DescribeTheVersion:
    """`__version__` drives the release; two other files must agree with it."""

    def it_is_the_version_the_documentation_site_shows(self):
        _require(SITE_CONFIG)

        match = re.search(r'\bversion:\s*"([^"]+)"', SITE_CONFIG.read_text(encoding="utf-8"))

        assert match is not None, "no version field in site/src/lib/site.ts"
        assert match.group(1) == power_pptx.__version__

    def it_has_a_dated_section_in_the_changelog(self):
        """The release workflow lifts its notes from this exact heading."""
        _require(HISTORY)

        heading = re.compile(
            r"^" + re.escape(power_pptx.__version__) + r" \(\d{4}-\d{2}-\d{2}\)\n\++$",
            re.MULTILINE,
        )

        assert heading.search(HISTORY.read_text(encoding="utf-8")), (
            f"HISTORY.rst has no '{power_pptx.__version__} (YYYY-MM-DD)' section "
            "underlined with '+'"
        )

    def it_keeps_an_unreleased_section_above_the_releases(self):
        _require(HISTORY)

        text = HISTORY.read_text(encoding="utf-8")
        unreleased = re.search(r"^Unreleased\n\++$", text, re.MULTILINE)
        first_release = re.search(r"^\d+\.\d+\.\d+ \(\d{4}-\d{2}-\d{2}\)\n\++$", text, re.MULTILINE)

        assert unreleased is not None, "HISTORY.rst has no 'Unreleased' section"
        assert first_release is not None
        assert unreleased.start() < first_release.start()
