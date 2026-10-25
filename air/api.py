"""Programmatic entry point shared by the CLI and the web demo.

There is exactly one analysis implementation; both frontends call this.
"""

from __future__ import annotations

import os

from . import __version__
from .analyze import ProcedureError, check_conformance, load_procedures, run_all_analyzers
from .evidence import build_bundle
from .ingest import ingest_ulog
from .report import render_html
from .schema import SEVERITY_ORDER

__all__ = ["ProcedureError", "UnsupportedLogError", "investigate_log"]


class UnsupportedLogError(Exception):
    """The file is not a parseable PX4 ULog."""


def investigate_log(log_path: str, procedures: str | None, out_dir: str,
                    key_dir: str, with_timestamp: bool) -> dict:
    """Run the full pipeline. Returns a dict with incident, findings,
    conformance, report, manifest, out_dir. Raises UnsupportedLogError for
    files pyulog cannot parse and ProcedureError for an invalid ruleset
    (checked first, before any parsing work)."""
    if procedures:
        load_procedures(procedures)
    try:
        inc = ingest_ulog(log_path)
    except (TypeError, ValueError, IndexError) as e:
        # pyulog raises TypeError("Invalid file format ...") for non-ULog input
        raise UnsupportedLogError(
            f"Not a parseable PX4 ULog file: {e}. AIR v{__version__} supports "
            f"PX4 .ulg logs only; ArduPilot dataflash and DJI logs are not yet "
            f"supported.") from e

    findings = run_all_analyzers(inc)

    conformance = None
    if procedures:
        conformance, conf_findings = check_conformance(inc, procedures)
        findings.extend(conf_findings)

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.code))

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

    return {"incident": inc, "findings": findings, "conformance": conformance,
            "report": report, "manifest": manifest, "out_dir": out_dir}
