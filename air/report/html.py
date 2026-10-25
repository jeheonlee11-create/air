"""Human-readable incident record rendering.

The HTML is a rendering of report.json. Both are leaves of the bundle's Merkle
tree, so both are covered by the signature; report.json is the machine-readable
record. Because this page is hashed into the tree, it cannot show the Merkle
root itself; it shows the signing-key fingerprint and points to manifest.json. The document is deliberately light-only and
print-oriented — it is an evidence document, styled like paper.

Charts follow the dataviz reference palette (first three categorical slots,
validated all-pairs on the light surface); severity chips use the reserved
status palette and always carry a text label, never color alone.
"""

from __future__ import annotations

import html as html_mod
import math

from ..schema import SEVERITY_ORDER, Finding, Incident, Series

# --- reference palette (light mode) ---
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1-3 (all-pairs validated)
STATUS = {"critical": "#d03b3b", "warning": "#fab219", "info": "#898781", "good": "#0ca30c"}
STATUS_TEXT = {"critical": "#a02020", "warning": "#8a5a00", "info": "#52514e", "good": "#006300"}


def esc(s) -> str:
    return html_mod.escape(str(s))


def _downsample(t: list[int], v: list[float], n: int = 400):
    if len(t) <= n:
        return t, v
    step = len(t) / n
    idx = [int(i * step) for i in range(n)]
    return [t[i] for i in idx], [v[i] for i in idx]


def _nice_ticks(lo: float, hi: float, n: int = 5):
    import math
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    raw = span / max(1, n - 1)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    start = math.floor(lo / step) * step
    ticks = []
    x = start
    while x <= hi + step * 0.01:
        if x >= lo - step * 0.01:
            ticks.append(round(x, 6))
        x += step
    return ticks


def svg_chart(inc: Incident, series_defs: list[tuple[Series, str]], title: str,
              y_label: str, critical_ts: list[int], width=820, height=260) -> str:
    """Multi-series line chart. series_defs: [(Series, display_name)]."""
    ml, mr, mt, mb = 52, 120, 14, 30
    pw, ph = width - ml - mr, height - mt - mb
    t0, t1 = inc.t0_us, inc.t1_us
    if t1 <= t0:
        return ""

    data = []
    y_min, y_max = float("inf"), float("-inf")
    for s, label in series_defs:
        t, v = _downsample(s.t_us, s.values)
        pts = [(ts, val) for ts, val in zip(t, v, strict=False) if not math.isnan(val)]
        if not pts:
            continue
        data.append((label, pts))
        y_min = min(y_min, min(p[1] for p in pts))
        y_max = max(y_max, max(p[1] for p in pts))
    if not data:
        return ""
    pad = (y_max - y_min) * 0.08 or 1
    y_min, y_max = y_min - pad, y_max + pad

    def X(t):
        return ml + (t - t0) / (t1 - t0) * pw

    def Y(v):
        return mt + (1 - (v - y_min) / (y_max - y_min)) * ph

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}" '
             f'style="width:100%;height:auto;background:{SURFACE};font-family:inherit">']

    # gridlines + y ticks (recessive)
    for ty in _nice_ticks(y_min, y_max):
        y = Y(ty)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{ml-8}" y="{y+3.5:.1f}" text-anchor="end" font-size="10.5" '
                     f'fill="{MUTED}" style="font-variant-numeric:tabular-nums">{ty:g}</text>')
    # x ticks: T+ seconds
    for tx in _nice_ticks(0, (t1 - t0) / 1e6, 6):
        x = X(t0 + tx * 1e6)
        parts.append(f'<text x="{x:.1f}" y="{mt+ph+18}" text-anchor="middle" font-size="10.5" '
                     f'fill="{MUTED}" style="font-variant-numeric:tabular-nums">T+{tx:g}s</text>')
    # baseline
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="{BASELINE}" stroke-width="1"/>')

    # critical event markers (status color, hairline)
    for ts in critical_ts:
        if t0 <= ts <= t1:
            x = X(ts)
            parts.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{mt+ph}" '
                         f'stroke="{STATUS["critical"]}" stroke-width="1" stroke-dasharray="2,3" opacity="0.55">'
                         f'<title>critical event at T+{(ts-t0)/1e6:.1f}s</title></line>')

    # series lines (2px) + direct end labels in ink with color swatch
    for i, (label, pts) in enumerate(data):
        color = SERIES[i % len(SERIES)]
        d = "M" + " L".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round">'
                     f'<title>{esc(label)}</title></path>')
        ex, ey = X(pts[-1][0]), Y(pts[-1][1])
        ey = min(max(ey, mt + 8 + i * 14), mt + ph - 4)
        parts.append(f'<line x1="{ex+4:.1f}" y1="{ey:.1f}" x2="{ex+16:.1f}" y2="{ey:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{ex+20:.1f}" y="{ey+3.5:.1f}" font-size="10.5" fill="{INK2}">{esc(label)}</text>')

    parts.append(f'<text x="{ml}" y="{mt-2}" font-size="10.5" fill="{MUTED}">{esc(y_label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _sev_chip(sev: str) -> str:
    label = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}[sev]
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:9px;'
            f'font-size:11px;font-weight:600;letter-spacing:.4px;color:{STATUS_TEXT[sev]};'
            f'border:1px solid {STATUS[sev]};background:{SURFACE}">'
            f'{"&#9679; " if sev != "info" else ""}{label}</span>')


