"""Arm/disarm parsing, arm cycles, and the ends-in-flight (INT-TRUNC) check."""

from air.analyze import integrity
from air.analyze.base import arm_cycles, arming_state, flight_window
from air.schema import TimelineEvent

from .synth import S, arm, incident, ramp, series


def test_disarmed_message_is_not_read_as_armed():
    # text fallback only (no data["armed"]): the old substring test matched ARMED in DISARMED
    assert arming_state(arm(1, armed=False, with_data=False)) is False
    assert arming_state(arm(1, armed=True, with_data=False)) is True
    ev = TimelineEvent(0, "x", "arming", "info", "Vehicle ARMED (armed at log start)")
    assert arming_state(ev) is True
    assert arming_state(TimelineEvent(0, "x", "message", "info", "ARMED")) is None


def test_leading_disarm_does_not_open_a_flight():
    inc = incident(events=[arm(5, False, with_data=False)])
    assert arm_cycles(inc) == []
    assert flight_window(inc) is None


def test_multiple_cycles_and_window():
    inc = incident(t1=100, events=[arm(10), arm(20, False), arm(40), arm(60, False)])
    assert arm_cycles(inc) == [(10 * S, 20 * S), (40 * S, 60 * S)]
    assert flight_window(inc) == (10 * S, 60 * S)


def test_log_ending_armed_in_second_cycle_is_truncation():
    # first flight lands and disarms; second flight's log ends 50 m up
    alt = ramp("alt_above_home_m", 0, 100, 0, 50, units="m")
    inc = incident(t1=100, series_list=[alt],
                   events=[arm(10), arm(20, False), arm(40)])
    codes = {f.code for f in integrity.analyze(inc)}
    assert "INT-TRUNC" in codes


def test_clean_disarm_at_end_is_not_truncation():
    alt = ramp("alt_above_home_m", 0, 100, 0, 50, units="m")
    inc = incident(t1=100, series_list=[alt], events=[arm(10), arm(90, False)])
    codes = {f.code for f in integrity.analyze(inc)}
    assert not codes & {"INT-TRUNC", "INT-NODISARM"}


def test_never_armed_reports_noarm():
    codes = {f.code for f in integrity.analyze(incident())}
    assert codes == {"INT-NOARM"}


def test_raw_barometric_msl_is_not_read_as_height():
    # baro reads ~300 m (pressure altitude) on the ground at both ends; the
    # old code compared 300 m with the 3 m threshold and called it INT-TRUNC
    baro = ramp("alt_baro_m", 0, 100, 300, 300.5)
    inc = incident(t1=100, series_list=[baro], events=[arm(10)])
    codes = {f.code for f in integrity.analyze(inc)}
    assert "INT-TRUNC" not in codes and "INT-NODISARM" in codes


def test_truncation_reference_is_stated():
    baro = series("alt_baro_m", [(0, 300), (10, 300), (50, 340), (100, 330)])
    inc = incident(t1=100, series_list=[baro], events=[arm(10)])
    f = next(f for f in integrity.analyze(inc) if f.code == "INT-TRUNC")
    assert f.evidence[0]["value"] == 30.0
    assert "arming point" in f.threshold["reference"]
