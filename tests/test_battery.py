"""Battery analyzer: low remaining and sag under load (not discharge)."""

from air.analyze import battery

from .synth import arm, incident, ramp, series


def _inc(*s):
    return incident(t1=600, series_list=list(s), events=[arm(0), arm(600, False)])


def test_slow_full_discharge_is_not_sag():
    # 25.2 V -> 19.8 V over 10 minutes: 21% below start, but no load sag
    v = ramp("batt_v", 0, 600, 25.2, 19.8, units="V")
    assert not [f for f in battery.analyze(_inc(v)) if f.code == "BAT-SAG"]


def test_fast_drop_under_load_is_sag_with_current_quoted():
    # slow discharge to ~21 V, then a 4 s load step pulls it to 17.5 V (17%)
    pts = [(t / 5, 24.0 - 0.002 * t) for t in range(0, 1500)]
    pts += [(300 + t / 5, 17.5) for t in range(0, 20)]
    pts += [(304 + t / 5, 20.9 - 0.002 * t) for t in range(0, 1480)]
    pts.sort()
    v = series("batt_v", pts, "V")
    cur = series("batt_current_a", [(t, 60.0 if 300 <= t < 304 else 15.0) for t in range(0, 600)])
    f = next(f for f in battery.analyze(_inc(v, cur)) if f.code == "BAT-SAG")
    assert f.severity == "warning"
    assert "60.0 A at the sag point" in f.summary
    assert f.threshold["window_s"] == battery.SAG_WINDOW_S


def test_collapse_is_critical():
    v = series("batt_v", [(t / 5, 22.0) for t in range(0, 2900)] + [(580 + t / 5, 12.0) for t in range(50)])
    f = next(f for f in battery.analyze(_inc(v)) if f.code == "BAT-SAG")
    assert f.severity == "critical"


def test_low_remaining():
    rem = ramp("batt_remaining", 0, 600, 0.9, 0.05)
    f = next(f for f in battery.analyze(_inc(rem)) if f.code == "BAT-LOW")
    assert f.severity == "critical"
    rem = ramp("batt_remaining", 0, 600, 0.9, 0.12)
    assert next(f for f in battery.analyze(_inc(rem)) if f.code == "BAT-LOW").severity == "warning"
    rem = ramp("batt_remaining", 0, 600, 0.9, 0.3)
    assert not battery.analyze(_inc(rem))


def test_worst_sag_uses_window_only():
    t = [0, 5_000_000, 20_000_000]
    assert battery.worst_sag(t, [20.0, 19.0, 15.0])[1] == 1  # 20 s drop is outside 10 s
