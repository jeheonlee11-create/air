"""Battery health and endurance.

BAT-LOW follows the dronekit-la / ArduPilot LogAnalyzer low-battery convention
(15% remaining).

BAT-SAG measures sag under load, not discharge. A pack's voltage falls slowly
over a whole flight as it discharges (31 V -> 22 V is normal for a 6S pack), so
comparing flight-start voltage with the minimum mostly measures discharge.
Instead each sample is compared with the highest voltage in the preceding
SAG_WINDOW_S seconds (a rolling baseline). Discharge over 10 s is a fraction of
a percent, so a large drop inside the window is the pack failing to hold
voltage under the load at that moment. Where current is logged, the current at
the sag point is quoted so the load is visible.
"""

from __future__ import annotations

from collections import deque

from ..schema import Finding, Incident
from .base import clip_series, extreme, flight_window

REMAINING_WARN = 0.15   # dronekit-la low_battery_threshold 15%
REMAINING_FAIL = 0.07
SAG_WINDOW_S = 10.0      # rolling-baseline window
SAG_FRACTION_WARN = 0.15  # drop below the 10 s rolling max (heuristic, see module doc)
SAG_FRACTION_FAIL = 0.30
SAG_BASIS = ("heuristic: drop below the highest voltage in the preceding 10 s. Healthy LiPo "
             "packs typically sag well under 10% on a load step; 15%+ suggests high internal "
             "resistance, a failing cell, a cold pack or overload")


def worst_sag(t: list[int], v: list[float], window_s: float = SAG_WINDOW_S):
    """Largest fractional drop below the rolling max of the preceding window.

    Returns (sag_fraction, i_sag, i_baseline) or None. O(n) monotonic deque.
    """
    win_us = int(window_s * 1e6)
    dq: deque[int] = deque()   # indices, voltages decreasing
    best = None
    for i, (ts, val) in enumerate(zip(t, v, strict=True)):
        while dq and t[dq[0]] < ts - win_us:
            dq.popleft()
        if dq and v[dq[0]] > 0:
            sag = (v[dq[0]] - val) / v[dq[0]]
            if best is None or sag > best[0]:
                best = (sag, i, dq[0])
        while dq and v[dq[-1]] <= val:
            dq.pop()
        dq.append(i)
    return best


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    rem = inc.series_or_none("batt_remaining")
    if rem is not None:
        worst = extreme(rem, t0, t1, "min")
        if worst and 0 <= worst[1] < REMAINING_WARN:
            t_min, v_min = worst
            findings.append(Finding(
                code="BAT-LOW",
                title=f"Battery depleted to {v_min:.0%} in flight",
                severity="critical" if v_min < REMAINING_FAIL else "warning",
                summary=(
                    f"Estimated battery remaining fell to {v_min:.0%} at {inc.t_label(t_min)}. "
                    f"Below {REMAINING_WARN:.0%} most operations manuals require immediate "
                    f"landing; below {REMAINING_FAIL:.0%} the vehicle is at imminent risk of "
                    f"power loss and uncontrolled descent."
                ),
                evidence=[{"t_us": t_min, "source": rem.source, "value": round(v_min, 3),
                           "note": "minimum battery remaining during flight"}],
                threshold={"metric": "battery_remaining", "warn_below": REMAINING_WARN,
                           "fail_below": REMAINING_FAIL,
                           "basis": "dronekit-la low_battery_threshold=15%"},
            ))

    volt = inc.series_or_none("batt_v")
    if volt is not None:
        t, v = clip_series(volt, t0, t1)
        hit = worst_sag(t, v) if len(v) > 10 else None
        if hit and hit[0] > SAG_FRACTION_WARN:
            sag, i, ib = hit
            cur = inc.series_or_none("batt_current_a")
            load = ""
            evidence = [
                {"t_us": t[ib], "source": volt.source, "value": round(v[ib], 2),
                 "note": f"baseline: highest voltage in the preceding {SAG_WINDOW_S:.0f} s"},
                {"t_us": t[i], "source": volt.source, "value": round(v[i], 2),
                 "note": f"voltage at worst sag ({sag:.0%} below baseline)"},
            ]
            if cur is not None:
                a_sag = cur.at_or_before(t[i], max_age_us=1_000_000)
                a_base = cur.at_or_before(t[ib], max_age_us=1_000_000)
                if a_sag is not None and a_base is not None:
                    load = (f" Current was {a_base:.1f} A at the baseline sample and "
                            f"{a_sag:.1f} A at the sag point.")
                    evidence.append({"t_us": t[i], "source": cur.source, "value": round(a_sag, 1),
                                     "note": "battery current at worst sag"})
            findings.append(Finding(
                code="BAT-SAG",
                title=f"Voltage sag under load ({sag:.0%} within {SAG_WINDOW_S:.0f} s)",
                severity="critical" if sag > SAG_FRACTION_FAIL else "warning",
                summary=(
                    f"Battery voltage fell from {v[ib]:.1f} V to {v[i]:.1f} V within "
                    f"{(t[i] - t[ib]) / 1e6:.1f} s, reaching the low point at "
                    f"{inc.t_label(t[i])} ({sag:.0%} below the recent baseline).{load} Normal "
                    f"discharge cannot explain a drop this fast; it indicates the pack could not "
                    f"hold voltage under load (high internal resistance, a failing or cold cell, "
                    f"overload, or a power-system fault), which can cut power before the "
                    f"remaining-capacity estimate reaches zero."
                ),
                evidence=evidence,
                threshold={"metric": "voltage_sag_fraction_vs_rolling_max",
                           "window_s": SAG_WINDOW_S, "warn_above": SAG_FRACTION_WARN,
                           "fail_above": SAG_FRACTION_FAIL, "basis": SAG_BASIS},
            ))

    return findings
