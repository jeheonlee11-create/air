"""Vibration and IMU consistency.

- accel_vibration_metric thresholds follow PX4 Flight Review conventions
  (warn ~15 m/s^2, fail ~30 m/s^2 for multirotors).
- Accelerometer clipping is a direct, unambiguous signal: the sensor hit its
  measurement limit, which corrupts altitude/position estimation.
- IMU inconsistency compares independent IMUs against each other — a built-in
  cross-sensor conflict measure.
"""

from __future__ import annotations

from ..schema import Finding, Incident
from .base import clip_series, extreme, flight_window

VIB_WARN = 15.0   # m/s^2, PX4 Flight Review convention
VIB_FAIL = 30.0
ACCEL_INCONSISTENCY_WARN = 0.7   # m/s^2, heuristic near PX4 defaults
ACCEL_INCONSISTENCY_FAIL = 1.5


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    vib = inc.series_or_none("vib_accel_ms2")
    if vib is not None:
        worst = extreme(vib, t0, t1, "max")
        if worst and worst[1] > VIB_WARN:
            t_max, v_max = worst
            _, vals = clip_series(vib, t0, t1)
            mean = sum(vals) / len(vals)
            findings.append(Finding(
                code="VIB-HIGH",
                title=f"High vibration (peak {v_max:.1f} m/s²)",
                severity="critical" if v_max > VIB_FAIL else "warning",
                summary=(
                    f"Accelerometer vibration peaked at {v_max:.1f} m/s² at {inc.t_label(t_max)} "
                    f"(flight mean {mean:.1f} m/s²). Sustained vibration above {VIB_FAIL:.0f} m/s² "
                    f"is strongly associated with altitude and position estimation failures; "
                    f"common causes are damaged propellers, loose mounts, or airframe resonance."
                ),
                evidence=[{"t_us": t_max, "source": vib.source, "value": round(v_max, 1),
                           "note": "peak accel vibration metric"}],
                threshold={"metric": "accel_vibration_metric_ms2", "warn_above": VIB_WARN,
                           "fail_above": VIB_FAIL, "basis": "PX4 Flight Review convention"},
            ))

    clip = inc.series_or_none("accel_clip_count")
    if clip is not None:
        t, v = clip_series(clip, t0, t1)
        if v and (v[-1] - v[0]) > 0:
            n = int(v[-1] - v[0])
            first_t = next((ts for ts, val in zip(t, v) if val > v[0]), t[0])
            findings.append(Finding(
                code="VIB-CLIP",
                title=f"Accelerometer clipping occurred ({n} clip events in flight)",
                severity="critical" if n > 100 else "warning",
                summary=(
                    f"The accelerometer hit its measurement range {n} times during the flight, "
                    f"beginning at {inc.t_label(first_t)}. Clipping means the true acceleration "
                    f"exceeded what the sensor can measure — data during clipped intervals is "
                    f"invalid, and the estimator was flying partially blind. Clipping bursts also "
                    f"commonly mark the moment of a hard impact."
                ),
                evidence=[{"t_us": first_t, "source": clip.source, "value": n,
                           "note": "accumulated clip count delta over flight"}],
                threshold={"metric": "accel_clipping_delta", "warn_above": 0, "fail_above": 100,
                           "basis": "clipping invalidates samples by definition"},
            ))

    inc_s = inc.series_or_none("imu_accel_inconsistency")
    if inc_s is not None:
        worst = extreme(inc_s, t0, t1, "max")
        if worst and worst[1] > ACCEL_INCONSISTENCY_WARN:
            t_max, v_max = worst
            findings.append(Finding(
                code="IMU-DISAGREE",
                title=f"Independent IMUs disagreed (peak {v_max:.2f} m/s²)",
                severity="critical" if v_max > ACCEL_INCONSISTENCY_FAIL else "warning",
                kind="conflict",
                summary=(
                    f"The vehicle's redundant IMUs reported accelerations differing by up to "
                    f"{v_max:.2f} m/s² at {inc.t_label(t_max)}. Redundant sensors measuring the "
                    f"same physical quantity should agree; sustained disagreement means at least "
                    f"one sensor was faulty, mis-calibrated, or affected by localized vibration — "
                    f"and any conclusion drawn from a single IMU's data around this time should "
                    f"be treated with caution."
                ),
                evidence=[{"t_us": t_max, "source": inc_s.source, "value": round(v_max, 2),
                           "note": "peak accel inconsistency between IMUs"}],
                threshold={"metric": "accel_inconsistency_m_s_s",
                           "warn_above": ACCEL_INCONSISTENCY_WARN,
                           "fail_above": ACCEL_INCONSISTENCY_FAIL,
                           "basis": "heuristic near PX4 sensors module defaults"},
            ))

    return findings
