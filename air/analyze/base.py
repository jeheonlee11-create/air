"""Analyzer registry and shared helpers.

Every analyzer is a pure function Incident -> list[Finding]. Thresholds are
deterministic and documented with their basis (which ruleset or firmware
constant they derive from), so every finding can be defended line-by-line.
No ML, no heuristics that can't be explained to an opposing expert.
"""

from __future__ import annotations

from ..schema import Finding, Incident, Series


def flight_window(inc: Incident) -> tuple[int, int] | None:
    """(t_us_takeoff, t_us_end_of_flight) using arming/land events; None if never armed."""
    armed_t, disarmed_t = None, None
    for ev in inc.sorted_events():
        if ev.kind == "arming":
            if "ARMED" in ev.message and armed_t is None:
                armed_t = ev.t_us
            if "DISARMED" in ev.message and armed_t is not None:
                disarmed_t = ev.t_us
    if armed_t is None:
        return None
    return armed_t, (disarmed_t or inc.t1_us)


def clip_series(s: Series, t0: int, t1: int) -> tuple[list[int], list[float]]:
    t, v = [], []
    for ts, val in zip(s.t_us, s.values):
        if t0 <= ts <= t1:
            t.append(ts)
            v.append(val)
    return t, v


def extreme(s: Series, t0: int, t1: int, mode: str = "max") -> tuple[int, float] | None:
    t, v = clip_series(s, t0, t1)
    if not v:
        return None
    if mode == "max":
        i = max(range(len(v)), key=lambda k: v[k])
    else:
        i = min(range(len(v)), key=lambda k: v[k])
    return t[i], v[i]


def run_all_analyzers(inc: Incident) -> list[Finding]:
    # imported here to avoid circulars
    from . import battery, conflict, ekf, gps, integrity, vibration

    findings: list[Finding] = []
    for mod in (integrity, gps, ekf, vibration, battery, conflict):
        findings.extend(mod.analyze(inc))
    return findings
