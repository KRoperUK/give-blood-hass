#!/usr/bin/env python3
"""Generate the brand assets HACS expects.

home-assistant/brands no longer accepts submissions for custom components, so the
in-repository fallback — ``custom_components/<domain>/brand/`` — is the only route
available to a HACS integration, not merely the convenient one. This script
produces that set from committed sources, so the artwork stays reproducible and
reviewable rather than becoming opaque binary history.

The artwork is the official NHS Blood and Transplant "Save lives, Give blood"
lockup (``src/official-logo.svg``, as published on blood.co.uk) and the official
NHS Give Blood app icon (embedded as base64 in ``src/icon.svg`` and
``src/dark_icon.svg``, as published on the App Store; the JPEG original lives on
in the SVG so every asset renders from committed text). It identifies the
service the integration talks to, which is the established custom-integration
convention; it is not an NHS endorsement of this unofficial project.

Usage:

    python scripts/make_brand_assets.py

Requires ``rsvg-convert`` (``brew install librsvg``).
"""

from __future__ import annotations

import binascii
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

BRAND_DIR = Path("custom_components/nhs_give_blood/brand")
SRC_DIR = BRAND_DIR / "src"

#: Brand red sampled from the official lockup (``.st0`` fill).
NHSBT_RED = "#DA291C"
WHITE = "#ffffff"

#: Logo canvas follows the Home Assistant brands spec: capped at 128/256 high.
LOGO_W, LOGO_H = 1024, 256


def _official_group(svg: str) -> str:
    """Return the artwork group of the official lockup SVG."""
    match = re.search(r"<g>.*</g>", svg, re.DOTALL)
    if not match:
        raise ValueError("official-logo.svg contains no <g> artwork group")
    return match.group(0)


def _logo_svg(*, fill: str) -> str:
    """The official lockup centred on the brands logo canvas.

    The lockup's viewBox is 201x57; it is scaled to the full canvas height and
    centred horizontally (hand-computed so nothing clips).
    """
    official = (SRC_DIR / "official-logo.svg").read_text()
    group = _official_group(official)
    scale = LOGO_H / 57
    x_offset = (LOGO_W - 201 * scale) / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LOGO_W} {LOGO_H}" width="{LOGO_W}" height="{LOGO_H}">
<style type="text/css">
\t.st0{{fill:{fill};}}
</style>
  <g transform="translate({x_offset:.2f},0) scale({scale:.5f})">
{group}
  </g>
</svg>
"""


LOGO_SVG = _logo_svg(fill=NHSBT_RED)
LOGO_DARK_SVG = _logo_svg(fill=WHITE)


#: ``(filename, svg, width, height)`` for every asset. Icons render from the
#: committed ``src/icon.svg`` / ``src/dark_icon.svg`` wrappers (official app
#: artwork embedded); logos from the wrappers built above.
def _icon_assets() -> tuple[tuple[str, str, int, int], ...]:
    icon = (SRC_DIR / "icon.svg").read_text()
    dark_icon = (SRC_DIR / "dark_icon.svg").read_text()
    return (
        ("icon.png", icon, 256, 256),
        ("icon@2x.png", icon, 512, 512),
        ("dark_icon.png", dark_icon, 256, 256),
        ("dark_icon@2x.png", dark_icon, 512, 512),
    )


VECTOR_ASSETS: tuple[tuple[str, str, int, int], ...] = (
    ("logo.png", LOGO_SVG, 512, 128),
    ("logo@2x.png", LOGO_SVG, 1024, 256),
    ("dark_logo.png", LOGO_DARK_SVG, 512, 128),
    ("dark_logo@2x.png", LOGO_DARK_SVG, 1024, 256),
)


def _render_svg(name: str, svg: str, width: int, height: int) -> None:
    target = BRAND_DIR / name
    subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height), "-o", str(target)],
        input=svg.encode(),
        check=True,
    )
    print(f"  {target}  {width}x{height}")


def _ensure_rgba(path: Path) -> None:
    """Add a fully-opaque alpha channel to an RGB PNG in place.

    rsvg-convert drops the alpha channel when the artwork is fully opaque (as
    the JPEG-sourced app icon is), but the integration's hygiene tests require
    RGBA throughout so Home Assistant can composite onto any surface. This
    rewrites 8-bit non-interlaced RGB files with stdlib only.
    """
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos, chunks, width, height, changed = 8, [], 0, 0, False
    idat = bytearray()
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos : pos + 4])
        ctype, data = raw[pos + 4 : pos + 8], raw[pos + 8 : pos + 8 + length]
        if ctype == b"IHDR":
            width, height, depth, colour, _, _, _ = struct.unpack(">IIBBBBB", data)
            if (depth, colour) not in ((8, 2), (8, 6)):
                raise ValueError(f"{path}: unexpected PNG format")
            if colour == 2:
                data = data[:9] + b"\x06" + data[10:]
                changed = True
        elif ctype == b"IDAT":
            idat += data
            if changed:
                pos += 12 + length
                continue
        chunks.append((ctype, data))
        pos += 12 + length
    if not changed:
        return
    stride = width * 3
    pixels, out = zlib.decompress(bytes(idat)), bytearray()
    for y in range(height):
        row = pixels[y * (stride + 1) : (y + 1) * (stride + 1)]
        out.append(row[0])
        for x in range(width):
            out += row[1 + x * 3 : 1 + x * 3 + 3] + b"\xff"
    idat_new = zlib.compress(bytes(out), 9)
    # IEND was collected last; the replacement IDAT must precede it.
    if chunks[-1][0] != b"IEND":
        raise ValueError(f"{path}: PNG does not end with IEND")
    chunks.insert(-1, (b"IDAT", idat_new))
    blob = bytearray(raw[:8])
    for ctype, data in chunks:
        blob += struct.pack(">I", len(data)) + ctype + data
        blob += struct.pack(">I", binascii.crc32(ctype + data) & 0xFFFFFFFF)
    path.write_bytes(bytes(blob))


def main() -> int:
    """Render every asset."""
    if shutil.which("rsvg-convert") is None:
        print("error: rsvg-convert not found. Install it with `brew install librsvg`.", file=sys.stderr)
        return 1

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    SRC_DIR.mkdir(exist_ok=True)

    # The SVG sources are committed alongside the PNGs so the artwork stays
    # reviewable and regenerable rather than being opaque binary history. The
    # hand-drawn predecessors are replaced: this integration now uses the
    # official artwork described in the module docstring.
    (SRC_DIR / "logo.svg").write_text(LOGO_SVG)
    (SRC_DIR / "dark_logo.svg").write_text(LOGO_DARK_SVG)

    assets = _icon_assets() + VECTOR_ASSETS
    for name, svg, width, height in assets:
        _render_svg(name, svg, width, height)
        _ensure_rgba(BRAND_DIR / name)

    print(f"\nwrote {len(assets)} assets to {BRAND_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
