"""Command-line entry point for the bundled Claude skill.

Usage::

    python -m power_pptx.skill install [TARGET]        # copy skill into target dir
    python -m power_pptx.skill install --target TARGET # same, spelled as an option
    python -m power_pptx.skill path                    # print on-disk skill source
    python -m power_pptx.skill                         # same as `path`

``TARGET`` is the directory the skill itself is installed as (it will hold
``SKILL.md``), not the ``skills/`` directory that contains it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from power_pptx.skill import DEFAULT_INSTALL_DIR, install_skill, skill_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m power_pptx.skill",
        description=(
            "Manage the bundled power-pptx Claude skill.  "
            "Ships SKILL.md and reference docs to your Claude skills directory."
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    install = sub.add_parser(
        "install",
        help="copy the bundled skill into a Claude skills directory",
        description=(
            "Copy the bundled skill into TARGET, the skill's own directory "
            f"(default: {DEFAULT_INSTALL_DIR}).  An existing TARGET is replaced only "
            "when it is empty or a previous install of this skill; any other "
            "directory or file is left untouched and the command fails."
        ),
    )
    install.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=None,
        help=f"destination directory (default: {DEFAULT_INSTALL_DIR})",
    )
    install.add_argument(
        "--target",
        dest="target_option",
        metavar="TARGET",
        type=Path,
        default=None,
        help="destination directory, as an option instead of a positional argument",
    )
    install.add_argument(
        "--no-overwrite",
        action="store_true",
        help="error out if the destination already exists",
    )

    sub.add_parser("path", help="print the package-internal skill directory")

    args = parser.parse_args(argv)

    if args.cmd == "install":
        if args.target is not None and args.target_option is not None:
            install.error("give the destination once: either TARGET or --target, not both")
        target = args.target if args.target is not None else args.target_option
        try:
            dest = install_skill(target, overwrite=not args.no_overwrite)
        except OSError as exc:
            # FileExistsError / NotADirectoryError carry a complete message of
            # their own; other OS errors (permissions, read-only filesystem)
            # already name the path.  Either way: no traceback, non-zero exit.
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"installed power-pptx skill -> {dest}")
        return 0

    # default + `path`
    print(skill_root())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
