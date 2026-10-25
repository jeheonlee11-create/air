"""Render code-native SVG chart partials from the exported real crash data.

Reads site/src/data/crash.json (derived from the public sample log) and writes
inline-ready SVG partials to site/src/partials/. Every coordinate comes from
real data; annotation positions use the exact evidence timestamps in the
canonical report. Deterministic output.

Usage: .venv/bin/python site/tools/render_charts.py
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(REPO, "site", "src", "data", "crash.json")
OUT = os.path.join(REPO, "site", "src", "partials")

# palette (mirrors site.css tokens; SVG uses literal values for portability)
INK = "#75726c"        # muted axis text on light panel
GRID = "#e4e1d8"
BARO = "#2563af"
GPS = "#0e7d6f"
EKF = "#c2410c"
CRIT = "#b3261e"
WARN = "#8a5a00"
PANEL = "#fdfcf9"

W, H = 960, 400
ML, MR, MT, MB = 58, 16, 18, 74   # margins; MB leaves room for event rail
BW, BH = 960, 190                  # battery panel
DUR = None  # set from data


def sx(t: float) -> float:
    return ML + (t / DUR) * (W - ML - MR)


def poly(points, y0, y1, ph, mt) -> str:
    def sy(v):
        return mt + (1 - (v - y0) / (y1 - y0)) * ph
    return " ".join(f"{sx(t):.1f},{sy(v):.1f}" for t, v in points)


def main() -> int:
    global DUR
    with open(DATA) as f:
        d = json.load(f)
    DUR = d["flight"]["duration_s"]
    os.makedirs(OUT, exist_ok=True)

    # ---------- main altitude chart ----------
    alt = {k: d["series"][k]["points"] for k in ("alt_baro_m", "alt_gps_m", "alt_local_m")}
    vals = [v for pts in alt.values() for _, v in pts]
    y0, y1 = min(vals) - 8, max(vals) + 14
    ph = H - MT - MB

    def sy(v):
        return MT + (1 - (v - y0) / (y1 - y0)) * ph

    p = []
    p.append(
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="altchart-t altchart-d" '
        f'class="chart chart-alt" preserveAspectRatio="xMidYMid meet">')
    p.append('<title id="altchart-t">Altitude by source over the 594-second flight</title>')
    p.append('<desc id="altchart-d">Three altitude traces with different references — '
             'barometer, GPS (above sea level), and EKF (above its local origin) — plotted '
             'against flight time. Near the end of the flight the barometer and GPS traces '
             'diverge by 20.3 meters, the procedure height limit is exceeded at 121.57 meters '
             'above the launch point, and all traces stop while the aircraft is still '
             'airborne.</desc>')
    p.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{PANEL}"/>')

    # grid + axes
    for gv in range(0, int(y1), 50):
        if gv < y0:
            continue
        gy = sy(gv)
        p.append(f'<line x1="{ML}" y1="{gy:.1f}" x2="{W-MR}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        p.append(f'<text x="{ML-8}" y="{gy+4:.1f}" text-anchor="end" class="tick">{gv}</text>')
    for gt in range(0, int(DUR) + 1, 100):
        gx = sx(gt)
        p.append(f'<line x1="{gx:.1f}" y1="{MT}" x2="{gx:.1f}" y2="{H-MB}" stroke="{GRID}" stroke-width="1"/>')
        p.append(f'<text x="{gx:.1f}" y="{H-MB+16}" text-anchor="middle" class="tick">T+{gt}s</text>')
    p.append(f'<text x="{ML-40}" y="{MT+10}" class="tick">m</text>')

    # conflict window shading (T+575 to end) — under traces
    cx0 = sx(575)
    p.append(f'<rect x="{cx0:.1f}" y="{MT}" width="{sx(DUR)-cx0:.1f}" height="{ph}" '
             f'fill="{WARN}" opacity="0.07"/>')

    # traces (baro/gps/ekf) — classed for CSS + JS
    for key, color, cls in (("alt_baro_m", BARO, "t-baro"),
                                   ("alt_gps_m", GPS, "t-gps"),
                                   ("alt_local_m", EKF, "t-ekf")):
        pts = alt[key]
        p.append(f'<polyline class="trace {cls}" points="{poly(pts, y0, y1, ph, MT)}" '
                 f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>')
        # legend chips drawn separately in HTML; keep SVG clean

    # ALT-1 peak marker on the EKF trace (T+586.9; EKF-origin 120.04 m = 121.57 m above home)
    mx, my = sx(586.94), sy(120.04)
    p.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="4.5" fill="{CRIT}"/>')
    p.append(f'<line x1="{mx:.1f}" y1="{my-8:.1f}" x2="{mx:.1f}" y2="{my-34:.1f}" stroke="{CRIT}" stroke-width="1"/>')
    p.append(f'<text x="{mx-6:.1f}" y="{my-40:.1f}" text-anchor="end" class="anno anno-crit">121.57 m above home — ALT-1 limit is 120 m · FAIL</text>')

    # conflict annotation: double arrow between baro & GPS at T+580.5 (204.73 vs 164.01)
    ax = sx(580.48)
    yb, yg = sy(204.73), sy(164.01)
    p.append(f'<line x1="{ax:.1f}" y1="{yb:.1f}" x2="{ax:.1f}" y2="{yg:.1f}" stroke="{WARN}" '
             f'stroke-width="1.6" stroke-dasharray="3 3" marker-start="url(#arrW)" marker-end="url(#arrW)"/>')
    p.append(f'<text x="{ax-8:.1f}" y="{(yb+yg)/2:.1f}" text-anchor="end" class="anno anno-warn">sources disagree: 20.3 m (offset-corrected)</text>')

    # log-end marker
    ex = sx(DUR)
    p.append(f'<line x1="{ex:.1f}" y1="{MT}" x2="{ex:.1f}" y2="{H-MB}" stroke="{CRIT}" '
             f'stroke-width="1.6" stroke-dasharray="5 4"/>')
    p.append(f'<text x="{ex-6:.1f}" y="{MT+14}" text-anchor="end" class="anno anno-crit">log ends in flight · 12.6 m</text>')

    # event rail
    ry = H - MB + 34
    p.append(f'<line x1="{ML}" y1="{ry}" x2="{W-MR}" y2="{ry}" stroke="{GRID}" stroke-width="1"/>')
    p.append(f'<text x="{ML-8}" y="{ry+4}" text-anchor="end" class="tick">events</text>')
    rail = [(1.78, "info"), (579.24, "critical"), (591.65, "critical"),
            (592.53, "critical"), (593.13, "critical"), (594.04, "critical"),
            (594.39, "info")]
    for t, sev in rail:
        color = CRIT if sev == "critical" else INK
        p.append(f'<line x1="{sx(t):.1f}" y1="{ry-7}" x2="{sx(t):.1f}" y2="{ry+7}" '
                 f'stroke="{color}" stroke-width="2"/>')
    # scrubber cursor (hidden unless JS enables)
    p.append(f'<g class="cursor" aria-hidden="true"><line x1="{ML}" y1="{MT}" x2="{ML}" '
             f'y2="{H-MB}" stroke="#141413" stroke-width="1" opacity="0"/></g>')

    p.append(f'<defs><marker id="arrW" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto">'
             f'<path d="M0,1 L6,3.5 L0,6 Z" fill="{WARN}"/></marker></defs>')
    p.append("</svg>")
    with open(os.path.join(OUT, "chart_altitude.svg"), "w") as f:
        f.write("\n".join(p))

    # ---------- battery panel ----------
    bv = d["series"]["batt_v"]["points"]
    br = d["series"]["batt_remaining"]["points"]
    bmt, bmb = 16, 40
    bph = BH - bmt - bmb
    vmin, vmax = min(v for _, v in bv) - 1, max(v for _, v in bv) + 1

    def syv(v):
        return bmt + (1 - (v - vmin) / (vmax - vmin)) * bph

    def syr(v):
        return bmt + (1 - v / 100) * bph

    q = [f'<svg viewBox="0 0 {BW} {BH}" role="img" aria-labelledby="batchart-t batchart-d" '
         f'class="chart chart-bat" preserveAspectRatio="xMidYMid meet">']
    q.append('<title id="batchart-t">Battery voltage and estimated remaining charge</title>')
    q.append('<desc id="batchart-d">Voltage falls from 31.3 volts to 12.7 volts and estimated '
             'remaining charge reaches zero percent at T+579 seconds, while the aircraft is '
             'still flying.</desc>')
    q.append(f'<rect x="0" y="0" width="{BW}" height="{BH}" fill="{PANEL}"/>')
    for gt in range(0, int(DUR) + 1, 100):
        gx = sx(gt)
        q.append(f'<line x1="{gx:.1f}" y1="{bmt}" x2="{gx:.1f}" y2="{BH-bmb}" stroke="{GRID}" stroke-width="1"/>')
        q.append(f'<text x="{gx:.1f}" y="{BH-bmb+16}" text-anchor="middle" class="tick">T+{gt}s</text>')
    q.append(f'<polyline class="trace t-batv" points="{poly(bv, vmin, vmax, bph, bmt)}" fill="none" '
             f'stroke="{BARO}" stroke-width="1.8"/>')
    q.append(f'<polyline class="trace t-batr" points="{poly([(t, v) for t, v in br], 0, 100, bph, bmt)}" '
             f'fill="none" stroke="{EKF}" stroke-width="1.8"/>')
    q.append(f'<text x="{ML-8}" y="{syv(31.3)+4:.1f}" text-anchor="end" class="tick">31.3&#8202;V</text>')
    q.append(f'<text x="{ML-8}" y="{syr(100)+14:.1f}" text-anchor="end" class="tick">100&#8202;%</text>')
    # 0% marker at 579.24
    zx, zy = sx(579.24), syr(0)
    q.append(f'<circle cx="{zx:.1f}" cy="{zy:.1f}" r="4.5" fill="{CRIT}"/>')
    q.append(f'<text x="{zx-8:.1f}" y="{zy-8:.1f}" text-anchor="end" class="anno anno-crit">0&#8202;% remaining at T+579&#8202;s — still airborne</text>')
    # sag annotation at 588.2 (12.74 V)
    sxx, syy = sx(588.23), syv(12.74)
    q.append(f'<circle cx="{sxx:.1f}" cy="{syy:.1f}" r="4" fill="{WARN}"/>')
    q.append(f'<text x="{sxx-8:.1f}" y="{syy+16:.1f}" text-anchor="end" class="anno anno-warn">12.74&#8202;V — 59&#8202;% sag from flight start</text>')
    ex = sx(DUR)
    q.append(f'<line x1="{ex:.1f}" y1="{bmt}" x2="{ex:.1f}" y2="{BH-bmb}" stroke="{CRIT}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    q.append(f'<g class="cursor" aria-hidden="true"><line x1="{ML}" y1="{bmt}" x2="{ML}" y2="{BH-bmb}" stroke="#141413" stroke-width="1" opacity="0"/></g>')
    q.append("</svg>")
    with open(os.path.join(OUT, "chart_battery.svg"), "w") as f:
        f.write("\n".join(q))

    # ---------- hero visual ----------
    # EKF altitude trace, stylized on dark, with three real markers and a
    # signed-record strip. Base state = fully drawn (reduced-motion safe);
    # CSS may animate stroke-dashoffset only under no-preference.
    hw, hh = 960, 300
    hmt, hmb, hml, hmr = 30, 74, 10, 10
    hph = hh - hmt - hmb
    ekf = d["series"]["alt_local_m"]["points"]
    e0, e1 = min(v for _, v in ekf) - 6, max(v for _, v in ekf) + 10

    def hx(t):
        return hml + (t / DUR) * (hw - hml - hmr)

    def hy(v):
        return hmt + (1 - (v - e0) / (e1 - e0)) * hph

    path = "M " + " L ".join(f"{hx(t):.1f} {hy(v):.1f}" for t, v in ekf)
    h = [f'<svg viewBox="0 0 {hw} {hh}" role="img" aria-labelledby="hero-t hero-d" '
         f'class="herovis" preserveAspectRatio="xMidYMid meet">']
    h.append('<title id="hero-t">Real flight telemetry becoming a signed incident record</title>')
    h.append('<desc id="hero-d">The EKF altitude trace of a real public crash log, with markers '
             'at the battery-depletion point, the procedure-limit exceedance, and the moment the '
             'log ends in flight, above a strip showing the record&#8217;s cryptographic digest.</desc>')
    for gt in range(0, int(DUR) + 1, 100):
        anchor = "start" if gt == 0 else "middle"
        h.append(f'<line x1="{hx(gt):.1f}" y1="{hmt}" x2="{hx(gt):.1f}" y2="{hh-hmb}" '
                 f'stroke="#2a2926" stroke-width="1"/>')
        h.append(f'<text x="{hx(gt):.1f}" y="{hh-hmb+16}" text-anchor="{anchor}" class="htick">T+{gt}s</text>')
    h.append(f'<path class="heropath" d="{path}" fill="none" stroke="#e8b26a" '
             f'stroke-width="1.6" stroke-linejoin="round"/>')
    for t, v, cls, label, anchor in (
            (579.24, None, "hm-bat", "battery 0%", "end"),
            (586.94, 120.04, "hm-alt", "121.6 m above home", "end"),
            (594.64, 12.64, "hm-end", "log ends in flight", "end")):
        yv = hy(v) if v is not None else hy(dict((round(pt[0], 2), pt[1]) for pt in ekf).get(579.24, 100))
        # nearest EKF value for battery marker
        if v is None:
            near = min(ekf, key=lambda pv: abs(pv[0] - t))
            yv = hy(near[1])
        h.append(f'<circle class="hmark {cls}" cx="{hx(t):.1f}" cy="{yv:.1f}" r="4" fill="#f0ede6"/>')
        h.append(f'<text x="{hx(t)-7:.1f}" y="{yv-9:.1f}" text-anchor="{anchor}" class="hanno">{label}</text>')
    # signed-record strip
    ry = hh - hmb + 34
    h.append(f'<line x1="{hml}" y1="{ry-12}" x2="{hw-hmr}" y2="{ry-12}" stroke="#2a2926" stroke-width="1"/>')
    h.append(f'<text x="{hml}" y="{ry+6}" class="hhash">record 2dad8196&#8230; · RFC 9162 merkle root · Ed25519 signed · verifies offline</text>')
    h.append(f'<text x="{hw-hmr}" y="{ry+6}" text-anchor="end" class="hhash hverified">VERIFICATION PASSED</text>')
    h.append("</svg>")
    with open(os.path.join(OUT, "hero_visual.svg"), "w") as f:
        f.write("\n".join(h))

    for name in ("chart_altitude.svg", "chart_battery.svg", "hero_visual.svg"):
        print(f"wrote {name} ({os.path.getsize(os.path.join(OUT, name))/1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
