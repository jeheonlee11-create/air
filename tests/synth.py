"""Shared helpers for building synthetic incidents (no fixture logs needed)."""

from __future__ import annotations

from air.schema import Incident, Series, TimelineEvent

S = 1_000_000  # microseconds per second


def series(name: str, points: list[tuple[float, float]], units: str = "",
           source: str | None = None) -> Series:
    """points: [(seconds, value), ...]"""
    return Series(name=name, source=source or f"test:{name}",
                  t_us=[int(t * S) for t, _ in points], values=[float(v) for _, v in points],
                  units=units)


def ramp(name: str, t0: float, t1: float, v0: float, v1: float, hz: float = 5.0,
         units: str = "") -> Series:
    n = int((t1 - t0) * hz) + 1
    pts = [(t0 + i / hz, v0 + (v1 - v0) * i / max(1, n - 1)) for i in range(n)]
    return series(name, pts, units)


def arm(t: float, armed: bool = True, with_data: bool = True) -> TimelineEvent:
    return TimelineEvent(int(t * S), "test:arming", "arming", "info",
                         "Vehicle ARMED" if armed else "Vehicle DISARMED",
                         {"armed": armed} if with_data else {})


def incident(*, t1: float = 100.0, series_list=(), events=(), home=None) -> Incident:
    inc = Incident(incident_id="test", created_utc="2026-01-01T00:00:00+00:00",
                   t0_us=0, t1_us=int(t1 * S), home=home)
    for s in series_list:
        inc.series[s.name] = s
    for e in events:
        inc.add_event(e)
    return inc
