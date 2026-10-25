"""Log integrity checks.

Ports of the retired ArduPilot LogAnalyzer integrity tests (last shipped in the
Copter-4.5.0 tag before the tool was deleted in Aug 2024), adapted to PX4:

- TestBrownout: log ends while armed and above altitude threshold (3.0 m)
- TestNaN:      any NaN in a normalized numeric series
"""

from __future__ import annotations

import math

from ..schema import Finding, Incident
from .base import arm_cycles

FINAL_ALT_MAX_M = 3.0  # ArduPilot LogAnalyzer TestBrownout `finalAltMax`


def final_height(inc: Incident, armed_t: int) -> tuple[int, str, float, str] | None:
    """(t_last, source, height_m, reference) for the end of the log.

    Prefers height above home. Otherwise uses the change in EKF-origin or
    barometric altitude since the last arm, which removes their (unrelated)
    reference offsets. Raw barometric altitude is roughly MSL and is never
    compared with the 3 m threshold directly.
    """
    s = inc.series_or_none("alt_above_home_m")
    if s is not None:
        return s.t_us[-1], s.source, s.values[-1], "above home"
    for name, label in (("alt_local_m", "above the arming point (EKF height change)"),
                        ("alt_baro_m", "above the arming point (barometric height change)")):
        s = inc.series_or_none(name)
        if s is None:
            continue
        at_arm = s.at_or_before(armed_t)
        if at_arm is None:  # series starts after the arm event
            at_arm = s.values[0]
        return s.t_us[-1], s.source, s.values[-1] - at_arm, label
    return None


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []

    # --- Ends-while-armed / brownout / power loss ---
    cycles = arm_cycles(inc)
    if cycles:
        # Only the LAST arm cycle decides: an earlier disarm (e.g. a landing
        # followed by a second flight) says nothing about how the log ends.
        still_armed_at_end = cycles[-1][1] is None
        if still_armed_at_end:
            final = final_height(inc, cycles[-1][0])
            if final is not None and final[2] > FINAL_ALT_MAX_M:
                t_last, src, final_alt, ref = final
                findings.append(Finding(
                    code="INT-TRUNC",
                    title="Log ends in flight (possible power loss / brownout / impact)",
                    severity="critical",
                    kind="integrity",
                    summary=(
                        f"The log terminates while the vehicle is still armed at approximately "
                        f"{final_alt:.1f} m {ref}. Flight logs normally continue until disarm; "
                        f"an in-air truncation is consistent with sudden power loss, controller "
                        f"brownout, or destruction of the vehicle at impact. The final logged "
                        f"data point is at {inc.t_label(t_last)}."
                    ),
                    evidence=[{"t_us": t_last, "source": src, "value": round(final_alt, 2),
                               "note": f"final logged height ({ref}) while armed"}],
                    threshold={"metric": "final_height_m", "fail_above": FINAL_ALT_MAX_M,
                               "reference": ref,
                               "basis": "ArduPilot LogAnalyzer TestBrownout (finalAltMax=3.0 m), Copter-4.5.0"},
                ))
            else:
                findings.append(Finding(
                    code="INT-NODISARM",
                    title="Log ends without a disarm event",
                    severity="warning",
                    kind="integrity",
                    summary="The vehicle armed but the log contains no disarm event. The log may be "
                            "truncated (power interruption, SD failure) or logging stopped early.",
                    threshold={"basis": "ArduPilot LogAnalyzer TestBrownout, Copter-4.5.0"},
                ))
    else:
        findings.append(Finding(
            code="INT-NOARM",
            title="Vehicle never armed in this log",
            severity="info",
            kind="integrity",
            summary="No arming event found; this log does not contain a flight.",
        ))

    # --- NaN scan (ArduPilot TestNaN port) ---
    nan_hits = []
    for name, s in inc.series.items():
        for i, v in enumerate(s.values):
            if isinstance(v, float) and math.isnan(v):
                nan_hits.append({"t_us": s.t_us[i], "source": s.source, "value": "NaN",
                                 "note": f"series {name}"})
                break  # one per series is enough evidence
    if nan_hits:
        findings.append(Finding(
            code="INT-NAN",
            title=f"NaN values present in {len(nan_hits)} telemetry channel(s)",
            severity="warning",
            kind="integrity",
            summary="One or more telemetry channels contain NaN (not-a-number) values, which "
                    "indicates a numerical fault in the firmware or a sensor delivering invalid "
                    "data. Channels affected are listed in evidence.",
            evidence=nan_hits[:10],
            threshold={"basis": "ArduPilot LogAnalyzer TestNaN, Copter-4.5.0"},
        ))

    # --- Ingest caveats surface as findings so they're never silent ---
    for note in inc.notes:
        if note.startswith("FILE CORRUPTION"):
            findings.append(Finding(
                code="INT-CORRUPT",
                title="Log file corruption reported by parser",
                severity="warning",
                kind="integrity",
                summary=note,
                threshold={"basis": "pyulog ULog.file_corruption flag"},
            ))
        else:
            findings.append(Finding(
                code="INT-COVERAGE",
                title="Evidence coverage gap",
                severity="info",
                kind="integrity",
                summary=note,
            ))

    return findings
