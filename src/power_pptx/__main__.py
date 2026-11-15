"""Installed command line interface for authoring and review workflows."""

from __future__ import annotations

import sys

_USAGE = """\
Usage: power-pptx COMMAND ...

Commands:
  lint    DECK [DECK ...]                       check decks with the layout linter
  review  INPUT [INPUT ...] --out-dir DIRECTORY render and validate a review bundle

Run 'power-pptx lint --help' for report formats, exit status and --fix options.
Run 'power-pptx review --help' for validation and rendering options."""


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "review":
        from power_pptx.review import main as review_main

        return review_main(args[1:])
    if args and args[0] == "lint":
        from power_pptx.lint_cli import main as lint_main

        return lint_main(args[1:])
    if not args or args[0] in {"-h", "--help"}:
        print(_USAGE)
        return 0
    print(f"Unknown command: {args[0]}. Use 'power-pptx --help'.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
