"""Workout state machine — accumulates strokes during a session."""
from __future__ import annotations
import time
from dataclasses import dataclass, field


@dataclass
class Stroke:
    index:            int
    timestamp:        float
    force_curve:      list[float]
    peak_force:       float
    time_to_peak_pct: float
    elapsed_time:     float = 0.0
    distance:         float = 0.0
    hr:               int   = 0
    watts:            int   = 0
    split:            int   = 0    # seconds per 500m
    rate:             float = 0.0  # spm
    drive_length:     float = 0.0  # metres
    drive_time:       float = 0.0  # seconds (derived from force curve sample count)


class WorkoutRecorder:
    def __init__(self) -> None:
        self.strokes:      list[Stroke] = []
        self.hr_samples:   list[int]    = []
        self.start_time:   float | None = None
        self.end_time:     float | None = None
        self._force_buf:   list[float]  = []
        self._last_stroke: dict         = {}
        self._last_hr:     int          = 0
        self._seq_times:   list[float]  = []  # timestamps of each seq-0 packet

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        self.strokes      = []
        self.hr_samples   = []
        self._force_buf   = []
        self._last_stroke = {}
        self._last_hr     = 0
        self._seq_times   = []
        self.start_time   = time.time()
        self.end_time     = None

    def stop(self) -> None:
        self._flush()
        self.end_time = time.time()

    # ---------------------------------------------------------------- properties
    @property
    def duration(self) -> float:
        if self.start_time is None:
            return 0.0
        return (self.end_time or time.time()) - self.start_time

    @property
    def stroke_rate(self) -> float:
        """Instantaneous rate (spm) from last two stroke-start timestamps."""
        if len(self._seq_times) < 2:
            return 0.0
        gap = self._seq_times[-1] - self._seq_times[-2]
        return round(60.0 / gap, 1) if gap > 0 else 0.0

    # ---------------------------------------------------------------- callbacks
    def on_force_packet(self, seq: int, values: list[float]) -> Stroke | None:
        """Call for every CE06003D notification.
        Returns a completed Stroke when the previous one is finalised."""
        if seq == 0:
            stroke = self._flush()
            self._force_buf = list(values)
            self._seq_times.append(time.time())
            return stroke
        else:
            self._force_buf.extend(values[1:])  # first value overlaps previous packet
            return None

    def on_stroke_data(self, data: dict) -> None:
        self._last_stroke = data

    def on_hr(self, hr: int) -> None:
        self._last_hr = hr
        self.hr_samples.append(hr)

    # ------------------------------------------------------------------ private
    def _flush(self) -> Stroke | None:
        buf, self._force_buf = self._force_buf, []
        if len(buf) < 5:
            return None
        peak     = max(buf)
        peak_idx = buf.index(peak)
        stroke   = Stroke(
            index            = len(self.strokes) + 1,
            timestamp        = time.time(),
            force_curve      = buf,
            peak_force       = round(peak, 1),
            time_to_peak_pct = round(peak_idx / len(buf) * 100.0, 1),
            elapsed_time     = self._last_stroke.get("elapsed_time", 0.0),
            distance         = self._last_stroke.get("distance", 0.0),
            hr               = self._last_hr,
            watts            = self._last_stroke.get("watts", 0),
            split            = self._last_stroke.get("split", 0),
            rate             = self.stroke_rate,
            drive_length     = self._last_stroke.get("drive_length", 0.0),
            drive_time       = round(len(buf) * 0.1, 2),
        )
        self.strokes.append(stroke)
        return stroke
