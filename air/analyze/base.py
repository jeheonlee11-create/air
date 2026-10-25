"""Analyzer registry and shared helpers.

Every analyzer is a pure function Incident -> list[Finding]. Thresholds are
deterministic and documented with their basis (which ruleset or firmware
constant they derive from), so every finding can be defended line-by-line.
No ML, no heuristics that can't be explained to an opposing expert.
"""

from __future__ import annotations

import re

from ..schema import Finding, Incident, Series, TimelineEvent

_ARMED_RE = re.compile(r"\bARMED\b")
_DISARMED_RE = re.compile(r"\bDISARMED\b")


def arming_state(ev: TimelineEvent) -> bool | None:
    """True for an arm event, False for a disarm event, None otherwise.

    Ingest records the state in ev.data["armed"]; the message text is only a
    fallback, matched on whole words so "DISARMED" is never read as "ARMED".
    """
    if ev.kind != "arming":
        return None
    if isinstance(ev.data.get("armed"), bool):
        return ev.data["armed"]
    if _DISARMED_RE.search(ev.message):
        return False
    if _ARMED_RE.search(ev.message):
        return True
    return None


def arm_cycles(inc: Incident) -> list[tuple[int, int | None]]:
    """[(t_armed, t_disarmed or None), ...] in time order.

    A disarm with no preceding arm is ignored; a repeated arm while already
    armed is ignored. The last cycle has t_disarmed=None if the log ends armed.
    """
    cycles: list[tuple[int, int | None]] = []
    armed_at: int | None = None
    for ev in inc.sorted_events():
        state = arming_state(ev)
        if state is True and armed_at is None:
            armed_at = ev.t_us
        elif state is False and armed_at is not None:
            cycles.append((armed_at, ev.t_us))
            armed_at = None
    if armed_at is not None:
        cycles.append((armed_at, None))
    return cycles


def flight_window(inc: Incident) -> tuple[int, int] | None:
    """(first arm, last disarm or end of log); None if never armed.

    With several arm cycles the window spans all of them, including any
    ground time in between; analyzers report the timestamp of what they find.
    """
    cycles = arm_cycles(inc)
    if not cycles:
        return None
    last_end = cycles[-1][1]
    return cycles[0][0], (last_end if last_end is not None else inc.t1_us)


def clip_series(s: Series, t0: int, t1: int) -> tuple[list[int], list[float]]:
    t, v = [], []
    for ts, val in zip(s.t_us, s.values, strict=False):
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
