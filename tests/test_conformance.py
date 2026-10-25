"""Conformance metrics: altitude reference, tolerance and verdicts."""

import json

from air.analyze.conformance import check_conformance, verdict

from .synth import arm, incident, ramp, series


def _rules(tmp_path, *rules):
    p = tmp_path / "proc.json"
    p.write_text(json.dumps({"name": "test rules", "rules": list(rules)}))
    return str(p)


ALT_RULE = {"id": "ALT-1", "description": "max 120 m", "metric": "max_alt_agl_m",
            "op": "<=", "limit": 120}


def test_verdict_bands():
    assert verdict(119.9, "<=", 120, 1.0) == "PASS"
    assert verdict(120.04, "<=", 120, 1.0) == "MARGINAL"
    assert verdict(121.01, "<=", 120, 1.0) == "FAIL"
    assert verdict(120.04, "<=", 120, 0.0) == "FAIL"
    assert verdict(5.5, ">=", 6, 1.0) == "MARGINAL"
    assert verdict(4, ">=", 6, 1.0) == "FAIL"


def _alt_incident(peak):
    up = ramp("alt_above_home_m", 0, 50, 0, peak, units="m above home")
    down = ramp("alt_above_home_m", 50, 100, peak, 0)
    s = series("alt_above_home_m", list(zip([t / 1e6 for t in up.t_us + down.t_us],
                                            up.values + down.values, strict=True)))
    return incident(t1=100, series_list=[s], events=[arm(0), arm(100, False)])


def test_altitude_within_tolerance_is_marginal_not_fail(tmp_path):
    summary, findings = check_conformance(_alt_incident(120.04), _rules(tmp_path, ALT_RULE))
    r = summary["results"][0]
    assert r["verdict"] == "MARGINAL" and r["tolerance"] == 1.0
    assert summary["marginal"] == 1 and summary["failed"] == 0
    assert findings[0].severity == "warning"
    assert "home" in r["evidence"]["reference"]


def test_altitude_beyond_tolerance_fails(tmp_path):
    summary, findings = check_conformance(_alt_incident(125), _rules(tmp_path, ALT_RULE))
    assert summary["results"][0]["verdict"] == "FAIL"
    assert findings[0].severity == "critical"


def test_rule_tolerance_overrides_default(tmp_path):
    rule = {**ALT_RULE, "tolerance": 0}
    summary, _ = check_conformance(_alt_incident(120.04), _rules(tmp_path, rule))
    assert summary["results"][0]["verdict"] == "FAIL"
    assert summary["results"][0]["tolerance_basis"] == "rule"


def test_barometric_altitude_is_never_used_as_agl(tmp_path):
    baro = ramp("alt_baro_m", 0, 100, 300, 350)      # MSL-like, would "fail" 120 m
    ekf = ramp("alt_local_m", 0, 100, 0, 50)
    inc = incident(t1=100, series_list=[baro, ekf], events=[arm(0), arm(100, False)])
    summary, findings = check_conformance(inc, _rules(tmp_path, ALT_RULE))
    r = summary["results"][0]
    assert r["verdict"] == "NOT_EVALUABLE"
    assert "not substituted" in r["reason"]
    assert findings[0].title.startswith("Rule ALT-1 could not be evaluated")


def test_distance_requires_home(tmp_path):
    rule = {"id": "DIST-1", "description": "500 m", "metric": "max_dist_home_m",
            "op": "<=", "limit": 500}
    inc = incident(t1=100, events=[arm(0)])
    summary, _ = check_conformance(inc, _rules(tmp_path, rule))
    assert summary["results"][0]["verdict"] == "NOT_EVALUABLE"
    inc.series["dist_home_m"] = ramp("dist_home_m", 0, 100, 0, 499.5)
    summary, _ = check_conformance(inc, _rules(tmp_path, rule))
    assert summary["results"][0]["verdict"] == "PASS"
