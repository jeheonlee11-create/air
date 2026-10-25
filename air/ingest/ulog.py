"""PX4 ULog ingestion -> normalized Incident.

PX4 topic/field names drift across firmware versions (e.g. GPS lives in
`vehicle_gps_position` on older firmware and `sensor_gps` on newer; positions
switch between 1e7-scaled ints and float degrees). All aliasing is centralized
here so analyzers only ever see normalized series names.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from pyulog import ULog

from ..schema import Incident, Series, SourceFile, TimelineEvent, UtcAnchor

# PX4 commander nav states (stable across recent firmware; unknowns fall back to raw id)
NAV_STATE = {
    0: "MANUAL", 1: "ALTITUDE", 2: "POSITION", 3: "AUTO_MISSION", 4: "AUTO_LOITER",
    5: "AUTO_RTL", 6: "POSITION_SLOW", 10: "ACRO", 12: "DESCEND", 13: "TERMINATION",
    14: "OFFBOARD", 15: "STABILIZED", 17: "AUTO_TAKEOFF", 18: "AUTO_LAND",
    19: "AUTO_FOLLOW_TARGET", 20: "AUTO_PRECLAND", 21: "ORBIT", 22: "VTOL_TAKEOFF",
}

GPS_FIX = {0: "none", 1: "none", 2: "2D", 3: "3D", 4: "DGPS", 5: "RTK float", 6: "RTK fixed"}
GPS_QUALITY_STATE = {0: "unknown", 1: "OK", 2: "WARNING", 3: "CRITICAL"}  # jamming/spoofing_state


def _topic(u: ULog, name: str, instance: int = 0):
    try:
        return u.get_dataset(name, instance)
    except (KeyError, IndexError, ValueError):
        return None


def _first_field(data, *names):
    """Return (field_name, values) for the first field that exists."""
    for n in names:
        if n in data.data:
            return n, data.data[n]
    return None, None


def _series(inc: Incident, name: str, topic, field_names, units="", scale=1.0, topic_label=""):
    """Extract a field (first alias that exists) into a normalized Series."""
    if topic is None:
        return None
    fname, vals = _first_field(topic, *field_names)
    if fname is None:
        return None
    t = topic.data["timestamp"]
    s = Series(
        name=name,
        source=f"px4_ulog:{topic_label or topic.name}.{fname}",
        t_us=[int(x) for x in t],
        values=[float(v) * scale for v in vals],
        units=units,
    )
    inc.series[name] = s
    return s


def _array_fields(data, base: str) -> list[str]:
    """PX4 logs fixed-size array fields as `base[0]`, `base[1]`, ... in index order."""
    out = []
    while f"{base}[{len(out)}]" in data.data:
        out.append(f"{base}[{len(out)}]")
    return out


def _combined_series(inc: Incident, name: str, topic, base: str, how: str, units="",
                     topic_label=""):
    """Collapse an array field (or a scalar of the same name) into one Series.

    how="sum": per-axis counters -> total; how="max": per-instance metrics -> worst.
    The provenance label names the elements combined and how.
    """
    if topic is None:
        return None
    fields = _array_fields(topic, base)
    if fields:
        cols = [[float(v) for v in topic.data[f]] for f in fields]
        if how == "sum":
            vals = [sum(row) for row in zip(*cols, strict=True)]
            what = "sum across axes"
        else:
            vals = [max((v for v in row if not math.isnan(v)), default=math.nan)
                    for row in zip(*cols, strict=True)]
            what = "max across instances"
        label = f"{base}[0..{len(fields) - 1}] ({what})"
    elif base in topic.data:
        vals, label = [float(v) for v in topic.data[base]], base
    else:
        return None
    s = Series(name=name, source=f"px4_ulog:{topic_label or topic.name}.{label}",
               t_us=[int(x) for x in topic.data["timestamp"]], values=vals, units=units)
    inc.series[name] = s
    return s


def ingest_ulog(path: str) -> Incident:
    u = ULog(path)
    src = SourceFile.from_path(path, kind="px4_ulog", meta={"topics": len(u.data_list)})
    if not u.data_list:
        raise ValueError("ULog header parsed but the file contains no data topics")

    inc = Incident(
        incident_id=str(uuid.uuid4()),
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sources=[src],
        t0_us=int(u.start_timestamp),
        t1_us=int(u.last_timestamp),
    )

    info = u.msg_info_dict
    inc.aircraft = {
        "firmware": "PX4",
        "fw_commit": info.get("ver_sw", ""),
        "hardware": info.get("ver_hw", ""),
        "os": info.get("sys_os_name", ""),
        "sys_name": info.get("sys_name", ""),
    }
    airframe = u.initial_parameters.get("SYS_AUTOSTART")
    if airframe is not None:
        inc.aircraft["sys_autostart"] = int(airframe)
    # EKF primary height source; decides whether baro-vs-EKF is an independent check
    for pname in ("EKF2_HGT_REF", "EKF2_HGT_MODE"):
        if pname in u.initial_parameters:
            code = int(u.initial_parameters[pname])
            inc.aircraft["ekf_height_ref"] = {0: "barometer", 1: "GPS", 2: "range finder",
                                              3: "vision"}.get(code, f"{pname}={code}")
            inc.aircraft["ekf_height_ref_param"] = f"{pname}={code}"
            break

    # ---- GPS (two topic generations, two coordinate encodings) ----
    gps = _topic(u, "vehicle_gps_position") or _topic(u, "sensor_gps")
    gps_label = "vehicle_gps_position" if _topic(u, "vehicle_gps_position") else "sensor_gps"
    if gps is not None:
        _series(inc, "gps_nsats", gps, ["satellites_used"], "count", topic_label=gps_label)
        _series(inc, "gps_eph", gps, ["eph"], "m", topic_label=gps_label)
        _series(inc, "gps_epv", gps, ["epv"], "m", topic_label=gps_label)
        _series(inc, "gps_fix", gps, ["fix_type"], "", topic_label=gps_label)
        _series(inc, "gps_jamming", gps, ["jamming_state"], "", topic_label=gps_label)
        _series(inc, "gps_spoofing", gps, ["spoofing_state"], "", topic_label=gps_label)
        _series(inc, "gps_noise", gps, ["noise_per_ms"], "", topic_label=gps_label)

        # altitude: int mm ("alt") vs float m ("altitude_msl_m")
        if "altitude_msl_m" in gps.data:
            _series(inc, "alt_gps_m", gps, ["altitude_msl_m"], "m MSL", topic_label=gps_label)
        else:
            _series(inc, "alt_gps_m", gps, ["alt"], "m MSL", scale=1e-3, topic_label=gps_label)

        # position: float deg ("latitude_deg") vs 1e7 int ("lat")
        lat_f, lat_v = _first_field(gps, "latitude_deg", "lat")
        lon_f, lon_v = _first_field(gps, "longitude_deg", "lon")
        if lat_f and lon_f and len(lat_v):
            lat_scale = 1.0 if lat_f == "latitude_deg" else 1e-7
            fix = inc.series_or_none("gps_fix")
            idx = 0
            if fix:  # first sample with a 3D fix
                for i, _v in enumerate(gps.data[lat_f]):
                    fx = fix.at_or_before(int(gps.data["timestamp"][i]))
                    if fx is not None and fx >= 3:
                        idx = i
                        break
            inc.home = {
                "lat": float(lat_v[idx]) * lat_scale,
                "lon": float(lon_v[idx]) * lat_scale,
                "source": f"px4_ulog:{gps_label}.{lat_f} (first 3D-fix sample)",
            }

        # UTC anchor from GPS time
        tf, tv = _first_field(gps, "time_utc_usec")
        if tf and len(tv):
            for i, utc in enumerate(tv):
                if utc > 1e15:  # plausible epoch µs (>2001)
                    inc.utc_anchor = UtcAnchor(
                        offset_us=int(utc) - int(gps.data["timestamp"][i]),
                        source=f"px4_ulog:{gps_label}.time_utc_usec",
                    )
                    break
    else:
        inc.notes.append("No GPS topic present in log (vehicle_gps_position/sensor_gps); "
                         "position, home distance and UTC anchoring unavailable.")

    # ---- Altitude / position ----
    _series(inc, "alt_baro_m", _topic(u, "vehicle_air_data"), ["baro_alt_meter"], "m", topic_label="vehicle_air_data")
    lp = _topic(u, "vehicle_local_position")
    if lp is not None:
        _series(inc, "alt_local_m", lp, ["z"], "m AGL(rel)", scale=-1.0, topic_label="vehicle_local_position")
        if "x" in lp.data and "y" in lp.data:
            t = lp.data["timestamp"]
            dist = [math.hypot(float(x), float(y)) for x, y in zip(lp.data["x"], lp.data["y"], strict=False)]
            inc.series["dist_home_m"] = Series(
                "dist_home_m", "px4_ulog:vehicle_local_position.x/y (horizontal, NED origin)",
                [int(x) for x in t], dist, "m")
        if "vx" in lp.data and "vy" in lp.data:
            t = lp.data["timestamp"]
            spd = [math.hypot(float(x), float(y)) for x, y in zip(lp.data["vx"], lp.data["vy"], strict=False)]
            inc.series["groundspeed_ms"] = Series(
                "groundspeed_ms", "px4_ulog:vehicle_local_position.vx/vy", [int(x) for x in t], spd, "m/s")

    # ---- Battery ----
    bat = _topic(u, "battery_status")
    _series(inc, "batt_v", bat, ["voltage_filtered_v", "voltage_v"], "V", topic_label="battery_status")
    _series(inc, "batt_remaining", bat, ["remaining"], "fraction", topic_label="battery_status")
    _series(inc, "batt_current_a", bat, ["current_filtered_a", "current_a"], "A", topic_label="battery_status")

    # ---- EKF health (estimator_status has *_test_ratio on all generations we target) ----
    est = _topic(u, "estimator_status")
    for ratio in ("vel_test_ratio", "pos_test_ratio", "hgt_test_ratio", "hagl_test_ratio"):
        _series(inc, f"ekf_{ratio}", est, [ratio], "ratio", topic_label="estimator_status")
    # heading innovation: `mag_test_ratio` on most firmware, `hdg_test_ratio` on some
    _series(inc, "ekf_mag_test_ratio", est, ["mag_test_ratio", "hdg_test_ratio"], "ratio",
            topic_label="estimator_status")
    _series(inc, "ekf_gps_check_fail", est, ["gps_check_fail_flags"], "bitmask", topic_label="estimator_status")
    _series(inc, "ekf_filter_faults", est, ["filter_fault_flags"], "bitmask", topic_label="estimator_status")

    # ---- Vibration / IMU consistency ----
    imu_status = _topic(u, "vehicle_imu_status")
    _series(inc, "vib_accel_ms2", imu_status, ["accel_vibration_metric"], "m/s^2", topic_label="vehicle_imu_status")
    # accel_clipping[0..2]: accumulated clip counts per axis -> total
    _combined_series(inc, "accel_clip_count", imu_status, "accel_clipping", "sum", "count",
                     topic_label="vehicle_imu_status")
    # *_inconsistency[0..3]: per IMU instance vs. the mean -> worst instance
    ssi = _topic(u, "sensors_status_imu")
    _combined_series(inc, "imu_accel_inconsistency", ssi, "accel_inconsistency_m_s_s", "max",
                     "m/s^2", topic_label="sensors_status_imu")
    _combined_series(inc, "imu_gyro_inconsistency", ssi, "gyro_inconsistency_rad_s", "max",
                     "rad/s", topic_label="sensors_status_imu")

    # ---- Attitude ----
    att = _topic(u, "vehicle_attitude")
    if att is not None and "q[0]" in att.data:
        t = att.data["timestamp"]
        q0, q1, q2, q3 = (att.data[f"q[{i}]"] for i in range(4))
        roll, pitch = [], []
        for a, b, c, d in zip(q0, q1, q2, q3, strict=False):
            roll.append(math.degrees(math.atan2(2 * (a * b + c * d), 1 - 2 * (b * b + c * c))))
            sp = max(-1.0, min(1.0, 2 * (a * c - d * b)))
            pitch.append(math.degrees(math.asin(sp)))
        ts = [int(x) for x in t]
        inc.series["roll_deg"] = Series("roll_deg", "px4_ulog:vehicle_attitude.q", ts, roll, "deg")
        inc.series["pitch_deg"] = Series("pitch_deg", "px4_ulog:vehicle_attitude.q", ts, pitch, "deg")

    # ---- File integrity flag from the parser itself ----
    if getattr(u, "file_corruption", False):
        inc.notes.append(
            "FILE CORRUPTION: the ULog parser reported corruption in this file; "
            "some messages were unreadable and the timeline may be incomplete.")

    # ---- Discrete events ----
    _extract_events(u, inc)

    return inc


def _transitions(topic, field: str):
    """Yield (t_us, old, new) whenever an integer/bool field changes value."""
    if topic is None or field not in topic.data:
        return
    t = topic.data["timestamp"]
    vals = topic.data[field]
    prev = None
    for i, v in enumerate(vals):
        v = int(v)
        if prev is not None and v != prev:
            yield int(t[i]), prev, v
        prev = v


def _initial(topic, field: str):
    """(t_us, value) of the first sample, or None."""
    if topic is None or field not in topic.data or not len(topic.data[field]):
        return None
    return int(topic.data["timestamp"][0]), int(topic.data[field][0])


def _extract_events(u: ULog, inc: Incident) -> None:
    # Arming — logs commonly start with the vehicle already armed (logging
    # starts on arm), so the initial state counts as an event too. Older
    # firmware does not log the `actuator_armed` topic at all; arming state
    # then lives in `vehicle_status.arming_state` (1=standby, 2=armed).
    armed = _topic(u, "actuator_armed")
    got_arming = False
    init = _initial(armed, "armed")
    if init and init[1]:
        got_arming = True
        inc.add_event(TimelineEvent(
            init[0], "px4_ulog:actuator_armed.armed", "arming", "info",
            "Vehicle ARMED (armed at log start)", {"armed": True}))
    for t, _old, new in _transitions(armed, "armed"):
        got_arming = True
        inc.add_event(TimelineEvent(
            t, "px4_ulog:actuator_armed.armed", "arming", "info",
            "Vehicle ARMED" if new else "Vehicle DISARMED", {"armed": bool(new)}))
    if not got_arming:
        vs_arm = _topic(u, "vehicle_status")
        init = _initial(vs_arm, "arming_state")
        if init is not None and init[1] == 2:
            inc.add_event(TimelineEvent(
                init[0], "px4_ulog:vehicle_status.arming_state", "arming", "info",
                "Vehicle ARMED (armed at log start)", {"armed": True}))
        for t, old, new in _transitions(vs_arm, "arming_state"):
            if new == 2:
                inc.add_event(TimelineEvent(
                    t, "px4_ulog:vehicle_status.arming_state", "arming", "info",
                    "Vehicle ARMED", {"armed": True}))
            elif old == 2:
                inc.add_event(TimelineEvent(
                    t, "px4_ulog:vehicle_status.arming_state", "arming", "info",
                    "Vehicle DISARMED", {"armed": False}))

    # Flight mode changes
    vs = _topic(u, "vehicle_status")
    init = _initial(vs, "nav_state")
    if init is not None:
        inc.add_event(TimelineEvent(
            init[0], "px4_ulog:vehicle_status.nav_state", "mode_change", "info",
            f"Mode at log start: {NAV_STATE.get(init[1], f'NAV_STATE_{init[1]}')}",
            {"old": None, "new": init[1]}))
    for t, old, new in _transitions(vs, "nav_state"):
        inc.add_event(TimelineEvent(
            t, "px4_ulog:vehicle_status.nav_state", "mode_change", "info",
            f"Mode: {NAV_STATE.get(old, f'NAV_STATE_{old}')} -> {NAV_STATE.get(new, f'NAV_STATE_{new}')}",
            {"old": old, "new": new}))
    for t, _old, new in _transitions(vs, "failsafe"):
        if new:
            inc.add_event(TimelineEvent(
                t, "px4_ulog:vehicle_status.failsafe", "failsafe", "critical", "FAILSAFE activated"))
        else:
            inc.add_event(TimelineEvent(
                t, "px4_ulog:vehicle_status.failsafe", "failsafe", "info", "Failsafe cleared"))

    # Takeoff / landing
    land = _topic(u, "vehicle_land_detected")
    for t, _old, new in _transitions(land, "landed"):
        inc.add_event(TimelineEvent(
            t, "px4_ulog:vehicle_land_detected.landed", "flight_phase", "info",
            "Landing detected" if new else "Takeoff detected"))

    # Failure detector
    fd = _topic(u, "failure_detector_status")
    if fd is not None:
        for f in ("fd_roll", "fd_pitch", "fd_alt", "fd_ext", "fd_arm_escs", "fd_battery",
                  "fd_imbalanced_prop", "fd_motor"):
            for t, _old, new in _transitions(fd, f):
                if new:
                    inc.add_event(TimelineEvent(
                        t, f"px4_ulog:failure_detector_status.{f}", "failure_detector", "critical",
                        f"Failure detector tripped: {f[3:].upper()}"))

    # Firmware text messages (the pilot-visible warnings/errors)
    sev_map = {"EMERGENCY": "critical", "ALERT": "critical", "CRITICAL": "critical",
               "ERROR": "critical", "WARNING": "warning", "NOTICE": "info", "INFO": "info",
               "DEBUG": "info"}
    for m in u.logged_messages:
        lvl = m.log_level_str()
        inc.add_event(TimelineEvent(
            int(m.timestamp), "px4_ulog:logged_message", "message",
            sev_map.get(lvl, "info"), f"[{lvl}] {m.message}"))
