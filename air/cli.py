"""AIR command-line interface.

    python -m air.cli investigate <log.ulg> [--procedures rules.json] [--out DIR]
                                            [--no-timestamp]

Thin wrapper over air.api.investigate_log — the single analysis pipeline
shared with the web demo.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .api import UnsupportedLogError, investigate_log
from .evidence.signing import public_key_fingerprint


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

    print(f"AIR v{__version__} — ingesting {os.path.basename(args.log)}")
    try:
        result = investigate_log(args.log, args.procedures, out, args.keys,
                                 with_timestamp=not args.no_timestamp)
    except UnsupportedLogError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return 2

    inc, findings, conformance, manifest = (result["incident"], result["findings"],
                                            result["conformance"], result["manifest"])
    print(f"  incident {inc.incident_id}")
    print(f"  {len(inc.series)} series, {len(inc.events)} events, {inc.duration_s:.1f}s of log")
    if conformance:
        print(f"  conformance: {conformance['passed']} pass / {conformance['failed']} fail / "
              f"{conformance['not_evaluable']} not evaluable")
    for f in findings:
        print(f"  [{f.severity.upper():8s}] {f.code}: {f.title}")

    n_crit = sum(1 for f in findings if f.severity == "critical")
    print(f"\n  bundle: {out}")
    print(f"  merkle root: {manifest['merkle']['root_hex'][:32]}…")
    fp = public_key_fingerprint(manifest["signature"]["public_key_pem"])
    print(f"  signing key fingerprint (sha256): {fp}")
    print("    publish this out of band; verifiers run: python3 verify.py --fingerprint <it>")
    print(f"  rfc3161: {manifest['rfc3161_timestamp'].get('status')}")
    print(f"  {n_crit} critical finding(s) — report.html / report.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
