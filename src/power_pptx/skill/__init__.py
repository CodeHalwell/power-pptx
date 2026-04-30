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
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

__all__ = ["skill_root", "install_skill", "DEFAULT_INSTALL_DIR"]


#: Default destination directory for ``install_skill``.
#:
#: Matches the convention that Claude Code uses for user-level skills.
#: Override by passing ``target=`` to :func:`install_skill`.
DEFAULT_INSTALL_DIR = Path.home() / ".claude" / "skills" / "power-pptx"


def skill_root() -> Path:
    """Return the directory inside the installed package that holds the skill.

    Contains ``SKILL.md`` and a ``references/`` subdirectory.  This is
    a regular filesystem path even when the package is installed inside
    a wheel, because setuptools copies ``package_data`` files onto disk.
    """
    return Path(__file__).resolve().parent


def install_skill(
    target: Optional[Path] = None, *, overwrite: bool = True
) -> Path:
    """Copy the bundled skill to *target* (default :data:`DEFAULT_INSTALL_DIR`).

    Returns the destination directory.  When *overwrite* is ``True``
    (the default), an existing skill at *target* is replaced; pass
    ``overwrite=False`` to raise :class:`FileExistsError` instead.
    """
    src = skill_root()
    dest = Path(target) if target is not None else DEFAULT_INSTALL_DIR

    if dest.exists():
        if not overwrite:
            raise FileExistsError(
                f"refusing to overwrite existing skill at {dest!s}; "
                "pass overwrite=True or remove it first"
            )
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Copy SKILL.md and references/ but not __init__.py / __main__.py.
    dest.mkdir()
    shutil.copy2(src / "SKILL.md", dest / "SKILL.md")
    refs_src = src / "references"
    if refs_src.is_dir():
        shutil.copytree(refs_src, dest / "references")
    return dest
