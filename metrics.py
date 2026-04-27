"""Aggregate metrics for a completed workout."""
from __future__ import annotations
import numpy as np
from workout_recorder import WorkoutRecorder
from stroke_processor import average_curve, consistency_score, time_axis_for_average


def compute(recorder: WorkoutRecorder) -> dict:
    strokes = recorder.strokes
    if not strokes:
        return {}

    avg        = average_curve(strokes)
    time_axis  = time_axis_for_average(strokes)
    peaks      = [s.peak_force       for s in strokes]
    ttps       = [s.time_to_peak_pct for s in strokes]
    hrs        = recorder.hr_samples

    def fmt(v: float, dp: int = 1) -> float:
        return round(float(v), dp)

    return {
        "stroke_count":         len(strokes),
        "duration":             fmt(recorder.duration, 1),
        "average_force_curve":  [fmt(v) for v in avg.tolist()],
        "time_axis":            time_axis,
        "peak_forces":          peaks,
        "average_peak_force":   fmt(np.mean(peaks)),
        "time_to_peak_trend":   ttps,
        "average_time_to_peak": fmt(np.mean(ttps)),
        "consistency_score":    consistency_score(strokes),
        "average_hr":           fmt(np.mean(hrs)) if hrs else None,
        "hr_trend":             hrs,
        "stroke_indices":       [s.index for s in strokes],
    }
