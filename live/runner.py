"""Deprecated CLI entrypoint for the removed Python Live scaffold."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None):
    _ = argv
    print(
        "The standalone Python Gemini Live scaffold has been removed.\n"
        "Start the Electron app with `npm start` to use the JS-based Live integration.",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
