#!/usr/bin/env python3
"""Normalise ``manifest.json`` key order and formatting.

Home Assistant's hassfest requires ``domain`` and ``name`` first, then the rest
alphabetical. release-please rewrites the ``version`` key with its own JSON
formatter, and Prettier would reorder keys, so this hook is the single authority —
which is why manifests are listed in ``.prettierignore``.

Run with no arguments; exits 1 if it changed the file, the way a formatting hook
should.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MANIFEST = Path("custom_components/nhs_give_blood/manifest.json")
LEADING_KEYS = ("domain", "name")


def normalise(manifest: dict[str, object]) -> dict[str, object]:
    """Return the manifest with hassfest's expected key order."""
    ordered: dict[str, object] = {key: manifest[key] for key in LEADING_KEYS if key in manifest}
    for key in sorted(key for key in manifest if key not in LEADING_KEYS):
        ordered[key] = manifest[key]
    return ordered


def main() -> int:
    """Rewrite the manifest if needed."""
    if not MANIFEST.is_file():
        print(f"{MANIFEST} not found", file=sys.stderr)
        return 1

    original = MANIFEST.read_text()
    formatted = json.dumps(normalise(json.loads(original)), indent=2) + "\n"

    if formatted == original:
        return 0

    MANIFEST.write_text(formatted)
    print(f"reformatted {MANIFEST}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
