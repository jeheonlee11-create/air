"""Procedure conformance — flight-vs-written-procedure verdicts.

The operator supplies their procedures as declarative rules (JSON). Each rule
is evaluated against the normalized telemetry and returns PASS / FAIL /
NOT_EVALUABLE with the extreme value and its timestamp as evidence.

NOT_EVALUABLE is a first-class verdict: if the data needed to check a rule is
missing, the record says so instead of silently passing — absence of evidence
is reported, never hidden.

MARGINAL is the verdict when a value is past the limit by no more than the
rule's measurement tolerance: the data cannot tell compliance from violation.

Altitude rules use height above the home (launch) position. Barometric and
EKF-origin altitude are never substituted: they have different references, and
a rule written as "AGL" cannot be checked against them honestly.
"""

from __future__ import annotations

import json

from ..ingest.ulog import NAV_STATE
from ..schema import Finding, Incident, SourceFile
from .base import clip_series, extreme, flight_window

# Default measurement tolerance per metric, used when a rule gives none. An
# observation past the limit by less than this is MARGINAL, not FAIL: the
# measurement cannot distinguish it from compliance. Order of magnitude of the
# PX4 EKF's own position/velocity uncertainty in GNSS-aided flight; operators
# should set "tolerance" per rule from their own equipment.
DEFAULT_TOLERANCE = {
    "max_alt_agl_m": 1.0,
    "max_dist_home_m": 2.0,
    "max_groundspeed_ms": 0.5,
}
TOLERANCE_BASIS = ("AIR default measurement tolerance (order of PX4 EKF position/velocity "
                   "uncertainty); override per rule with \"tolerance\"")

ALT_REFERENCE = ("height above the home (launch) position: home_position.z minus "
                 "vehicle_local_position.z. Equals height above ground only where the "
                 "terrain is level with the launch point.")


def _extreme_metric(inc: Incident, series_name: str, t0: int, t1: int, mode: str,
                    missing: str, reference: str = "", as_int: bool = False):
    s = inc.series_or_none(series_name)
    if s is None:
        return None, missing
    ex = extreme(s, t0, t1, mode)
    if not ex:
        return None, "no in-flight samples"
    ev = {"t_us": ex[0], "source": s.source,
          "value": int(ex[1]) if as_int else round(ex[1], 2)}
    if reference:
        ev["reference"] = reference
    return ex[1], ev


def _metric(inc: Incident, name: str, t0: int, t1: int):
    """Compute a named conformance metric. Returns (value, evidence) or (None, reason)."""
    if name == "max_alt_agl_m":
        value, ev = _extreme_metric(
            inc, "alt_above_home_m", t0, t1, "max",
            "no home-relative height in log (home_position not logged or not valid); "
            "barometric and EKF-origin altitude use other references and are not substituted",
            reference=ALT_REFERENCE)
        epv = inc.series_or_none("alt_epv_m")
        if value is not None and epv is not None:
            e = epv.at_or_before(ev["t_us"], max_age_us=1_000_000)
            if e is not None:
                ev["estimator_vertical_uncertainty_m"] = round(e, 2)
        return value, ev
    if name == "max_dist_home_m":
        return _extreme_metric(
            inc, "dist_home_m", t0, t1, "max",
            "no home-relative horizontal position in log (home_position not logged or not valid)",
            reference="horizontal distance from the home (launch) position")
    if name == "max_groundspeed_ms":
        return _extreme_metric(inc, "groundspeed_ms", t0, t1, "max", "no velocity series in log")
    if name == "min_gps_sats":
        return _extreme_metric(inc, "gps_nsats", t0, t1, "min",
                               "no GPS satellite-count series in log", as_int=True)
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


def verdict(value, op: str, limit, tolerance: float = 0.0) -> str:
    """PASS / MARGINAL / FAIL. MARGINAL: past the limit by no more than the tolerance."""
    if _passes(value, op, limit):
        return "PASS"
    if op == "<=" and value <= limit + tolerance:
        return "MARGINAL"
    if op == ">=" and value >= limit - tolerance:
        return "MARGINAL"
    return "FAIL"


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
        tol = rule.get("tolerance", DEFAULT_TOLERANCE.get(rule["metric"], 0.0))
        v = verdict(value, rule["op"], rule["limit"], tol)
        result = {
            "id": rid, "description": desc,
            "verdict": v,
            "observed": value if not isinstance(value, float) else round(value, 2),
            "limit": rule["limit"], "op": rule["op"],
            "evidence": evidence,
        }
        if rule["op"] in ("<=", ">="):
            result["tolerance"] = tol
            result["tolerance_basis"] = ("rule" if "tolerance" in rule else
                                         TOLERANCE_BASIS if tol else "none (exact limit)")
        results.append(result)
        if v == "PASS":
            continue
        shown = ", ".join(value) if isinstance(value, list) else f"{value:.2f}" if isinstance(value, float) else str(value)
        ref = evidence.get("reference") if isinstance(evidence, dict) else None
        ref_txt = f" Reference: {ref}" if ref else ""
        if v == "MARGINAL":
            findings.append(Finding(
                code=f"PROC-{rid}", kind="conformance", severity="warning",
                title=f"Procedure limit marginally exceeded: {desc}",
                summary=(
                    f"Rule {rid} ('{desc}') requires {rule['metric']} {rule['op']} "
                    f"{rule['limit']}; the flight recorded {shown}, which is past the limit by "
                    f"less than the {tol} measurement tolerance. The data cannot establish "
                    f"either conformance or a violation.{ref_txt}"
                ),
                evidence=[evidence] if isinstance(evidence, dict) else [],
                threshold={"metric": rule["metric"], "op": rule["op"], "limit": rule["limit"],
                           "tolerance": tol,
                           "basis": proc.get("name", "operator procedures")},
            ))
            continue
        findings.append(Finding(
            code=f"PROC-{rid}", kind="conformance", severity="critical",
            title=f"Procedure violated: {desc}",
            summary=(
                f"Rule {rid} ('{desc}') requires {rule['metric']} {rule['op']} "
                f"{rule['limit']}; the flight recorded {shown}"
                + (f", beyond the {tol} measurement tolerance" if tol else "")
                + f". See conformance table for the evidence sample.{ref_txt}"
            ),
            evidence=[evidence] if isinstance(evidence, dict) else [],
            threshold={"metric": rule["metric"], "op": rule["op"], "limit": rule["limit"],
                       **({"tolerance": tol} if tol else {}),
                       "basis": proc.get("name", "operator procedures")},
        ))

    summary = {
        "procedures_name": proc.get("name", ""),
        "rules_total": len(results),
        "passed": sum(1 for r in results if r["verdict"] == "PASS"),
        "failed": sum(1 for r in results if r["verdict"] == "FAIL"),
        "marginal": sum(1 for r in results if r["verdict"] == "MARGINAL"),
        "not_evaluable": sum(1 for r in results if r["verdict"] == "NOT_EVALUABLE"),
        "results": results,
    }
    return summary, findings
