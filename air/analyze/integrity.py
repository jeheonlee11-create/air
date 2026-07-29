"""Log integrity checks.

Ports of the retired ArduPilot LogAnalyzer integrity tests (last shipped in the
Copter-4.5.0 tag before the tool was deleted in Aug 2024), adapted to PX4:

- TestBrownout: log ends while armed and above altitude threshold (3.0 m)
- TestNaN:      any NaN in a normalized numeric series
"""

from __future__ import annotations

import math

from ..schema import Finding, Incident
from .base import flight_window

FINAL_ALT_MAX_M = 3.0  # ArduPilot LogAnalyzer TestBrownout `finalAltMax`


def analyze(inc: Incident) -> list[Finding]:
    findings: list[Finding] = []

    # --- Ends-while-armed / brownout / power loss ---
    win = flight_window(inc)
    if win is not None:
        armed_t, _end_t = win
        still_armed_at_end = True
        for ev in inc.sorted_events():
            if ev.kind == "arming" and "DISARMED" in ev.message and ev.t_us >= armed_t:
                still_armed_at_end = False
        if still_armed_at_end:
            alt = inc.series_or_none("alt_local_m") or inc.series_or_none("alt_baro_m")
            final_alt = alt.values[-1] if alt else None
            if final_alt is not None and final_alt > FINAL_ALT_MAX_M:
                findings.append(Finding(
                    code="INT-TRUNC",
                    title="Log ends in flight (possible power loss / brownout / impact)",
                    severity="critical",
                    kind="integrity",
                    summary=(
                        f"The log terminates while the vehicle is still armed at approximately "
                        f"{final_alt:.1f} m altitude. Flight logs normally continue until disarm; "
                        f"an in-air truncation indicates sudden power loss, controller brownout, "
                        f"or destruction of the vehicle at the moment of impact. The final logged "
                        f"data point is at {inc.t_label(alt.t_us[-1])}."
                    ),
                    evidence=[{"t_us": alt.t_us[-1], "source": alt.source, "value": round(final_alt, 2),
                               "note": "final logged altitude while armed"}],
                    threshold={"metric": "final_altitude_m", "fail_above": FINAL_ALT_MAX_M,
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
