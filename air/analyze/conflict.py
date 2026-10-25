"""Cross-source conflict analysis.

Sensors measuring the same physical quantity should agree. When they diverge,
at least one of them is wrong, and any conclusion built on the wrong one is
open to challenge. This module measures agreement explicitly and reports where
the evidence conflicts, instead of silently trusting one source.

Currently implemented:
- Barometric altitude vs GPS altitude (independent sensors; offset-corrected)
- Barometric altitude vs EKF fused altitude. NOT independent when the EKF uses
  the barometer as its height reference (the PX4 default), and labeled so.
(IMU-vs-IMU disagreement is covered in vibration.py via sensors_status_imu.)

Time alignment: both series are sampled on a common grid using the last sample
at or before each grid time, but only if that sample is at most MAX_AGE_US old.
A sensor that stopped reporting (e.g. GPS dropout) leaves a gap instead of
having its last value held and compared as if it were current.
"""

from __future__ import annotations

from ..schema import Finding, Incident, Series
from .base import flight_window

ALT_DIVERGENCE_WARN_M = 10.0
ALT_DIVERGENCE_FAIL_M = 25.0
GRID_STEP_US = 500_000
# Max sample age for a comparison. PX4 logs baro and GPS at several Hz, so a
# value older than 1 s means the source was not reporting at that moment.
MAX_AGE_US = 1_000_000


def resample_pair(a: Series, b: Series, t0: int, t1: int, step_us: int = GRID_STEP_US,
                  max_age_us: int = MAX_AGE_US):
    """Sample both series on a common grid inside [t0, t1].

    Returns (pairs, gaps): pairs = [(t, va, vb)] where both had a fresh sample;
    gaps = number of grid points skipped because a source was absent or stale.
    """
    pairs, gaps = [], 0
    for t in range(t0, t1, step_us):
        va, vb = a.at_or_before(t, max_age_us), b.at_or_before(t, max_age_us)
        if va is not None and vb is not None:
            pairs.append((t, va, vb))
        else:
            gaps += 1
    return pairs, gaps


def _gap_note(gaps: int, total: int) -> str:
    if not gaps:
        return ""
    return (f" {gaps} of {total} comparison points were skipped because one source had no "
            f"sample within {MAX_AGE_US / 1e6:.1f} s (treated as a data gap, not compared).")


def _divergence_finding(inc: Incident, a: Series, b: Series, label_a: str, label_b: str,
                        code: str, t0: int, t1: int, relation: str) -> tuple[Finding | None, int, int]:
    """Returns (finding or None, compared points, gap points)."""
    pairs, gaps = resample_pair(a, b, t0, t1)
    if len(pairs) < 10:
        return None, len(pairs), gaps
    # offset-correct using the first samples (different references: MSL vs relative)
    n0 = min(5, len(pairs))
    offset = sum(va - vb for _, va, vb in pairs[:n0]) / n0
    worst = max(pairs, key=lambda p: abs((p[1] - p[2]) - offset))
    worst_t, worst_a, worst_b = worst
    worst_d = abs((worst_a - worst_b) - offset)
    if worst_d < ALT_DIVERGENCE_WARN_M:
        return None, len(pairs), gaps
    return Finding(
        code=code,
        title=f"{label_a} and {label_b} diverged by {worst_d:.1f} m",
        severity="critical" if worst_d > ALT_DIVERGENCE_FAIL_M else "warning",
        kind="conflict",
        summary=(
            f"{relation} After correcting for their initial reference offset "
            f"({offset:+.1f} m), {label_a} and {label_b} diverged by up to {worst_d:.1f} m at "
            f"{inc.t_label(worst_t)}. At least one of them is wrong at that moment. Typical "
            f"causes: barometer error from airflow or temperature, GPS multipath or poor "
            f"satellite geometry, or estimator divergence. Altitude-dependent conclusions near "
            f"this time must state which source they rely on."
            + _gap_note(gaps, len(pairs) + gaps)
        ),
        evidence=[
            {"t_us": worst_t, "source": a.source, "value": round(worst_a, 2), "note": label_a},
            {"t_us": worst_t, "source": b.source, "value": round(worst_b, 2), "note": label_b},
        ],
        threshold={"metric": "altitude_divergence_m", "warn_above": ALT_DIVERGENCE_WARN_M,
                   "fail_above": ALT_DIVERGENCE_FAIL_M, "max_sample_age_s": MAX_AGE_US / 1e6,
                   "basis": "offset-corrected cross-source residual"},
    ), len(pairs), gaps


def _ekf_relation(inc: Incident) -> str:
    ref = inc.aircraft.get("ekf_height_ref")
    if ref == "barometer":
        return ("These are not independent: the EKF uses the barometer as its height "
                "reference (logged parameter), so it is partly built from the barometer "
                "reading. Divergence means the estimator was correcting with other height "
                "sources (GPS, range finder) or rejecting the barometer.")
    if ref:
        return (f"The EKF height reference is the {ref} (logged parameter), but the EKF may "
                f"still fuse the barometer, so the two are not fully independent.")
    return ("Independence is not established: the EKF height reference is not in the log, "
            "and PX4's default is to fuse the barometer.")


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    baro = inc.series_or_none("alt_baro_m")
    gps = inc.series_or_none("alt_gps_m")
    fused = inc.series_or_none("alt_local_m")

    gps_checked, gps_gaps, gps_total = False, 0, 0
    if baro is not None and gps is not None:
        f, n, gps_gaps = _divergence_finding(
            inc, baro, gps, "barometric altitude", "GPS altitude", "CONF-ALT-BARO-GPS", t0, t1,
            "Two independent altitude sensors disagree.")
        gps_checked, gps_total = n >= 10, n + gps_gaps
        if f:
            findings.append(f)
    if baro is not None and fused is not None:
        f, _, _ = _divergence_finding(
            inc, baro, fused, "barometric altitude", "EKF fused altitude", "CONF-ALT-BARO-EKF",
            t0, t1, "The barometer and the flight controller's fused height estimate disagree. "
            + _ekf_relation(inc))
        if f:
            findings.append(f)

    # Explicit agreement statement when sources were compared and did NOT conflict:
    # silence is not evidence; checked-and-agreed is.
    if gps_checked and not any(f.code == "CONF-ALT-BARO-GPS" for f in findings):
        findings.append(Finding(
            code="CONF-ALT-AGREE",
            title="Barometric and GPS altitude agree",
            severity="info",
            kind="conflict",
            summary=(
                f"Barometric and GPS altitude were cross-checked over the flight window and "
                f"remained within {ALT_DIVERGENCE_WARN_M:.0f} m of each other after reference "
                f"offset correction, so altitude in this record is corroborated by two "
                f"independent sensors wherever both were reporting."
                + _gap_note(gps_gaps, gps_total)
            ),
            threshold={"metric": "altitude_divergence_m", "warn_above": ALT_DIVERGENCE_WARN_M,
                       "max_sample_age_s": MAX_AGE_US / 1e6,
                       "basis": "offset-corrected cross-source residual"},
        ))

    return findings
