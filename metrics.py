"""Aggregate metrics for a completed workout."""
from __future__ import annotations
import numpy as np
from workout_recorder import WorkoutRecorder
from stroke_processor import average_curve, consistency_score, time_axis_for_average


def compute(recorder: WorkoutRecorder) -> dict:
    strokes = recorder.strokes
    if not strokes:
        return {}

    avg       = average_curve(strokes)
    time_axis = time_axis_for_average(strokes)
    peaks        = [s.peak_force       for s in strokes]
    ttps         = [s.time_to_peak_pct for s in strokes]
    watts        = [s.watts            for s in strokes]
    splits       = [s.split            for s in strokes]
    rates        = [s.rate             for s in strokes]
    hrs          = [s.hr               for s in strokes]
    drive_lens   = [s.drive_length     for s in strokes]
    drive_times  = [s.drive_time       for s in strokes]
    hr_samples   = recorder.hr_samples

    valid_watts       = [w for w in watts       if w  > 0]
    valid_splits      = [s for s in splits      if s  > 0]
    valid_rates       = [r for r in rates       if r  > 0]
    valid_hrs         = [h for h in hrs         if h  > 0]
    valid_drive_lens  = [d for d in drive_lens  if d  > 0]
    valid_drive_times = [d for d in drive_times if d  > 0]

    def fmt(v: float, dp: int = 1) -> float:
        return round(float(v), dp)

    return {
        # summary scalars
        "stroke_count":         len(strokes),
        "duration":             fmt(recorder.duration, 1),
        "average_peak_force":   fmt(np.mean(peaks)),
        "consistency_score":    consistency_score(strokes),
        "average_time_to_peak": fmt(np.mean(ttps)),
        "average_watts":        fmt(np.mean(valid_watts))       if valid_watts       else None,
        "average_split":        fmt(np.mean(valid_splits))      if valid_splits      else None,
        "average_hr":           fmt(np.mean(hr_samples))        if hr_samples        else None,
        "average_drive_length": fmt(np.mean(valid_drive_lens))  if valid_drive_lens  else None,
        "average_drive_time":   fmt(np.mean(valid_drive_times)) if valid_drive_times else None,

        # chart data — average force curve
        "average_force_curve":  [fmt(v) for v in avg.tolist()],
        "time_axis":            time_axis,

        # per-stroke series (all same length = stroke_count)
        "stroke_indices":       [s.index for s in strokes],
        "peak_forces":          peaks,
        "time_to_peak_trend":   ttps,
        "watts_per_stroke":      watts,
        "split_per_stroke":      splits,
        "stroke_rates":          rates,
        "hr_per_stroke":         hrs,
        "drive_length_per_stroke": drive_lens,
        "drive_time_per_stroke":   drive_times,

        # raw HR samples (higher frequency than per-stroke)
        "hr_trend":             hr_samples,
    }
