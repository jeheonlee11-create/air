"""Unit tests for the GPS, EKF, vibration and integrity analyzers (synthetic data)."""

import math

from air.analyze import ekf, gps, integrity, run_all_analyzers, vibration

from .synth import arm, incident, ramp, series


def _flight(*s, t1=100):
    return incident(t1=t1, series_list=list(s), events=[arm(0), arm(t1, False)])


def _codes(findings):
    return {f.code: f for f in findings}


def test_analyzers_ignore_samples_outside_flight():
    # 3 satellites before arming and after disarm must not count
    sats = series("gps_nsats", [(0, 3), (10, 12), (50, 12), (90, 12), (99, 3)])
    inc = incident(t1=100, series_list=[sats], events=[arm(5), arm(95, False)])
    assert "GPS-SATS" not in _codes(gps.analyze(inc))


def test_gps_sats_thresholds():
    f = _codes(gps.analyze(_flight(series("gps_nsats", [(0, 12), (50, 4), (99, 12)]))))
    assert f["GPS-SATS"].severity == "critical"
    f = _codes(gps.analyze(_flight(series("gps_nsats", [(0, 12), (50, 5), (99, 12)]))))
    assert f["GPS-SATS"].severity == "warning"
    assert not gps.analyze(_flight(series("gps_nsats", [(0, 12), (50, 6), (99, 12)])))


def test_gps_eph_jamming_spoofing_and_fixloss():
    s = [series("gps_eph", [(0, 1.0), (40, 12.0), (99, 1.0)]),
         series("gps_jamming", [(0, 1), (40, 2), (99, 1)]),
         series("gps_spoofing", [(0, 1), (40, 3), (99, 1)]),
         series("gps_fix", [(t, 3 if t % 10 else 2) for t in range(100)])]
    f = _codes(gps.analyze(_flight(*s)))
    assert f["GPS-EPH"].severity == "critical"
    assert f["GPS-JAM"].severity == "warning" and "indicator" in f["GPS-JAM"].summary
    assert f["GPS-SPOOF"].severity == "critical"
    assert f["GPS-FIXLOSS"].severity == "critical"     # 10% of samples below 3D


def test_ekf_ratio_amber_and_red():
    # 5% of samples above 1.0 -> critical
    vals = [(t / 5, 1.5 if t % 20 == 0 else 0.2) for t in range(500)]
    f = _codes(ekf.analyze(_flight(series("ekf_vel_test_ratio", vals))))
    assert f["EKF-VELOCITY"].severity == "critical"
    # a single brief spike above 1.0 -> warning only
    vals = [(t / 5, 1.2 if t == 250 else 0.2) for t in range(500)]
    f = _codes(ekf.analyze(_flight(series("ekf_mag_test_ratio", vals))))
    assert f["EKF-MAGNETOMETER"].severity == "warning"
    # healthy
    assert not ekf.analyze(_flight(ramp("ekf_pos_test_ratio", 0, 100, 0.1, 0.4)))


def test_ekf_filter_fault():
    f = _codes(ekf.analyze(_flight(series("ekf_filter_faults", [(0, 0), (30, 4), (99, 0)]))))
    assert f["EKF-FAULT"].evidence[0]["value"] == 4


def test_vibration_clipping_and_imu_disagreement():
    s = [series("vib_accel_ms2", [(0, 5), (50, 32), (99, 5)]),
         series("accel_clip_count", [(0, 10), (50, 10), (60, 50), (99, 50)]),
         series("imu_accel_inconsistency", [(0, 0.1), (50, 0.9), (99, 0.1)])]
    f = _codes(vibration.analyze(_flight(*s)))
    assert f["VIB-HIGH"].severity == "critical"
    assert f["VIB-CLIP"].evidence[0]["value"] == 40 and f["VIB-CLIP"].severity == "warning"
    assert f["IMU-DISAGREE"].kind == "conflict" and f["IMU-DISAGREE"].severity == "warning"


def test_vibration_quiet_flight_has_no_findings():
    s = [ramp("vib_accel_ms2", 0, 100, 3, 6), ramp("accel_clip_count", 0, 100, 7, 7)]
    assert not vibration.analyze(_flight(*s))


def test_integrity_nan_and_parser_notes():
    inc = _flight(series("batt_v", [(0, 24.0), (10, math.nan), (20, 23.9)]))
    inc.notes = ["FILE CORRUPTION: parser said so", "No GPS topic present in log"]
    f = _codes(integrity.analyze(inc))
    assert f["INT-NAN"].evidence[0]["note"] == "series batt_v"
    assert "INT-CORRUPT" in f and "INT-COVERAGE" in f


def test_registry_runs_every_analyzer_without_data():
    # an armed flight with no telemetry yields only integrity findings, no crash
    findings = run_all_analyzers(incident(t1=10, events=[arm(0), arm(10, False)]))
    assert {f.kind for f in findings} <= {"integrity"}
