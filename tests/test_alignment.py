"""Time alignment: staleness-bounded sampling and the altitude cross-checks."""

from air.analyze import conflict

from .synth import S, arm, incident, ramp, series


def test_sample_at_respects_max_age():
    s = series("x", [(0, 1.0), (1, 2.0), (2, 3.0)])
    assert s.at_or_before(int(1.5 * S)) == 2.0
    assert s.sample_at(int(1.5 * S)) == (1 * S, 2.0)
    assert s.at_or_before(-1) is None                        # before first sample
    assert s.at_or_before(10 * S) == 3.0                     # unbounded: holds last value
    assert s.at_or_before(10 * S, max_age_us=S) is None      # bounded: stale -> gap
    assert s.at_or_before(int(2.9 * S), max_age_us=S) == 3.0


def test_resample_pair_counts_gaps_during_dropout():
    a = ramp("a", 0, 100, 0, 0)
    # b reports for 0-40 s, drops out, resumes at 70 s
    b = series("b", [(t / 5, 0.0) for t in range(0, 200)] + [(t / 5, 0.0) for t in range(350, 500)])
    pairs, gaps = conflict.resample_pair(a, b, 0, 100 * S)
    # ~29 s of the dropout lies beyond the 1 s max age
    assert 55 <= gaps <= 60
    assert all(not (41 * S < t < 70 * S) for t, _, _ in pairs)


def _baro_gps_incident(gps_points, ekf_ref=None):
    baro = ramp("alt_baro_m", 0, 100, 300, 350, units="m")
    gps = series("alt_gps_m", gps_points, units="m MSL")
    inc = incident(t1=100, series_list=[baro, gps], events=[arm(1)])
    if ekf_ref:
        inc.aircraft["ekf_height_ref"] = ekf_ref
    return inc


def test_held_value_after_gps_dropout_is_not_a_conflict():
    # GPS tracks baro (offset +20 m) then stops at 30 s. The old code held the
    # 30 s value for the rest of the flight and reported a ~35 m divergence.
    pts = [(t / 5, 320 + 50 * (t / 5) / 100) for t in range(0, 150)]
    findings = conflict.analyze(_baro_gps_incident(pts))
    codes = {f.code for f in findings}
    assert "CONF-ALT-BARO-GPS" not in codes
    agree = next(f for f in findings if f.code == "CONF-ALT-AGREE")
    assert "treated as a data gap" in agree.summary


def test_real_divergence_is_reported_with_both_values():
    pts = [(t / 5, 320 + 50 * (t / 5) / 100 - (30 if t > 300 else 0)) for t in range(0, 500)]
    f = next(f for f in conflict.analyze(_baro_gps_incident(pts)) if f.code == "CONF-ALT-BARO-GPS")
    assert f.severity == "critical" and len(f.evidence) == 2
    assert "independent" in f.summary


def test_baro_vs_ekf_is_labeled_not_independent():
    baro = ramp("alt_baro_m", 0, 100, 300, 350)
    ekf = series("alt_local_m", [(t / 5, (t / 5) * 0.5 - (20 if t > 300 else 0)) for t in range(500)])
    inc = incident(t1=100, series_list=[baro, ekf], events=[arm(1)])
    inc.aircraft["ekf_height_ref"] = "barometer"
    f = next(f for f in conflict.analyze(inc) if f.code == "CONF-ALT-BARO-EKF")
    assert "not independent" in f.summary
    inc.aircraft.pop("ekf_height_ref")
    f = next(f for f in conflict.analyze(inc) if f.code == "CONF-ALT-BARO-EKF")
    assert "Independence is not established" in f.summary
