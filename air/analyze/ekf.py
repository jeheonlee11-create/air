"""EKF (state estimator) health.

PX4's own ecl_ekf analysis convention: an innovation test ratio > 1.0 means the
measurement was rejected by the estimator (red); > 0.5 is degraded (amber).
Sustained high ratios mean the estimator's world-model and the sensors disagree
— the core signal behind flyaways, toilet-bowling, and position glitches.
"""

from __future__ import annotations

from ..schema import Finding, Incident
from .base import clip_series, flight_window

RATIO_AMBER = 0.5  # PX4 Tools/ecl_ekf convention
RATIO_RED = 1.0

LABELS = {
    "ekf_vel_test_ratio": "velocity",
    "ekf_pos_test_ratio": "horizontal position",
    "ekf_hgt_test_ratio": "height",
    "ekf_mag_test_ratio": "magnetometer/heading",
    "ekf_hagl_test_ratio": "height-above-ground",
}


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    for key, label in LABELS.items():
        s = inc.series_or_none(key)
        if s is None:
            continue
        t, v = clip_series(s, t0, t1)
        if not v:
            continue
        peak_i = max(range(len(v)), key=lambda i: v[i])
        peak_t, peak_v = t[peak_i], v[peak_i]
        frac_red = sum(1 for x in v if x > RATIO_RED) / len(v)
        frac_amber = sum(1 for x in v if x > RATIO_AMBER) / len(v)

        if peak_v <= RATIO_AMBER:
            continue
        sev = "critical" if (peak_v > RATIO_RED and frac_red > 0.02) else \
              "warning" if peak_v > RATIO_RED or frac_amber > 0.1 else None
        if sev is None:
            continue
        findings.append(Finding(
            code=f"EKF-{label.split('/')[0].split()[0].upper()}",
            title=f"Estimator rejected {label} measurements (peak ratio {peak_v:.2f})",
            severity=sev,
            summary=(
                f"The flight controller's state estimator (EKF) reported a {label} innovation "
                f"test ratio peaking at {peak_v:.2f} at {inc.t_label(peak_t)} "
                f"({frac_red:.1%} of in-flight samples above {RATIO_RED}, {frac_amber:.1%} above "
                f"{RATIO_AMBER}). A ratio above 1.0 means the estimator was actively rejecting "
                f"that sensor's measurements because they disagreed with its state estimate — "
                f"the vehicle's believed {label} and the measured {label} were in conflict."
            ),
            evidence=[{"t_us": peak_t, "source": s.source, "value": round(peak_v, 3),
                       "note": f"peak {label} innovation test ratio"}],
            threshold={"metric": key, "amber_above": RATIO_AMBER, "red_above": RATIO_RED,
                       "basis": "PX4 Tools/ecl_ekf check convention"},
        ))

    faults = inc.series_or_none("ekf_filter_faults")
    if faults is not None:
        t, v = clip_series(faults, t0, t1)
        hit = next(((ts, val) for ts, val in zip(t, v) if val != 0), None)
        if hit:
            findings.append(Finding(
                code="EKF-FAULT",
                title="EKF filter fault flags set during flight",
                severity="critical",
                summary=(
                    f"estimator_status.filter_fault_flags became non-zero "
                    f"(value {int(hit[1])}) at {inc.t_label(hit[0])}. PX4 documentation states "
                    f"this field should always be zero in healthy operation; a non-zero value "
                    f"indicates numerical or fusion faults inside the estimator."
                ),
                evidence=[{"t_us": hit[0], "source": faults.source, "value": int(hit[1]),
                           "note": "first non-zero filter_fault_flags"}],
                threshold={"metric": "filter_fault_flags", "fail_if": "non-zero",
                           "basis": "PX4 estimator_status documentation"},
            ))

    return findings
