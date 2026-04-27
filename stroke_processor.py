"""Force curve signal processing."""
from __future__ import annotations
import numpy as np
from workout_recorder import Stroke

N_POINTS        = 100   # every curve is normalised to this many points
SAMPLE_INTERVAL = 0.1   # seconds per raw force-plot sample (~10 Hz from PM5)


def normalize(curve: list[float], n: int = N_POINTS) -> np.ndarray:
    arr   = np.array(curve, dtype=float)
    old_x = np.linspace(0, 1, len(arr))
    new_x = np.linspace(0, 1, n)
    return np.interp(new_x, old_x, arr)


def average_curve(strokes: list[Stroke]) -> np.ndarray:
    if not strokes:
        return np.zeros(N_POINTS)
    return np.mean([normalize(s.force_curve) for s in strokes], axis=0)


def consistency_score(strokes: list[Stroke]) -> float:
    """0–100; 100 = every stroke identical to the average."""
    if len(strokes) < 2:
        return 100.0
    normed = [normalize(s.force_curve) for s in strokes]
    avg    = np.mean(normed, axis=0)
    peak   = float(np.max(avg)) or 1.0
    errors = [float(np.mean(np.abs(n - avg))) / peak for n in normed]
    return round(max(0.0, 100.0 * (1.0 - float(np.mean(errors)) * 4.0)), 1)


def time_axis_for_average(strokes: list[Stroke]) -> list[float]:
    """Real-time x-axis (seconds) for the normalised average curve."""
    avg_raw_len = float(np.mean([len(s.force_curve) for s in strokes]))
    total_secs  = avg_raw_len * SAMPLE_INTERVAL
    return [round(i / (N_POINTS - 1) * total_secs, 3) for i in range(N_POINTS)]
