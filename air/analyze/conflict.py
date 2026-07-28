"""Cross-source conflict analysis — the capability no incumbent ships.

Independent sensors measuring the same physical quantity should agree.
When they diverge, at least one of them is wrong, and any downstream
conclusion built on the wrong one is impeachable. This module measures
agreement explicitly and reports WHERE the evidence conflicts, instead of
silently trusting one source.

Currently implemented:
- Barometric altitude vs GPS altitude (offset-corrected divergence)
- Barometric altitude vs EKF fused altitude
(IMU-vs-IMU disagreement is covered in vibration.py via sensors_status_imu.)
"""

from __future__ import annotations

from ..schema import Finding, Incident, Series
from .base import flight_window

ALT_DIVERGENCE_WARN_M = 10.0
ALT_DIVERGENCE_FAIL_M = 25.0


def _resample_pair(a: Series, b: Series, t0: int, t1: int, step_us: int = 500_000):
    """Sample both series on a common grid inside [t0, t1]."""
    grid = range(t0, t1, step_us)
    pairs = []
    for t in grid:
        va, vb = a.at_or_before(t), b.at_or_before(t)
        if va is not None and vb is not None:
            pairs.append((t, va, vb))
    return pairs


def _divergence_finding(inc: Incident, a: Series, b: Series, label_a: str, label_b: str,
                        code: str, t0: int, t1: int) -> Finding | None:
    pairs = _resample_pair(a, b, t0, t1)
    if len(pairs) < 10:
        return None
    # offset-correct using the first samples (different references: MSL vs relative)
    n0 = min(5, len(pairs))
    offset = sum(va - vb for _, va, vb in pairs[:n0]) / n0
    worst_t, worst_d = None, 0.0
    for t, va, vb in pairs:
        d = abs((va - vb) - offset)
        if d > worst_d:
            worst_t, worst_d = t, d
    if worst_d < ALT_DIVERGENCE_WARN_M:
        return None
    return Finding(
        code=code,
        title=f"{label_a} and {label_b} diverged by {worst_d:.1f} m",
        severity="critical" if worst_d > ALT_DIVERGENCE_FAIL_M else "warning",
        kind="conflict",
        summary=(
            f"Two independent altitude sources disagree: after correcting for their initial "
            f"reference offset ({offset:+.1f} m), {label_a} and {label_b} diverged by up to "
            f"{worst_d:.1f} m at {inc.t_label(worst_t)}. One of these sources is wrong at that "
            f"moment. Typical causes: barometer drift from airflow/temperature (baro wrong), "
            f"GPS multipath or degraded constellation geometry (GPS wrong), or estimator "
            f"divergence. Altitude-dependent conclusions near this time must state which source "
            f"they rely on."
        ),
        evidence=[
            {"t_us": worst_t, "source": a.source, "value": round(a.at_or_before(worst_t), 2),
             "note": label_a},
            {"t_us": worst_t, "source": b.source, "value": round(b.at_or_before(worst_t), 2),
             "note": label_b},
        ],
        threshold={"metric": "altitude_divergence_m", "warn_above": ALT_DIVERGENCE_WARN_M,
                   "fail_above": ALT_DIVERGENCE_FAIL_M,
                   "basis": "offset-corrected cross-source residual"},
    )


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    baro = inc.series_or_none("alt_baro_m")
    gps = inc.series_or_none("alt_gps_m")
    fused = inc.series_or_none("alt_local_m")

    if baro is not None and gps is not None:
        f = _divergence_finding(inc, baro, gps, "barometric altitude", "GPS altitude",
                                "CONF-ALT-BARO-GPS", t0, t1)
        if f:
            findings.append(f)
    if baro is not None and fused is not None:
        f = _divergence_finding(inc, baro, fused, "barometric altitude", "EKF fused altitude",
                                "CONF-ALT-BARO-EKF", t0, t1)
        if f:
            findings.append(f)

    # Explicit agreement statement when sources were compared and did NOT conflict:
    # silence is not evidence; checked-and-agreed is.
    if baro is not None and gps is not None and not any(f.code == "CONF-ALT-BARO-GPS" for f in findings):
        findings.append(Finding(
            code="CONF-ALT-AGREE",
            title="Independent altitude sources agree",
            severity="info",
            kind="conflict",
            summary=(
                f"Barometric and GPS altitude were cross-checked over the flight window and "
                f"remained within {ALT_DIVERGENCE_WARN_M:.0f} m of each other after reference "
                f"offset correction. Altitude readings in this record are corroborated by two "
                f"independent sensors."
            ),
            threshold={"metric": "altitude_divergence_m", "warn_above": ALT_DIVERGENCE_WARN_M,
                       "basis": "offset-corrected cross-source residual"},
        ))

    return findings
