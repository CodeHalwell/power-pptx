"""Installed command line interface for authoring and review workflows."""

from __future__ import annotations

import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "review":
        from power_pptx.review import main as review_main

        return review_main(args[1:])
    if not args or args[0] in {"-h", "--help"}:
        print(
            "Usage: power-pptx review INPUT [INPUT ...] --out-dir DIRECTORY\n"
            "Run 'power-pptx review --help' for validation and rendering options."
        )
        return 0
    print(f"Unknown command: {args[0]}. Use 'power-pptx --help'.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
