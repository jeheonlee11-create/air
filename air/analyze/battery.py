"""Battery health and endurance.

Thresholds follow the retired ArduPilot LogAnalyzer battery conventions
(low-battery 15%) and standard lithium-polymer sag behavior.
"""

from __future__ import annotations

from ..schema import Finding, Incident
from .base import clip_series, extreme, flight_window

REMAINING_WARN = 0.15   # dronekit-la low_battery_threshold 15%
REMAINING_FAIL = 0.07
SAG_FRACTION_WARN = 0.25  # >25% voltage drop from flight start


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
        if len(v) > 10:
            start_v = sum(v[:5]) / 5
            min_i = min(range(len(v)), key=lambda i: v[i])
            sag = (start_v - v[min_i]) / start_v if start_v > 0 else 0
            if sag > SAG_FRACTION_WARN:
                findings.append(Finding(
                    code="BAT-SAG",
                    title=f"Severe voltage sag ({sag:.0%} below flight-start voltage)",
                    severity="warning",
                    summary=(
                        f"Battery voltage sagged from {start_v:.1f} V at flight start to "
                        f"{v[min_i]:.1f} V at {inc.t_label(t[min_i])} ({sag:.0%} drop). Sag of "
                        f"this magnitude under load indicates a degraded or cold battery, an "
                        f"overloaded aircraft, or a failing cell — all of which can cause sudden "
                        f"power loss before the remaining-capacity estimate reaches zero."
                    ),
                    evidence=[{"t_us": t[min_i], "source": volt.source, "value": round(v[min_i], 2),
                               "note": f"minimum voltage; flight started at {start_v:.2f} V"}],
                    threshold={"metric": "voltage_sag_fraction", "warn_above": SAG_FRACTION_WARN,
                               "basis": "LiPo sag heuristic"},
                ))

    return findings
