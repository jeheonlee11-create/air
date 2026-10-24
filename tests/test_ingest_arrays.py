"""ULog array fields (accel_clipping[0..2], *_inconsistency[0..3]) and the
hdg_test_ratio alias reach the analyzers.

Uses a tiny ULog writer so the test runs on a clean clone; the fixture-based
check at the bottom is skipped when the gitignored logs are absent.
"""

import os
import struct

import pytest

from air.analyze import run_all_analyzers
from air.ingest import ingest_ulog

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDG_LOG = os.path.join(REPO, "fixtures", "bb94988c-fc8c-4a44-b8ca-cf62052a227e.ulg")

T0 = 1_000_000
STEP = 1_000_000


def _msg(kind: str, payload: bytes) -> bytes:
    return struct.pack("<HB", len(payload), ord(kind)) + payload


def write_ulog(path, topics):
    """topics: [(name, "type field;...", struct_fmt_after_timestamp, [row, ...])].
    Each row is a tuple of field values; timestamps are T0, T0+STEP, ..."""
    out = b"ULog\x01\x12\x35" + b"\x01" + struct.pack("<Q", T0)
    out += _msg("B", bytes(40))                               # flag bits: none set
    for name, fields, _, _ in topics:
        out += _msg("F", f"{name}:uint64_t timestamp;{fields}".encode())
    for msg_id, (name, _, _, _) in enumerate(topics):
        out += _msg("A", struct.pack("<BH", 0, msg_id) + name.encode())
    for msg_id, (_, _, fmt, rows) in enumerate(topics):
        for i, row in enumerate(rows):
            out += _msg("D", struct.pack("<H", msg_id)
                        + struct.pack("<Q" + fmt, T0 + i * STEP, *row))
    with open(path, "wb") as f:
        f.write(out)


@pytest.fixture
def synthetic_log(tmp_path):
    p = tmp_path / "arrays.ulg"
    clip = [(0, 0, 0), (10, 0, 0), (25, 5, 0), (40, 5, 1), (60, 9, 1)]   # cumulative per axis
    accel_inc = [(0.0, 0.1, 0.0, 0.0), (0.0, 0.2, 0.0, 0.0), (0.0, 2.4, 0.3, 0.0),
                 (0.0, 0.4, 0.1, 0.0), (0.0, 0.2, 0.0, 0.0)]
    gyro_inc = [(0.0, 0.01, 0.0, 0.0)] * 2 + [(0.0, 0.0, 0.09, 0.0)] + [(0.0, 0.0, 0.0, 0.0)] * 2
    write_ulog(str(p), [
        ("actuator_armed", "bool armed;", "?", [(True,)] * 5),
        ("vehicle_imu_status", "uint32_t[3] accel_clipping;float accel_vibration_metric;",
         "3If", [(*c, 3.0) for c in clip]),
        ("sensors_status_imu",
         "float[4] accel_inconsistency_m_s_s;float[4] gyro_inconsistency_rad_s;",
         "4f4f", [(*a, *g) for a, g in zip(accel_inc, gyro_inc, strict=True)]),
        ("estimator_status", "float hdg_test_ratio;", "f", [(0.1,), (0.2,), (1.4,), (0.3,), (0.1,)]),
    ])
    return str(p)


def test_array_fields_become_series_with_provenance(synthetic_log):
    inc = ingest_ulog(synthetic_log)

    clip = inc.series["accel_clip_count"]
    assert clip.values == [0, 10, 30, 46, 70]                 # summed across axes
    assert clip.source == "px4_ulog:vehicle_imu_status.accel_clipping[0..2] (sum across axes)"

    acc = inc.series["imu_accel_inconsistency"]
    assert acc.values[2] == pytest.approx(2.4)                # worst instance per sample
    assert acc.source == ("px4_ulog:sensors_status_imu.accel_inconsistency_m_s_s[0..3] "
                          "(max across instances)")
    gyro = inc.series["imu_gyro_inconsistency"]
    assert max(gyro.values) == pytest.approx(0.09)
    assert gyro.source.endswith("gyro_inconsistency_rad_s[0..3] (max across instances)")

    mag = inc.series["ekf_mag_test_ratio"]
    assert mag.source == "px4_ulog:estimator_status.hdg_test_ratio"
    assert max(mag.values) == pytest.approx(1.4)


def test_clip_and_imu_disagree_analyzers_fire(synthetic_log):
    findings = {f.code: f for f in run_all_analyzers(ingest_ulog(synthetic_log))}
    assert "VIB-CLIP" in findings
    assert findings["VIB-CLIP"].evidence[0]["value"] == 70
    assert "IMU-DISAGREE" in findings
    assert findings["IMU-DISAGREE"].severity == "critical"    # 2.4 > 1.5 m/s^2
    assert "EKF-MAGNETOMETER" in findings                     # via the hdg alias


@pytest.mark.skipif(not os.path.exists(HDG_LOG), reason="fixture not downloaded")
def test_real_fixture_array_fields_and_hdg_alias():
    inc = ingest_ulog(HDG_LOG)
    assert "accel_clipping[0..2]" in inc.series["accel_clip_count"].source
    assert "accel_inconsistency_m_s_s[0..3]" in inc.series["imu_accel_inconsistency"].source
    assert inc.series["ekf_mag_test_ratio"].source.endswith("hdg_test_ratio")
