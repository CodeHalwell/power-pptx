"""Bundled Claude Code skill for power-pptx.

Ships the ``SKILL.md`` and reference markdown that drive the Claude
Code (and Claude Agent SDK) ``power-pptx`` skill, so that pip-installing
power-pptx is enough to make the skill available wherever the library
runs.

Typical usage from a shell::

    # Install into the current user's Claude skills directory
    python -m power_pptx.skill install

    # Or just print where the skill files live inside the package
    python -m power_pptx.skill path

Programmatic usage::

    from power_pptx.skill import skill_root, install_skill

    src = skill_root()                  # pathlib.Path inside the package
    dest = install_skill()              # default: ~/.claude/skills/power-pptx
    dest = install_skill(target="/some/other/dir/power-pptx")

*target* is the directory the skill itself lives in (the one that holds
``SKILL.md``), not the parent ``skills/`` directory.  An existing
directory is only ever replaced when it is empty or is recognisably a
previous install of this skill; anything else is refused.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Union

__all__ = ["skill_root", "install_skill", "DEFAULT_INSTALL_DIR", "SKILL_NAME"]


#: The ``name:`` this skill declares in its ``SKILL.md`` front matter.  It is
#: also how a previous install is recognised before it is replaced.
SKILL_NAME = "power-pptx"

#: Default destination directory for ``install_skill``.
#:
#: Matches the convention that Claude Code uses for user-level skills.
#: Override by passing ``target=`` to :func:`install_skill`.
DEFAULT_INSTALL_DIR = Path.home() / ".claude" / "skills" / SKILL_NAME


def skill_root() -> Path:
    """Return the directory inside the installed package that holds the skill.

    Contains ``SKILL.md`` and a ``references/`` subdirectory.  This is
    a regular filesystem path even when the package is installed inside
    a wheel, because setuptools copies ``package_data`` files onto disk.
    """
    return Path(__file__).resolve().parent


def install_skill(
    target: Optional[Union[str, os.PathLike[str]]] = None, *, overwrite: bool = True
) -> Path:
    """Copy the bundled skill to *target* (default :data:`DEFAULT_INSTALL_DIR`).

    *target* is the skill directory itself — the one that will contain
    ``SKILL.md`` — not the ``skills/`` directory it sits in.  Returns the
    destination directory.

    When *overwrite* is ``True`` (the default), a previous install of this
    skill at *target* is replaced; pass ``overwrite=False`` to raise
    :class:`FileExistsError` whenever *target* already exists.

    Nothing other than a previous install is ever deleted.  An existing
    *target* is replaced only when it is an empty directory or a directory
    whose ``SKILL.md`` declares ``name: power-pptx``.  Otherwise the call
    changes nothing and raises:

    * :class:`NotADirectoryError` when *target* is a file;
    * :class:`FileExistsError` when *target* is a symbolic link, or a
      non-empty directory that is not an install of this skill (for
      example the ``skills/`` directory itself, which holds other skills).
    """
    src = skill_root()
    dest = Path(target) if target is not None else DEFAULT_INSTALL_DIR

    if dest.is_symlink() or dest.exists():
        if not overwrite:
            raise FileExistsError(
                f"refusing to overwrite existing skill at {dest!s}; "
                "pass overwrite=True or remove it first"
            )
        _require_replaceable(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Build the new copy next to the destination and only then swap it in, so
    # a copy that fails part-way never leaves a half-written (or missing)
    # skill where a working one used to be.
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent))
    try:
        # Copy SKILL.md and references/ but not __init__.py / __main__.py.
        shutil.copy2(src / "SKILL.md", staging / "SKILL.md")
        refs_src = src / "references"
        if refs_src.is_dir():
            shutil.copytree(refs_src, staging / "references")
        # mkdtemp creates the directory 0700; a skill directory is ordinary
        # user content, so give it the permissions `mkdir` would have.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(staging, 0o777 & ~umask)

        if dest.exists():
            shutil.rmtree(dest)
        os.replace(staging, dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return dest


def _require_replaceable(dest: Path) -> None:
    """Raise unless the existing *dest* may safely be replaced by an install.

    Only an empty directory or a previous install of this skill qualifies.
    This is what stops ``install ~/.claude/skills`` (the parent directory,
    an easy slip) from deleting every other skill the user has.
    """
    if dest.is_symlink():
        raise FileExistsError(
            f"refusing to replace {dest!s}: it is a symbolic link. "
            "Remove the link, or install into the directory it points at."
        )
    if not dest.is_dir():
        raise NotADirectoryError(
            f"cannot install the skill at {dest!s}: it is a file, not a directory. "
            "Pass the directory the skill should live in "
            f"(for example {DEFAULT_INSTALL_DIR!s})."
        )
    if _is_previous_install(dest) or not any(dest.iterdir()):
        return
    raise FileExistsError(
        f"refusing to replace {dest!s}: it is not empty and is not a "
        f"{SKILL_NAME} skill install, so replacing it would delete unrelated files. "
        f"The target is the skill's own directory, for example {dest / SKILL_NAME!s}."
    )


def _is_previous_install(dest: Path) -> bool:
    """True when *dest* holds a ``SKILL.md`` that declares this skill's name."""
    skill_md = dest / "SKILL.md"
    if skill_md.is_symlink() or not skill_md.is_file():
        return False
    try:
        with skill_md.open(encoding="utf-8-sig", errors="replace") as f:
            head = [next(f, "") for _ in range(40)]
    except OSError:
        return False
    if not head or head[0].strip() != "---":
        return False
    for line in head[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        key, sep, value = stripped.partition(":")
        if sep and key.strip() == "name":
            return value.strip().strip("'\"") == SKILL_NAME
    return False
