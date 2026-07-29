"""Generate favicon/OG/poster images locally with Pillow (free, no services).

The OG image and poster draw the REAL EKF altitude trace from crash.json —
the same data as the site — plus the wordmark and record strip. Fonts: macOS
system fonts rendered locally into raster images (no font files are shipped).

Usage: .venv/bin/python site/tools/gen_images.py
"""

from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(REPO, "site", "src", "data", "crash.json")
OUT = os.path.join(REPO, "site", "src", "assets", "img")

DARK = (19, 18, 17)
GRIDC = (42, 41, 38)
AMBER = (232, 178, 106)
SIGNAL = (194, 65, 12)
INK = (240, 237, 230)
MUTED = (160, 156, 147)
GREEN = (121, 201, 139)


def font(size: int, mono: bool = False, bold: bool = False):
    candidates = (
        ["/System/Library/Fonts/Menlo.ttc"] if mono else
        ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc"])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size, index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_trace(dr: ImageDraw.ImageDraw, pts, x0, y0, w, h, dur, vmin, vmax, width=3):
    coords = []
    for t, v in pts:
        x = x0 + (t / dur) * w
        y = y0 + (1 - (v - vmin) / (vmax - vmin)) * h
        coords.append((x, y))
    dr.line(coords, fill=AMBER, width=width, joint="curve")
    return coords


def base_canvas(W, H, d):
    img = Image.new("RGB", (W, H), DARK)
    dr = ImageDraw.Draw(img)
    dur = d["flight"]["duration_s"]
    for gt in range(0, int(dur) + 1, 100):
        x = int(60 + (gt / dur) * (W - 120))
        dr.line([(x, H * 0.42), (x, H * 0.80)], fill=GRIDC, width=1)
    pts = d["series"]["alt_local_m"]["points"]
    vmin = min(v for _, v in pts) - 6
    vmax = max(v for _, v in pts) + 10
    draw_trace(dr, pts, 60, H * 0.42, W - 120, H * 0.36, dur, vmin, vmax)
    # markers: battery 0% (579.24), alt peak (586.94, 120.04), end (594.64, 12.64)
    for t, v in ((579.24, None), (586.94, 120.04), (594.64, 12.64)):
        if v is None:
            near = min(pts, key=lambda pv: abs(pv[0] - t))
            v = near[1]
        x = 60 + (t / dur) * (W - 120)
        y = H * 0.42 + (1 - (v - vmin) / (vmax - vmin)) * (H * 0.36)
        r = 6
        dr.ellipse([x - r, y - r, x + r, y + r], fill=INK)
    return img, dr, dur


def og():
    W, H = 1200, 630
    with open(DATA) as f:
        d = json.load(f)
    img, dr, _dur = base_canvas(W, H, d)
    dr.ellipse([57, 57, 75, 75], fill=SIGNAL)
    dr.text((92, 52), "AIR", font=font(30, mono=True, bold=True), fill=INK)
    dr.text((60, 120), "Turn raw drone telemetry into", font=font(52, bold=True), fill=INK)
    dr.text((60, 180), "an incident record you can verify.", font=font(52, bold=True), fill=INK)
    dr.text((60, 252), "Real public crash log · deterministic findings · signed record · offline verification",
            font=font(22), fill=MUTED)
    dr.line([(60, H - 78), (W - 60, H - 78)], fill=GRIDC, width=1)
    dr.text((60, H - 62), "record 2dad8196…  ·  RFC 9162 merkle root  ·  Ed25519 signed",
            font=font(19, mono=True), fill=MUTED)
    tw = dr.textlength("VERIFICATION PASSED", font=font(19, mono=True))
    dr.text((W - 60 - tw, H - 62), "VERIFICATION PASSED", font=font(19, mono=True), fill=GREEN)
    img.save(os.path.join(OUT, "og.png"), optimize=True)


def poster():
    W, H = 1280, 720
    with open(DATA) as f:
        d = json.load(f)
    img, dr, _dur = base_canvas(W, H, d)
    dr.ellipse([57, 61, 75, 79], fill=SIGNAL)
    dr.text((92, 56), "AIR", font=font(30, mono=True, bold=True), fill=INK)
    dr.text((60, 130), "One real crash. 594.7 seconds of log.", font=font(54, bold=True), fill=INK)
    dr.text((60, 192), "Seven findings. One verifiable record.", font=font(54, bold=True), fill=INK)
    dr.text((60, 268), "Public PX4 corpus log 75957ba9 · analyzed by the AIR engine",
            font=font(22, mono=True), fill=MUTED)
    dr.line([(60, H - 84), (W - 60, H - 84)], fill=GRIDC, width=1)
    dr.text((60, H - 66), "battery 0% in flight · 120.04 m vs 120 m limit · baro/GPS disagree 20.3 m · log ends in flight",
            font=font(20, mono=True), fill=MUTED)
    img.save(os.path.join(OUT, "poster.png"), optimize=True)


def icons():
    # simple mark: dark rounded square, amber trace, signal dot
    for size, name in ((32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "icon-512.png")):
        s = size
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        rad = max(4, s // 6)
        dr.rounded_rectangle([0, 0, s - 1, s - 1], radius=rad, fill=DARK)
        pts = [(0.12, 0.68), (0.30, 0.52), (0.42, 0.60), (0.58, 0.30), (0.70, 0.42), (0.88, 0.22)]
        dr.line([(x * s, y * s) for x, y in pts], fill=AMBER, width=max(2, s // 14), joint="curve")
        r = max(2, s // 12)
        cx, cy = 0.88 * s, 0.22 * s
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SIGNAL)
        img.save(os.path.join(OUT, name))


def favicon_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" rx="6" fill="#131211"/>
<polyline points="4,22 9.5,17 13.5,19 18.5,10 22.5,13.5 28,7" fill="none"
 stroke="#e8b26a" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
<circle cx="28" cy="7" r="2.6" fill="#c2410c"/>
</svg>
"""
    with open(os.path.join(OUT, "favicon.svg"), "w") as f:
        f.write(svg)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    favicon_svg()
    icons()
    og()
    poster()
    for n in sorted(os.listdir(OUT)):
        print(f"  {n}: {os.path.getsize(os.path.join(OUT, n))/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
