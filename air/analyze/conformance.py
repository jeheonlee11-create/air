"""Procedure conformance — flight-vs-written-procedure verdicts.

The operator supplies their procedures as declarative rules (JSON). Each rule
is evaluated against the normalized telemetry and returns PASS / FAIL /
NOT_EVALUABLE with the extreme value and its timestamp as evidence.

NOT_EVALUABLE is a first-class verdict: if the data needed to check a rule is
missing, the record says so instead of silently passing — absence of evidence
is reported, never hidden.
"""

from __future__ import annotations

import json

from ..ingest.ulog import NAV_STATE
from ..schema import Finding, Incident, SourceFile
from .base import clip_series, extreme, flight_window


def _metric(inc: Incident, name: str, t0: int, t1: int):
    """Compute a named conformance metric. Returns (value, evidence) or (None, reason)."""
    if name == "max_alt_agl_m":
        s = inc.series_or_none("alt_local_m") or inc.series_or_none("alt_baro_m")
        if s is None:
            return None, "no altitude series in log"
        ex = extreme(s, t0, t1, "max")
        return (ex[1], {"t_us": ex[0], "source": s.source, "value": round(ex[1], 2)}) if ex else (None, "no in-flight samples")
    if name == "max_dist_home_m":
        s = inc.series_or_none("dist_home_m")
        if s is None:
            return None, "no horizontal position series in log"
        ex = extreme(s, t0, t1, "max")
        return (ex[1], {"t_us": ex[0], "source": s.source, "value": round(ex[1], 2)}) if ex else (None, "no in-flight samples")
    if name == "max_groundspeed_ms":
        s = inc.series_or_none("groundspeed_ms")
        if s is None:
            return None, "no velocity series in log"
        ex = extreme(s, t0, t1, "max")
        return (ex[1], {"t_us": ex[0], "source": s.source, "value": round(ex[1], 2)}) if ex else (None, "no in-flight samples")
    if name == "min_gps_sats":
        s = inc.series_or_none("gps_nsats")
        if s is None:
            return None, "no GPS satellite-count series in log"
        ex = extreme(s, t0, t1, "min")
        return (ex[1], {"t_us": ex[0], "source": s.source, "value": int(ex[1])}) if ex else (None, "no in-flight samples")
    if name == "battery_at_landing_pct":
        s = inc.series_or_none("batt_remaining")
        if s is None:
            return None, "no battery-remaining series in log"
        t, v = clip_series(s, t0, t1)
        if not v:
            return None, "no in-flight samples"
        return v[-1] * 100.0, {"t_us": t[-1], "source": s.source, "value": round(v[-1] * 100.0, 1)}
    if name == "modes_flown":
        modes = set()
        first_at = {}
        for ev in inc.sorted_events():
            if ev.kind == "mode_change" and t0 <= ev.t_us <= t1:
                m = NAV_STATE.get(ev.data.get("new"), f"NAV_STATE_{ev.data.get('new')}")
                modes.add(m)
                first_at.setdefault(m, ev.t_us)
        return sorted(modes), {"source": "px4_ulog:vehicle_status.nav_state", "first_at": first_at}
    return None, f"unknown metric '{name}'"


def _passes(value, op: str, limit) -> bool:
    if op == "<=":
        return value <= limit
    if op == ">=":
        return value >= limit
    if op == "not_contains":
        return not any(m in value for m in limit)
    raise ValueError(f"unknown op {op}")


def check_conformance(inc: Incident, procedures_path: str) -> tuple[dict, list[Finding]]:
    with open(procedures_path) as f:
        proc = json.load(f)
    inc.sources.append(SourceFile.from_path(procedures_path, kind="procedures",
                                            meta={"name": proc.get("name", "")}))
    win = flight_window(inc)
    results = []
    findings: list[Finding] = []

    for rule in proc.get("rules", []):
        rid, desc = rule["id"], rule["description"]
        if win is None:
            results.append({"id": rid, "description": desc, "verdict": "NOT_EVALUABLE",
                            "reason": "no flight in log"})
            continue
        value, evidence = _metric(inc, rule["metric"], *win)
        if value is None:
            results.append({"id": rid, "description": desc, "verdict": "NOT_EVALUABLE",
                            "reason": evidence})
            findings.append(Finding(
                code=f"PROC-{rid}", kind="conformance", severity="warning",
                title=f"Rule {rid} could not be evaluated",
                summary=f"'{desc}' could not be checked: {evidence}. This gap is itself part of "
                        f"the record — the operator cannot demonstrate conformance with this rule "
                        f"from the available evidence.",
            ))
            continue
        ok = _passes(value, rule["op"], rule["limit"])
        results.append({
            "id": rid, "description": desc,
            "verdict": "PASS" if ok else "FAIL",
            "observed": value if not isinstance(value, float) else round(value, 2),
            "limit": rule["limit"], "op": rule["op"],
            "evidence": evidence,
        })
        if not ok:
            shown = ", ".join(value) if isinstance(value, list) else f"{value:.2f}" if isinstance(value, float) else str(value)
            findings.append(Finding(
                code=f"PROC-{rid}", kind="conformance", severity="critical",
                title=f"Procedure violated: {desc}",
                summary=(
                    f"Rule {rid} ('{desc}') requires {rule['metric']} {rule['op']} "
                    f"{rule['limit']}; the flight recorded {shown}. See conformance table for "
                    f"the evidence sample."
                ),
                evidence=[evidence] if isinstance(evidence, dict) else [],
                threshold={"metric": rule["metric"], "op": rule["op"], "limit": rule["limit"],
                           "basis": proc.get("name", "operator procedures")},
            ))

    summary = {
        "procedures_name": proc.get("name", ""),
        "rules_total": len(results),
        "passed": sum(1 for r in results if r["verdict"] == "PASS"),
        "failed": sum(1 for r in results if r["verdict"] == "FAIL"),
        "not_evaluable": sum(1 for r in results if r["verdict"] == "NOT_EVALUABLE"),
        "results": results,
    }
    return summary, findings