def _verdict_chip(verdict: str) -> str:
    style = {"PASS": ("good", "&#10003; PASS"), "FAIL": ("critical", "&#10007; FAIL"),
             "MARGINAL": ("warning", "~ MARGINAL"),
             "NOT_EVALUABLE": ("warning", "? NOT EVALUABLE")}[verdict]
    return (f'<span style="font-weight:600;color:{STATUS_TEXT[style[0]]}">{style[1]}</span>')


def render_html(inc: Incident, findings: list[Finding], conformance: dict | None,
                key_fingerprint: str, generator_version: str) -> str:
    findings = sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.code))
    n_crit = sum(1 for f in findings if f.severity == "critical")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    critical_ts = [e["t_us"] for f in findings if f.severity == "critical"
                   for e in f.evidence if isinstance(e.get("t_us"), int)]

    # charts
    alt_defs = []
    for key, label in (("alt_baro_m", "Barometer"), ("alt_gps_m", "GPS MSL"), ("alt_local_m", "EKF (origin)")):
        s = inc.series_or_none(key)
        if s:
            alt_defs.append((s, label))
    alt_chart = svg_chart(inc, alt_defs, "Altitude by source", "altitude (m)", critical_ts) if alt_defs else ""
    bat = inc.series_or_none("batt_v")
    bat_chart = svg_chart(inc, [(bat, "Battery")], "Battery voltage", "volts", critical_ts) if bat else ""

    utc_note = (f"UTC anchored via {esc(inc.utc_anchor.source)}" if inc.utc_anchor
                else "No UTC anchor in log — times are relative to log start")
    home_note = (f"{inc.home['lat']:.6f}, {inc.home['lon']:.6f}" if inc.home else "unavailable")

    events_rows = []
    shown = [e for e in inc.sorted_events() if e.kind != "message" or e.severity != "info"]
    for ev in shown[:120]:
        dot = STATUS.get(ev.severity, MUTED)
        events_rows.append(
            f'<tr><td style="white-space:nowrap;color:{MUTED};font-variant-numeric:tabular-nums">'
            f'{esc(inc.t_label(ev.t_us))}</td>'
            f'<td><span style="color:{dot}">&#9679;</span> {esc(ev.message)}</td>'
            f'<td style="color:{MUTED};font-size:11px">{esc(ev.source.split(":",1)[-1])}</td></tr>')

    finding_cards = []
    for f in findings:
        ev_rows = "".join(
            f'<tr><td style="white-space:nowrap;color:{MUTED}">{esc(inc.t_label(e["t_us"])) if isinstance(e.get("t_us"), int) else "—"}</td>'
            f'<td style="font-variant-numeric:tabular-nums">{esc(e.get("value","—"))}</td>'
            f'<td>{esc(e.get("note",""))}</td>'
            f'<td style="color:{MUTED};font-size:11px">{esc(e.get("source",""))}</td></tr>'
            for e in f.evidence)
        thr = ""
        if f.threshold:
            basis = f.threshold.get("basis", "")
            nums = ", ".join(f"{k}={v}" for k, v in f.threshold.items() if k not in ("basis", "metric"))
            thr = (f'<div style="margin-top:6px;font-size:11.5px;color:{MUTED}">Threshold: '
                   f'{esc(f.threshold.get("metric",""))} {esc(nums)}'
                   f'{" &middot; basis: " + esc(basis) if basis else ""}</div>')
        finding_cards.append(f"""
        <div style="border:1px solid {GRID};border-left:3px solid {STATUS[f.severity]};
                    border-radius:6px;padding:12px 16px;margin:10px 0;background:{SURFACE}">
          <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
            {_sev_chip(f.severity)}
            <span style="font-size:11px;color:{MUTED};font-family:ui-monospace,monospace">{esc(f.code)}</span>
            <strong style="font-size:14px">{esc(f.title)}</strong>
          </div>
          <p style="margin:8px 0 0;font-size:13px;line-height:1.55;color:{INK2}">{esc(f.summary)}</p>
          {f'<table style="margin-top:8px;font-size:12px;border-collapse:collapse;width:100%">{ev_rows}</table>' if ev_rows else ''}
          {thr}
        </div>""")

    conf_html = ""
    if conformance:
        rows = []
        for r in conformance["results"]:
            obs = r.get("observed", "—")
            if isinstance(obs, list):
                obs = ", ".join(obs)
            rows.append(
                f'<tr><td style="font-family:ui-monospace,monospace;font-size:11.5px">{esc(r["id"])}</td>'
                f'<td>{esc(r["description"])}</td>'
                f'<td>{_verdict_chip(r["verdict"])}</td>'
                f'<td style="font-variant-numeric:tabular-nums">{esc(obs)}</td>'
                f'<td style="color:{MUTED};font-variant-numeric:tabular-nums">{esc(r.get("op",""))} {esc(r.get("limit", r.get("reason","")))}</td></tr>')
        conf_html = f"""
        <h2 style="font-size:16px;margin:28px 0 4px">Procedure conformance</h2>
        <div style="font-size:12.5px;color:{MUTED};margin-bottom:8px">Checked against:
          {esc(conformance.get("procedures_name",""))} &middot;
          {conformance["passed"]} passed &middot; {conformance["failed"]} failed &middot;
          {conformance.get("marginal", 0)} marginal (within measurement tolerance) &middot;
          {conformance["not_evaluable"]} not evaluable</div>
        <table style="width:100%;border-collapse:collapse;font-size:12.5px" class="rules">
          <thead><tr style="text-align:left;color:{MUTED};font-size:11px">
            <th style="padding:4px 8px 4px 0">RULE</th><th>REQUIREMENT</th><th>VERDICT</th>
            <th>OBSERVED</th><th>LIMIT</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>"""

    src_rows = "".join(
        f'<tr><td>{esc(s.kind)}</td><td style="font-size:11.5px">{esc(s.path.split("/")[-1])}</td>'
        f'<td style="font-family:ui-monospace,monospace;font-size:10.5px;word-break:break-all">{esc(s.sha256)}</td>'
        f'<td style="font-variant-numeric:tabular-nums">{s.size_bytes:,} B</td></tr>'
        for s in inc.sources)

    aircraft_bits = " &middot; ".join(esc(f"{k}: {v}") for k, v in inc.aircraft.items() if v)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Airspace Incident Record {esc(inc.incident_id[:8])}</title>
