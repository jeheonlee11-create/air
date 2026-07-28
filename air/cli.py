"""AIR command-line interface.

    python -m air.cli investigate <log.ulg> [--procedures rules.json] [--out DIR]
                                            [--no-timestamp]

Pipeline: ingest -> analyze -> conformance -> report.json (canonical, signed,
Merkle-committed, optionally RFC 3161 timestamped) -> report.html rendering.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .analyze import check_conformance, run_all_analyzers
from .evidence import build_bundle
from .ingest import ingest_ulog
from .report import render_html
from .schema import SEVERITY_ORDER


def investigate(log_path: str, procedures: str | None, out_dir: str,
                key_dir: str, with_timestamp: bool) -> int:
    print(f"AIR v{__version__} — ingesting {os.path.basename(log_path)}")
    inc = ingest_ulog(log_path)
    print(f"  incident {inc.incident_id}")
    print(f"  {len(inc.series)} series, {len(inc.events)} events, {inc.duration_s:.1f}s of log")

    findings = run_all_analyzers(inc)

    conformance = None
    if procedures:
        conformance, conf_findings = check_conformance(inc, procedures)
        findings.extend(conf_findings)
        print(f"  conformance: {conformance['passed']} pass / {conformance['failed']} fail / "
              f"{conformance['not_evaluable']} not evaluable")

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.code))
    for f in findings:
        print(f"  [{f.severity.upper():8s}] {f.code}: {f.title}")

    report = {
        "format": "air-incident-record/1",
        "generator": {"name": "AIR", "version": __version__,
                      "determinism": "rule-based; thresholds documented per finding"},
        "incident_id": inc.incident_id,
        "created_utc": inc.created_utc,
        "aircraft": inc.aircraft,
        "flight": {
            "t0_us": inc.t0_us, "t1_us": inc.t1_us,
            "duration_s": round(inc.duration_s, 2),
            "utc_anchor": ({"offset_us": inc.utc_anchor.offset_us, "source": inc.utc_anchor.source}
                           if inc.utc_anchor else None),
            "home": inc.home,
        },
        "sources": [{"path": s.path, "sha256": s.sha256, "size_bytes": s.size_bytes,
                     "kind": s.kind, "meta": s.meta} for s in inc.sources],
        "findings": [f.to_dict() for f in findings],
        "conformance": conformance,
        "timeline": [{"t_us": e.t_us, "severity": e.severity, "kind": e.kind,
                      "message": e.message, "source": e.source} for e in inc.sorted_events()],
        "series_inventory": [
            {"name": s.name, "source": s.source, "samples": len(s.t_us), "units": s.units}
            for s in inc.series.values()],
    }

    os.makedirs(out_dir, exist_ok=True)
    manifest = build_bundle(report, out_dir, key_dir, with_timestamp=with_timestamp)

    html = render_html(inc, findings, conformance, manifest, __version__)
    with open(os.path.join(out_dir, "report.html"), "w") as f:
        f.write(html)

    n_crit = sum(1 for f in findings if f.severity == "critical")
    print(f"\n  bundle: {out_dir}")
    print(f"  merkle root: {manifest['merkle']['root_hex'][:32]}…")
    ts = manifest["rfc3161_timestamp"].get("status")
    print(f"  rfc3161: {ts}")
    print(f"  {n_crit} critical finding(s) — report.html / report.json written")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="air")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("investigate", help="investigate a flight log")
    q.add_argument("log", help="path to PX4 .ulg flight log")
    q.add_argument("--procedures", help="path to procedures JSON ruleset")
    q.add_argument("--out", default=None, help="output bundle directory")
    q.add_argument("--keys", default="keys", help="signing key directory")
    q.add_argument("--no-timestamp", action="store_true", help="skip RFC 3161 timestamping")
    args = p.parse_args(argv)

    out = args.out or os.path.join(
        "bundles", os.path.splitext(os.path.basename(args.log))[0])
    return investigate(args.log, args.procedures, out, args.keys,
                       with_timestamp=not args.no_timestamp)


if __name__ == "__main__":
    sys.exit(main())
