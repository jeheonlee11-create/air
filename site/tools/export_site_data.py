"""Export derived, downsampled data from the public sample log for the website.

Reads the fixture log with the AIR engine (no engine changes) and the canonical
regenerated bundle, and writes site/src/data/crash.json containing ONLY derived
series (downsampled), findings, conformance, and selected timeline events —
never the raw log (its corpus redistribution license is unclear; see
CLAIMS_LEDGER.md C0).

Deterministic: same inputs -> same output file.

Usage: .venv/bin/python site/tools/export_site_data.py
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from air.ingest import ingest_ulog  # noqa: E402

FIXTURE = os.path.join(REPO, "fixtures", "75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg")
BUNDLE = os.path.join(REPO, "bundles", "site-source")
OUT = os.path.join(REPO, "site", "src", "data", "crash.json")

MAX_POINTS = 240


def downsample(t_us: list[int], values: list[float], t0: int) -> list[list[float]]:
    """Min/max-preserving decimation to <= MAX_POINTS, as [t_rel_s, value] pairs."""
    n = len(t_us)
    if n <= MAX_POINTS:
        return [[round((t - t0) / 1e6, 2), round(v, 2)] for t, v in zip(t_us, values, strict=False)]
    out: list[list[float]] = []
    bucket = n / (MAX_POINTS / 2)  # each bucket contributes min+max
    i = 0.0
    while int(i) < n:
        j = min(n, int(i + bucket))
        seg = list(range(int(i), j))
        if not seg:
            break
        lo = min(seg, key=lambda k: values[k])
        hi = max(seg, key=lambda k: values[k])
        for k in sorted({lo, hi}):
            out.append([round((t_us[k] - t0) / 1e6, 2), round(values[k], 2)])
        i += bucket
    out.sort(key=lambda p: p[0])
    return out


def main() -> int:
    inc = ingest_ulog(FIXTURE)
    t0 = inc.t0_us

    series = {}
    for name in ("alt_baro_m", "alt_gps_m", "alt_local_m", "batt_v", "batt_remaining",
                 "gps_nsats", "groundspeed_ms", "dist_home_m"):
        s = inc.series_or_none(name)
        if s is None:
            continue
        series[name] = {
            "source": s.source,
            "units": s.units,
            "points": downsample(s.t_us, s.values, t0),
        }
    # battery remaining as percent for display
    if "batt_remaining" in series:
        series["batt_remaining"]["points"] = [
            [t, round(v * 100, 1)] for t, v in series["batt_remaining"]["points"]]
        series["batt_remaining"]["units"] = "%"

    with open(os.path.join(BUNDLE, "report.json")) as f:
        report = json.load(f)
    with open(os.path.join(BUNDLE, "manifest.json")) as f:
        manifest = json.load(f)

    # Key timeline events for the site (kinds that matter to the story; drop
    # raw logger messages except the terminal GCS loss)
    events = []
    for e in report["timeline"]:
        keep = e["kind"] in {"arming", "mode_change", "failsafe", "failure_detector",
                             "flight_phase"} or "Connection to ground station lost" in e["message"]
        if keep:
            events.append({
                "t": round((e["t_us"] - t0) / 1e6, 2),
                "severity": e["severity"],
                "kind": e["kind"],
                "message": e["message"].strip(),
            })

    out = {
        "_provenance": {
            "log_id": "75957ba9-f979-430d-a49c-8ef6e5ceec12",
            "corpus": "PX4 Flight Review public database (review.px4.io)",
            "corpus_url": "https://review.px4.io/plot_app?log=75957ba9-f979-430d-a49c-8ef6e5ceec12",
            "flight_date": "2023-02-26",
            "upload_date": "2023-03-02",
            "uploader_rating": "crash_sw_hw",
            "uploader_description": "at minute 12, my drone started to gain altitude sharply…",
            "license_note": ("The corpus is publicly downloadable but carries no explicit "
                             "redistribution license; this file contains derived, downsampled "
                             "data and analysis results with citation, not the raw log."),
            "engine": f"AIR v{report['generator']['version']}",
            "note": "All values derived from the public log by the AIR engine; deterministic.",
        },
        "flight": {"duration_s": report["flight"]["duration_s"]},
        "series": series,
        "findings": report["findings"],
        "conformance": report["conformance"],
        "events": events,
        "record": {
            "merkle_root": manifest["merkle"]["root_hex"],
            "tree_size": manifest["merkle"]["tree_size"],
            "signature_algorithm": manifest["signature"]["algorithm"],
            "source_digests": [{"name": os.path.basename(s["path"]), "sha256": s["sha256"]}
                               for s in report["sources"]],
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    sizes = {k: len(v["points"]) for k, v in series.items()}
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB); series points: {sizes}; "
          f"events: {len(events)}; findings: {len(report['findings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