<style>
  body {{ margin:0; background:{PAGE}; color:{INK};
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .page {{ max-width:900px; margin:0 auto; padding:36px 28px 60px; }}
  table.rules td, table.rules th {{ padding:6px 8px 6px 0; border-bottom:1px solid {GRID}; vertical-align:top; }}
  h2 {{ font-weight:600; }}
  @media print {{ body {{ background:#fff }} }}
</style></head>
<body><div class="page">

  <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
    <div style="font-size:11px;letter-spacing:2.5px;color:{MUTED};font-weight:600">AIRSPACE INCIDENT RECORD</div>
    <div style="font-size:11px;color:{MUTED};font-family:ui-monospace,monospace">{esc(inc.incident_id)}</div>
  </div>
  <h1 style="font-size:22px;margin:10px 0 2px">Flight incident investigation record</h1>
  <div style="font-size:12.5px;color:{INK2};margin-bottom:2px">
    Generated {esc(inc.created_utc)} &middot; AIR v{esc(generator_version)} (deterministic analysis) &middot; duration {inc.duration_s:.1f}s</div>
  <div style="font-size:12px;color:{MUTED}">{aircraft_bits}</div>
  <div style="font-size:12px;color:{MUTED}">{esc(utc_note)} &middot; launch position: {home_note}</div>

  <div style="display:flex;gap:12px;margin:20px 0 4px;flex-wrap:wrap">
    <div style="flex:1;min-width:130px;border:1px solid {GRID};border-radius:6px;padding:10px 14px;background:{SURFACE}">
      <div style="font-size:26px;font-weight:600;color:{STATUS_TEXT['critical'] if n_crit else INK}">{n_crit}</div>
      <div style="font-size:11px;color:{MUTED};letter-spacing:.5px">CRITICAL FINDINGS</div></div>
    <div style="flex:1;min-width:130px;border:1px solid {GRID};border-radius:6px;padding:10px 14px;background:{SURFACE}">
      <div style="font-size:26px;font-weight:600;color:{STATUS_TEXT['warning'] if n_warn else INK}">{n_warn}</div>
      <div style="font-size:11px;color:{MUTED};letter-spacing:.5px">WARNINGS</div></div>
    <div style="flex:1;min-width:130px;border:1px solid {GRID};border-radius:6px;padding:10px 14px;background:{SURFACE}">
      <div style="font-size:26px;font-weight:600">{conformance['failed'] if conformance else '—'}</div>
      <div style="font-size:11px;color:{MUTED};letter-spacing:.5px">PROCEDURE VIOLATIONS</div></div>
    <div style="flex:1;min-width:130px;border:1px solid {GRID};border-radius:6px;padding:10px 14px;background:{SURFACE}">
      <div style="font-size:26px;font-weight:600">{len(inc.sources)}</div>
      <div style="font-size:11px;color:{MUTED};letter-spacing:.5px">EVIDENCE SOURCES</div></div>
  </div>

  {f'<h2 style="font-size:16px;margin:26px 0 8px">Altitude by source</h2>{alt_chart}' if alt_chart else ''}
  {f'<div style="font-size:11.5px;color:{MUTED};margin-top:4px">Dashed red rules mark critical-finding timestamps. The three sources use different references (barometric pressure altitude, GPS height above mean sea level, EKF height above its local origin), so compare their shapes, not their absolute values; divergence in shape is itself evidence (see conflict findings).</div>' if alt_chart else ''}
  {f'<h2 style="font-size:16px;margin:26px 0 8px">Battery voltage</h2>{bat_chart}' if bat_chart else ''}

  <h2 style="font-size:16px;margin:28px 0 8px">Findings</h2>
  {''.join(finding_cards) if finding_cards else '<p style="font-size:13px;color:' + INK2 + '">No findings above threshold.</p>'}

  {conf_html}

  <h2 style="font-size:16px;margin:28px 0 8px">Event timeline</h2>
  <table style="width:100%;border-collapse:collapse;font-size:12.5px" class="rules">
    <tbody>{''.join(events_rows)}</tbody></table>
  {f'<div style="font-size:11px;color:{MUTED};margin-top:4px">Showing {min(len(shown),120)} of {len(shown)} events (info-level firmware chatter suppressed). Full timeline in report.json.</div>'}

  <h2 style="font-size:16px;margin:28px 0 8px">Evidence &amp; verification</h2>
  <table style="width:100%;border-collapse:collapse;font-size:12px" class="rules">
    <thead><tr style="text-align:left;color:{MUTED};font-size:11px">
      <th style="padding:4px 8px 4px 0">KIND</th><th>FILE</th><th>SHA-256</th><th>SIZE</th></tr></thead>
    <tbody>{src_rows}</tbody></table>
  <div style="font-size:12px;color:{INK2};margin-top:10px;line-height:1.6">
    Signing key fingerprint (SHA-256): <span style="font-family:ui-monospace,monospace;font-size:10.5px;word-break:break-all">{esc(key_fingerprint)}</span>.
    Compare it with the fingerprint the operator published separately; this page cannot vouch for itself.<br>
    This page and report.json are leaves of an RFC 9162 Merkle tree whose root is signed with Ed25519. The root, the
    signature and any RFC 3161 timestamp are in <span style="font-family:ui-monospace,monospace">manifest.json</span>
    (this page is hashed into the tree, so it cannot contain the root).<br>
    To verify: <span style="font-family:ui-monospace,monospace">python3 verify.py --fingerprint &lt;published fingerprint&gt;</span>
    inside the bundle directory. Changing any byte of report.json, of this page, or of a referenced source file makes
    verification fail; a copy re-signed with a different key fails the fingerprint check.
  </div>

  <div style="margin-top:34px;padding-top:14px;border-top:1px solid {GRID};font-size:11px;color:{MUTED};line-height:1.6">
    This page is a human-readable rendering of <span style="font-family:ui-monospace,monospace">report.json</span>; both are covered by the bundle signature.
    All findings are produced by deterministic, documented rules (no machine-learning inference); every threshold cites its basis.
    The signature and hashes show whether this record changed after signing; they do not show who controls the
    signing key, and they do not make the record admissible. AIR produces records intended to support a qualified
    person's certification (for example under Fed. R. Evid. 902(13)/(14)); it does not itself certify identity or
    admissibility. Conclusions about cause remain the responsibility of a qualified investigator. Findings marked as indicators (e.g. interference indicators)
    are stated with their corroboration requirements and are not conclusions.
  </div>
</div></body></html>"""
