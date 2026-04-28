"""Generate realistic fake workout data for UI testing.
Run once:  python generate_fake_data.py
"""
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

DATA = Path(__file__).parent / "data" / "workouts"
DATA.mkdir(parents=True, exist_ok=True)

# ── Fake settings (so TSS calculation works)
SETTINGS_PATH = Path(__file__).parent / "data" / "settings.json"
if not SETTINGS_PATH.exists():
    SETTINGS_PATH.write_text(json.dumps({"ftp": 180, "threshold_hr": 175, "rest_hr": 55}))


def bell_curve(n_samples: int, peak_pct: float = 0.42,
               peak_force: float = 160.0, noise: float = 0.08) -> list[float]:
    """Generate a realistic rowing force curve (bell shape with noise)."""
    curve = []
    for i in range(n_samples):
        t = i / (n_samples - 1)
        # asymmetric bell: faster rise, slower fall
        if t < peak_pct:
            base = max(0.0, math.sin(math.pi / 2 * t / peak_pct))
            val  = peak_force * base ** 1.4
        else:
            base = max(0.0, math.cos(math.pi / 2 * (t - peak_pct) / (1 - peak_pct)))
            val  = peak_force * base ** 0.9
        val = max(0.0, val * (1 + random.gauss(0, noise)))
        curve.append(round(val, 1))
    return curve


def make_stroke(index: int, base_watts: int, base_split: int,
                base_hr: int, base_rate: float) -> dict:
    jitter = lambda v, pct: v * (1 + random.gauss(0, pct))

    peak_force   = round(jitter(base_watts * 1.05, 0.06), 1)
    n_samples    = random.randint(28, 42)
    drive_time   = round(n_samples * 0.1, 2)
    drive_length = round(jitter(0.50, 0.05), 2)
    peak_pct     = max(0.25, min(0.70, jitter(0.42, 0.08)))
    curve        = bell_curve(n_samples, peak_pct, peak_force)

    peak     = max(curve)
    peak_idx = curve.index(peak)

    return {
        "index":         index,
        "force_curve":   curve,
        "peak_force":    peak,
        "time_to_peak":  round(peak_idx / len(curve) * 100, 1),
        "elapsed_time":  round(index * (60 / base_rate), 1),
        "distance":      round(index * 7.5, 1),
        "hr":            int(jitter(base_hr, 0.03)),
        "watts":         int(jitter(base_watts, 0.07)),
        "split":         int(jitter(base_split, 0.04)),
        "drive_length":  drive_length,
        "drive_time":    drive_time,
    }


def make_workout(date: datetime, n_strokes: int, base_watts: int,
                 base_split: int, base_hr: int, base_rate: float) -> dict:
    strokes = [
        make_stroke(i + 1, base_watts, base_split, base_hr, base_rate)
        for i in range(n_strokes)
    ]

    duration    = n_strokes * (60 / base_rate)
    avg_watts   = round(sum(s["watts"] for s in strokes) / n_strokes, 1)
    avg_split   = round(sum(s["split"] for s in strokes) / n_strokes, 1)
    avg_hr      = round(sum(s["hr"]    for s in strokes) / n_strokes, 1)
    peaks       = [s["peak_force"]   for s in strokes]
    ttps        = [s["time_to_peak"] for s in strokes]
    d_lens      = [s["drive_length"] for s in strokes]
    d_times     = [s["drive_time"]   for s in strokes]
    rates       = [round(base_rate * (1 + random.gauss(0, 0.03)), 1) for _ in strokes]
    hrs         = [s["hr"] for s in strokes]

    # Consistency score — how similar the stroke shapes are
    import numpy as np
    normed = []
    for s in strokes:
        c  = s["force_curve"]
        ox = np.linspace(0, 1, len(c))
        nx = np.linspace(0, 1, 100)
        normed.append(np.interp(nx, ox, c))
    avg_normed   = np.mean(normed, axis=0)
    peak_n       = float(np.max(avg_normed)) or 1.0
    errors       = [float(np.mean(np.abs(n - avg_normed))) / peak_n for n in normed]
    consistency  = round(max(0.0, 100.0 * (1.0 - float(np.mean(errors)) * 4.0)), 1)

    avg_raw_len  = float(np.mean([len(s["force_curve"]) for s in strokes]))
    total_secs   = avg_raw_len * 0.1
    time_axis    = [round(i / 99 * total_secs, 3) for i in range(100)]
    avg_curve    = [round(float(v), 1) for v in avg_normed.tolist()]

    metrics = {
        "stroke_count":           n_strokes,
        "duration":               round(duration, 1),
        "average_force_curve":    avg_curve,
        "time_axis":              time_axis,
        "peak_forces":            peaks,
        "average_peak_force":     round(float(np.mean(peaks)), 1),
        "time_to_peak_trend":     ttps,
        "average_time_to_peak":   round(float(np.mean(ttps)), 1),
        "consistency_score":      consistency,
        "average_watts":          avg_watts,
        "average_split":          avg_split,
        "average_hr":             avg_hr,
        "average_drive_length":   round(float(np.mean(d_lens)), 2),
        "average_drive_time":     round(float(np.mean(d_times)), 2),
        "stroke_indices":         [s["index"] for s in strokes],
        "watts_per_stroke":       [s["watts"] for s in strokes],
        "split_per_stroke":       [s["split"] for s in strokes],
        "stroke_rates":           rates,
        "hr_per_stroke":          hrs,
        "drive_length_per_stroke":[s["drive_length"] for s in strokes],
        "drive_time_per_stroke":  [s["drive_time"]   for s in strokes],
        "hr_trend":               hrs,
    }

    # TSS (power-based, FTP=180)
    ftp = 180
    IF  = avg_watts / ftp
    tss = round((duration * avg_watts * IF) / (ftp * 3600) * 100, 1)

    wid = date.strftime("%Y%m%d_%H%M%S")
    return {
        "id":         wid,
        "date":       date.isoformat(),
        "tss":        tss,
        "tss_method": "power",
        "metrics":    metrics,
        "strokes":    strokes,
    }


# ── Workout schedule — 14 sessions over the past 6 weeks
# (date_offset_days, n_strokes, watts, split_secs, hr, spm)
SESSIONS = [
    (42, 18, 145, 175, 148, 19.0),   # easy base
    (39, 22, 155, 168, 153, 20.0),
    (36, 20, 148, 172, 150, 19.5),
    (33, 25, 165, 160, 160, 21.0),   # step up
    (30, 20, 152, 168, 154, 20.0),
    (27, 28, 170, 156, 163, 21.5),   # longer
    (24, 22, 158, 165, 157, 20.5),
    (21, 30, 175, 152, 167, 22.0),   # quality session
    (18, 20, 155, 168, 155, 20.0),   # recovery
    (15, 28, 178, 150, 168, 22.0),
    (12, 25, 172, 153, 165, 21.5),
    (9,  32, 182, 148, 170, 22.5),   # peak
    (6,  20, 150, 170, 152, 20.0),   # taper
    (3,  35, 185, 145, 172, 23.0),   # race simulation
    (1,  22, 162, 163, 158, 21.0),   # easy
]

today = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

for offset, n, watts, split, hr, rate in SESSIONS:
    date    = today - timedelta(days=offset)
    workout = make_workout(date, n, watts, split, hr, rate)
    path    = DATA / f"{workout['id']}.json"
    path.write_text(json.dumps(workout, indent=2))
    print(f"  {date.strftime('%Y-%m-%d')}  {n:2d} strokes  {watts}W  TSS {workout['tss']}")

print(f"\nGenerated {len(SESSIONS)} workouts in {DATA}")
