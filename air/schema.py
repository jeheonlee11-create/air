"""Normalized incident schema.

Every ingested source (PX4 ULog, ArduPilot dataflash, detection alerts, weather)
is reduced to the same three primitives so analyzers never touch vendor formats:

- Series:        a named, unit-tagged time series with a source reference
- TimelineEvent: a discrete event at a timestamp with severity and provenance
- SourceFile:    the raw evidence file, hashed at ingest (SHA-256)

Timestamps are microseconds on the vehicle clock (t_us). If any source provides
an absolute UTC anchor (e.g. GPS time), `utc_anchor` maps t_us -> UTC.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SourceFile:
    path: str
    sha256: str
    size_bytes: int
    kind: str  # "px4_ulog" | "ardupilot_bin" | "procedures" | ...
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: str, kind: str, meta: dict | None = None) -> SourceFile:
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
                size += len(chunk)
        return cls(path=path, sha256=h.hexdigest(), size_bytes=size, kind=kind, meta=meta or {})


@dataclass
class Series:
    name: str          # normalized name, e.g. "alt_baro_m"
    source: str        # provenance, e.g. "px4_ulog:vehicle_air_data.baro_alt_meter"
    t_us: list[int]
    values: list[float]
    units: str = ""

    def sample_at(self, t: int, max_age_us: int | None = None) -> tuple[int, float] | None:
        """(t_sample, value) of the last sample at or before t (series are time-ordered).

        With max_age_us, a sample older than t - max_age_us is stale and None is
        returned: a sensor that stopped reporting is a gap, not its last value.
        """
        lo, hi, ans = 0, len(self.t_us) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.t_us[mid] <= t:
                ans = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if ans is None:
            return None
        if max_age_us is not None and t - self.t_us[ans] > max_age_us:
            return None
        return self.t_us[ans], self.values[ans]

    def at_or_before(self, t: int, max_age_us: int | None = None) -> float | None:
        """Value of sample_at(), or None (no sample yet, or stale)."""
        hit = self.sample_at(t, max_age_us)
        return hit[1] if hit else None


@dataclass
class TimelineEvent:
    t_us: int
    source: str        # provenance
    kind: str          # "mode_change" | "failsafe" | "arming" | "message" | ...
    severity: str      # "info" | "warning" | "critical"
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class UtcAnchor:
    """Maps vehicle time to UTC: utc_us = t_us + offset_us."""
    offset_us: int
    source: str

    def to_utc(self, t_us: int) -> datetime:
        return datetime.fromtimestamp((t_us + self.offset_us) / 1e6, tz=timezone.utc)


@dataclass
class Incident:
    incident_id: str
    created_utc: str
    sources: list[SourceFile] = field(default_factory=list)
    aircraft: dict = field(default_factory=dict)   # hw/sw versions, airframe
    t0_us: int = 0
    t1_us: int = 0
    utc_anchor: UtcAnchor | None = None
    home: dict | None = None                       # {"lat":..,"lon":..,"alt_m":..}
    series: dict[str, Series] = field(default_factory=dict)
    events: list[TimelineEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # ingest caveats — data gaps etc.

    @property
    def duration_s(self) -> float:
        return (self.t1_us - self.t0_us) / 1e6

    def series_or_none(self, name: str) -> Series | None:
        s = self.series.get(name)
        return s if s and len(s.t_us) >= 2 else None

    def add_event(self, ev: TimelineEvent) -> None:
        self.events.append(ev)

    def sorted_events(self) -> list[TimelineEvent]:
        return sorted(self.events, key=lambda e: e.t_us)

    def t_rel(self, t_us: int) -> float:
        """Seconds since start of log."""
        return (t_us - self.t0_us) / 1e6

    def t_label(self, t_us: int) -> str:
        rel = f"T+{self.t_rel(t_us):.1f}s"
        if self.utc_anchor:
            return f"{self.utc_anchor.to_utc(t_us).strftime('%H:%M:%S')}Z ({rel})"
        return rel


@dataclass
class Finding:
    code: str          # stable ID, e.g. "GPS-JAM"
    title: str
    severity: str      # "info" | "warning" | "critical"
    summary: str       # one-paragraph plain-language statement
    evidence: list[dict] = field(default_factory=list)  # [{"t_us":..,"source":..,"value":..,"note":..}]
    threshold: dict = field(default_factory=dict)        # {"metric":..,"warn":..,"fail":..,"basis":..}
    kind: str = "anomaly"  # "anomaly" | "conflict" | "integrity" | "conformance"

    def to_dict(self) -> dict:
        return {
            "code": self.code, "title": self.title, "severity": self.severity,
            "summary": self.summary, "evidence": self.evidence,
            "threshold": self.threshold, "kind": self.kind,
        }


SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
