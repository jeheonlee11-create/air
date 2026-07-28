"""GPS quality, loss, jamming and spoofing indicators.

Thresholds derive from the retired ArduPilot LogAnalyzer TestGPSGlitch
(minSatsWARN=6, minSatsFAIL=5) and PX4's EKF gps_check / jamming_state and
spoofing_state semantics (0 unknown, 1 OK, 2 WARNING, 3 CRITICAL).

Findings state indicators with confidence language — never a verdict of
"jammed" or "spoofed"; that determination belongs to a human investigator.
"""

from __future__ import annotations

from ..schema import Finding, Incident
from .base import clip_series, extreme, flight_window

MIN_SATS_WARN = 6   # ArduPilot LogAnalyzer TestGPSGlitch minSatsWARN
MIN_SATS_FAIL = 5   # ArduPilot LogAnalyzer TestGPSGlitch minSatsFAIL
EPH_WARN_M = 5.0    # horizontal position uncertainty, heuristic on PX4 eph meters
EPH_FAIL_M = 10.0


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []
    win = flight_window(inc)
    if win is None:
        return findings
    t0, t1 = win

    sats = inc.series_or_none("gps_nsats")
    if sats is not None:
        worst = extreme(sats, t0, t1, "min")
        if worst is not None:
            t_min, v_min = worst
            if v_min < MIN_SATS_FAIL:
                sev = "critical"
            elif v_min < MIN_SATS_WARN:
                sev = "warning"
            else:
                sev = None
            if sev:
                _, vals = clip_series(sats, t0, t1)
                below = sum(1 for v in vals if v < MIN_SATS_WARN) / max(1, len(vals))
                findings.append(Finding(
                    code="GPS-SATS",
                    title=f"GPS satellite count dropped to {int(v_min)} in flight",
                    severity=sev,
                    summary=(
                        f"The number of GPS satellites used fell to {int(v_min)} at "
                        f"{inc.t_label(t_min)} ({below:.0%} of in-flight samples were below "
                        f"{MIN_SATS_WARN}). Low satellite counts degrade position accuracy and can "
                        f"trigger position-estimate failsafes. Sudden drops, especially with a "
                        f"simultaneous position jump, are also one indicator consistent with RF "
                        f"interference."
                    ),
                    evidence=[{"t_us": t_min, "source": sats.source, "value": int(v_min),
                               "note": "minimum satellites used during flight"}],
                    threshold={"metric": "satellites_used", "warn_below": MIN_SATS_WARN,
                               "fail_below": MIN_SATS_FAIL,
                               "basis": "ArduPilot LogAnalyzer TestGPSGlitch, Copter-4.5.0"},
                ))

    eph = inc.series_or_none("gps_eph")
    if eph is not None:
        worst = extreme(eph, t0, t1, "max")
        if worst is not None and worst[1] > EPH_WARN_M:
            t_max, v_max = worst
            findings.append(Finding(
                code="GPS-EPH",
                title=f"GPS horizontal uncertainty peaked at {v_max:.1f} m",
                severity="critical" if v_max > EPH_FAIL_M else "warning",
                summary=(
                    f"Reported horizontal position uncertainty (EPH) reached {v_max:.1f} m at "
                    f"{inc.t_label(t_max)}. Values above {EPH_WARN_M:.0f} m indicate degraded "
                    f"position quality; the flight controller's position estimate cannot be "
                    f"treated as reliable around this time."
                ),
                evidence=[{"t_us": t_max, "source": eph.source, "value": round(v_max, 2),
                           "note": "peak EPH during flight"}],
                threshold={"metric": "eph_m", "warn_above": EPH_WARN_M, "fail_above": EPH_FAIL_M,
                           "basis": "heuristic on PX4 eph; ArduPilot HDOP analog (3.0/10.0)"},
            ))

    for name, code, label in (("gps_jamming", "GPS-JAM", "jamming"),
                              ("gps_spoofing", "GPS-SPOOF", "spoofing")):
        s = inc.series_or_none(name)
        if s is None:
            continue
        worst = extreme(s, t0, t1, "max")
        if worst is not None and worst[1] >= 2:
            t_max, v_max = worst
            state = {2: "WARNING", 3: "CRITICAL"}.get(int(v_max), str(int(v_max)))
            findings.append(Finding(
                code=code,
                title=f"GPS receiver reported {label} state {state}",
                severity="critical" if v_max >= 3 else "warning",
                summary=(
                    f"The GNSS receiver's own {label} detector reported state {state} at "
                    f"{inc.t_label(t_max)}. This is an indicator from the receiver, not a "
                    f"conclusion: it is consistent with RF interference or signal manipulation, "
                    f"but can also be triggered by benign local interference. Corroborate with "
                    f"satellite-count drops, position jumps, and any co-located detection-sensor "
                    f"records before drawing conclusions."
                ),
                evidence=[{"t_us": t_max, "source": s.source, "value": int(v_max),
                           "note": f"peak {label}_state (0=unknown,1=OK,2=WARNING,3=CRITICAL)"}],
                threshold={"metric": f"{label}_state", "warn_at": 2, "fail_at": 3,
                           "basis": "PX4/ublox receiver state semantics"},
            ))

    fix = inc.series_or_none("gps_fix")
    if fix is not None:
        t, v = clip_series(fix, t0, t1)
        lost = [(ts, val) for ts, val in zip(t, v) if val < 3]
        if lost:
            frac = len(lost) / max(1, len(v))
            findings.append(Finding(
                code="GPS-FIXLOSS",
                title="GPS fix degraded below 3D during flight",
                severity="critical" if frac > 0.05 else "warning",
                summary=(
                    f"The GPS fix dropped below 3D for {frac:.1%} of in-flight samples, first at "
                    f"{inc.t_label(lost[0][0])}. Without a 3D fix the vehicle cannot maintain "
                    f"position-controlled flight and may drift or trigger failsafes."
                ),
                evidence=[{"t_us": lost[0][0], "source": fix.source, "value": int(lost[0][1]),
                           "note": "first sub-3D fix sample in flight"}],
                threshold={"metric": "fix_type", "fail_below": 3, "basis": "3D fix required for position control"},
            ))

    return findings
