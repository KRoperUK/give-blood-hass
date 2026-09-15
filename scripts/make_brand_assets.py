#!/usr/bin/env python3
"""Generate the brand assets HACS and the Home Assistant brands repository expect.

HACS requires either a PR to home-assistant/brands or local assets under
``custom_components/<domain>/brand/``. This script produces the local set from a
single SVG source, so the artwork is reproducible and reviewable as text rather
than as opaque binaries.

The mark is a **blood droplet inside a rounded square**, drawn from scratch in a
neutral red. It deliberately does **not** use the NHS logo, the NHS Blood and
Transplant identity, or the NHS blue — this is an unofficial project and reusing
protected identity marks would be both a trademark problem and misleading about
endorsement.

Usage:

    python scripts/make_brand_assets.py

Requires ``rsvg-convert`` (``brew install librsvg``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BRAND_DIR = Path("custom_components/nhs_give_blood/brand")

# Neutral crimson. Distinct from NHS blue and not sampled from any NHSBT asset.
RED = "#c8102e"
RED_DARK = "#8a0b20"
WHITE = "#ffffff"

#: A droplet: rounded bottom, tapered top. Path is a circle of radius r centred
#: at (cx, cy) with two straight edges rising to an apex, which is the classic
#: teardrop construction and renders cleanly at 16 px as well as 512 px.
_DROPLET = "M 256 96 C 256 96 168 216 168 292 a 88 88 0 0 0 176 0 C 344 216 256 96 256 96 Z"

ICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" rx="96" fill="{RED}"/>
  <path d="{_DROPLET}" fill="{WHITE}"/>
  <!-- Highlight: a small offset arc, so the droplet reads as a volume rather
       than a flat silhouette at large sizes. -->
  <path d="M 226 268 a 34 34 0 0 1 24 -46" fill="none" stroke="{RED}"
        stroke-width="14" stroke-linecap="round" opacity="0.35"/>
</svg>
"""

ICON_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" rx="96" fill="{WHITE}"/>
  <path d="{_DROPLET}" fill="{RED}"/>
  <path d="M 226 268 a 34 34 0 0 1 24 -46" fill="none" stroke="{WHITE}"
        stroke-width="14" stroke-linecap="round" opacity="0.55"/>
</svg>
"""


def _logo_svg(*, drop: str, text: str, background: str | None) -> str:
    """A wordmark: the droplet beside "Give Blood".

    The droplet path spans x 168-344, y 96-380 in the icon's 512 viewBox. The
    transform below scales it to 200px tall with 28px of vertical padding and
    seats it at x=24, and the text baseline is placed so the cap height is
    optically centred. Hand-computed rather than eyeballed, because a wordmark
    that clips or overlaps at 512px looks worse than no logo at all.
    """
    backdrop = f'<rect width="1024" height="256" fill="{background}"/>' if background else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 256" width="1024" height="256">
  {backdrop}
  <g transform="translate(-93.6, -39.2) scale(0.7)">
    <path d="{_DROPLET}" fill="{drop}"/>
  </g>
  <text x="182" y="176" font-family="Helvetica, Arial, sans-serif" font-size="128"
        font-weight="700" letter-spacing="-2" fill="{text}">Give Blood</text>
</svg>
"""


LOGO_SVG = _logo_svg(drop=RED, text=RED_DARK, background=None)
LOGO_DARK_SVG = _logo_svg(drop=RED, text=WHITE, background=None)

#: ``(filename, svg, width, height)``. Sizes follow the Home Assistant brands
#: spec: icons are square at 256/512, logos are capped at 128/256 in height.
ASSETS: tuple[tuple[str, str, int, int], ...] = (
    ("icon.png", ICON_SVG, 256, 256),
    ("icon@2x.png", ICON_SVG, 512, 512),
    ("dark_icon.png", ICON_DARK_SVG, 256, 256),
    ("dark_icon@2x.png", ICON_DARK_SVG, 512, 512),
    ("logo.png", LOGO_SVG, 512, 128),
    ("logo@2x.png", LOGO_SVG, 1024, 256),
    ("dark_logo.png", LOGO_DARK_SVG, 512, 128),
    ("dark_logo@2x.png", LOGO_DARK_SVG, 1024, 256),
)


def main() -> int:
    """Render every asset."""
    if shutil.which("rsvg-convert") is None:
        print("error: rsvg-convert not found. Install it with `brew install librsvg`.", file=sys.stderr)
        return 1

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    source_dir = BRAND_DIR / "src"
    source_dir.mkdir(exist_ok=True)

    # The SVG sources are committed alongside the PNGs so the artwork stays
    # reviewable and regenerable rather than being opaque binary history.
    (source_dir / "icon.svg").write_text(ICON_SVG)
    (source_dir / "dark_icon.svg").write_text(ICON_DARK_SVG)
    (source_dir / "logo.svg").write_text(LOGO_SVG)
    (source_dir / "dark_logo.svg").write_text(LOGO_DARK_SVG)

    for name, svg, width, height in ASSETS:
        target = BRAND_DIR / name
        subprocess.run(
            ["rsvg-convert", "-w", str(width), "-h", str(height), "-o", str(target)],
            input=svg.encode(),
            check=True,
        )
        print(f"  {target}  {width}x{height}")

    print(f"\nwrote {len(ASSETS)} assets to {BRAND_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
