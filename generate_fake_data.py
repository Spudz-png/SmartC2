"""Generate realistic fake aerobic workout data for UI testing.
Run once:  python generate_fake_data.py
"""
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

random.seed(42)
np.random.seed(42)

DATA = Path(__file__).parent / "data" / "workouts"
DATA.mkdir(parents=True, exist_ok=True)

# Clear old workouts so we start clean
for old in DATA.glob("*.json"):
    old.unlink()

# Update settings — aerobic zone is 190-210W so FTP sits higher
SETTINGS_PATH = Path(__file__).parent / "data" / "settings.json"
SETTINGS_PATH.write_text(json.dumps({"ftp": 240, "threshold_hr": 175, "rest_hr": 55}))


# ── Force curve shape profiles ───────────────────────────────────────────────
# Each workout is assigned one shape; strokes within it vary slightly around it.

def _bell(t: float, peak_pct: float, rise_exp: float, fall_exp: float) -> float:
    if t < peak_pct:
        return math.sin(math.pi / 2 * t / peak_pct) ** rise_exp
    return max(0.0, math.cos(math.pi / 2 * (t - peak_pct) / (1 - peak_pct))) ** fall_exp


def make_force_curve(n_samples: int, peak_force: float,
                     shape: str, base_noise: float) -> list[float]:
    curve = []
    for i in range(n_samples):
        t = i / (n_samples - 1)

        if shape == "classic":
            # Textbook asymmetric bell — fast rise, moderate fall
            peak_pct = random.uniform(0.37, 0.47)
            base = _bell(t, peak_pct, 1.4, 0.9)

        elif shape == "early_peak":
            # Aggressive catch, quick drop — peak in first third
            peak_pct = random.uniform(0.25, 0.33)
            base = _bell(t, peak_pct, 1.1, 1.6)

        elif shape == "late_push":
            # Gradual build, late leg drive — peak past midpoint
            peak_pct = random.uniform(0.52, 0.60)
            base = _bell(t, peak_pct, 1.9, 0.7)

        elif shape == "plateau":
            # Sustained flat force from ~30–62% then drops
            if t < 0.30:
                base = math.sin(math.pi / 2 * t / 0.30) ** 1.2
            elif t < 0.62:
                base = 1.0 - 0.07 * ((t - 0.46) / 0.16) ** 2
            else:
                base = max(0.0, math.cos(math.pi / 2 * (t - 0.62) / 0.38) ** 0.8)

        elif shape == "choppy":
            # Erratic / fatigued stroke — normal bell but 2.5× noise
            peak_pct = random.uniform(0.35, 0.50)
            base = _bell(t, peak_pct, 1.4, 0.9)
            base_noise = base_noise * 2.5

        else:  # "smooth"
            # Very clean low-noise bell — highly consistent technique
            peak_pct = random.uniform(0.38, 0.45)
            base = _bell(t, peak_pct, 1.4, 0.9)
            base_noise = base_noise * 0.25

        val = max(0.0, peak_force * base * (1 + random.gauss(0, base_noise)))
        curve.append(round(val, 1))

    return curve


# ── Single stroke ─────────────────────────────────────────────────────────────

def make_stroke(index: int, base_watts: int, base_split: int,
                base_hr: int, base_rate: float, shape: str) -> dict:
    jitter = lambda v, pct: v * (1 + random.gauss(0, pct))

    # Drive time: 9–11 samples × 0.1 s → average ~1.00 s (target 0.95–1.05)
    n_samples    = random.choices([9, 10, 10, 10, 11], k=1)[0]
    drive_time   = round(n_samples * 0.1, 2)
    drive_length = round(jitter(1.35, 0.04), 2)   # ~1.35 m typical aerobic drive
    peak_force   = round(jitter(base_watts * 1.05, 0.06), 1)

    curve    = make_force_curve(n_samples, peak_force, shape, 0.06)
    peak     = max(curve) if curve else peak_force
    peak_idx = curve.index(peak) if curve else 0

    # Clamp HR to aerobic plausible range
    hr = min(160, max(118, int(jitter(base_hr, 0.025))))

    return {
        "index":        index,
        "force_curve":  curve,
        "peak_force":   peak,
        "time_to_peak": round(peak_idx / len(curve) * 100, 1) if curve else 0,
        "elapsed_time": round(index * (60 / base_rate), 1),
        "distance":     round(index * 10.0, 1),
        "hr":           hr,
        "watts":        max(155, int(jitter(base_watts, 0.06))),
        "split":        int(jitter(base_split, 0.03)),
        "drive_length": drive_length,
        "drive_time":   drive_time,
    }


# ── Full workout ──────────────────────────────────────────────────────────────

def make_workout(date: datetime, n_strokes: int, base_watts: int,
                 base_split: int, base_hr: int, base_rate: float,
                 shape: str) -> dict:
    strokes = [
        make_stroke(i + 1, base_watts, base_split, base_hr, base_rate, shape)
        for i in range(n_strokes)
    ]

    duration  = n_strokes * (60 / base_rate)
    avg_watts = round(sum(s["watts"] for s in strokes) / n_strokes, 1)
    avg_split = round(sum(s["split"] for s in strokes) / n_strokes, 1)
    avg_hr    = round(sum(s["hr"]    for s in strokes) / n_strokes, 1)
    peaks     = [s["peak_force"]   for s in strokes]
    ttps      = [s["time_to_peak"] for s in strokes]
    d_lens    = [s["drive_length"] for s in strokes]
    d_times   = [s["drive_time"]   for s in strokes]
    rates     = [round(base_rate * (1 + random.gauss(0, 0.02)), 1) for _ in strokes]
    hrs       = [s["hr"] for s in strokes]

    normed = []
    for s in strokes:
        c  = s["force_curve"]
        ox = np.linspace(0, 1, len(c))
        nx = np.linspace(0, 1, 100)
        normed.append(np.interp(nx, ox, c))
    avg_normed  = np.mean(normed, axis=0)
    peak_n      = float(np.max(avg_normed)) or 1.0
    errors      = [float(np.mean(np.abs(n - avg_normed))) / peak_n for n in normed]
    consistency = round(max(0.0, 100.0 * (1.0 - float(np.mean(errors)) * 4.0)), 1)

    avg_raw_len = float(np.mean([len(s["force_curve"]) for s in strokes]))
    total_secs  = avg_raw_len * 0.1
    time_axis   = [round(i / 99 * total_secs, 3) for i in range(100)]
    avg_curve   = [round(float(v), 1) for v in avg_normed.tolist()]

    metrics = {
        "stroke_count":            n_strokes,
        "duration":                round(duration, 1),
        "average_force_curve":     avg_curve,
        "time_axis":               time_axis,
        "peak_forces":             peaks,
        "average_peak_force":      round(float(np.mean(peaks)), 1),
        "time_to_peak_trend":      ttps,
        "average_time_to_peak":    round(float(np.mean(ttps)), 1),
        "consistency_score":       consistency,
        "average_watts":           avg_watts,
        "average_split":           avg_split,
        "average_hr":              avg_hr,
        "average_drive_length":    round(float(np.mean(d_lens)), 2),
        "average_drive_time":      round(float(np.mean(d_times)), 2),
        "stroke_indices":          [s["index"] for s in strokes],
        "watts_per_stroke":        [s["watts"] for s in strokes],
        "split_per_stroke":        [s["split"] for s in strokes],
        "stroke_rates":            rates,
        "hr_per_stroke":           hrs,
        "drive_length_per_stroke": [s["drive_length"] for s in strokes],
        "drive_time_per_stroke":   [s["drive_time"]   for s in strokes],
        "hr_trend":                hrs,
        "force_curve_shape":       shape,
    }

    ftp = 240
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


# ── Aerobic training schedule — 30 sessions over 10 weeks ────────────────────
# Columns: (days_ago, n_strokes, watts, split_secs, hr, spm, shape)
#
# Watts 190–210  |  HR 135–150  |  SPM 18–22  |  drive time ~1.0 s avg
# Split in seconds for 500 m (≈119–123 s at this power band)
#
# Shape rotation: classic, early_peak, late_push, plateau, smooth, choppy

SESSIONS = [
    # Week 1 — base building, easy aerobic
    (70, 180, 191, 123, 136, 18.5, "classic"),
    (68, 200, 193, 122, 138, 19.0, "smooth"),
    (66, 160, 190, 123, 135, 18.5, "early_peak"),

    # Week 2
    (63, 220, 195, 121, 139, 19.5, "classic"),
    (61, 180, 192, 122, 137, 19.0, "late_push"),
    (59, 160, 191, 123, 136, 18.5, "plateau"),

    # Week 3 — moderate volume
    (56, 240, 198, 120, 141, 20.0, "smooth"),
    (54, 200, 196, 121, 140, 19.5, "classic"),
    (52, 180, 193, 122, 138, 19.0, "choppy"),

    # Week 4
    (49, 260, 200, 120, 143, 20.0, "early_peak"),
    (47, 200, 198, 120, 142, 20.0, "late_push"),
    (45, 180, 194, 122, 138, 19.5, "classic"),

    # Week 5 — build
    (42, 280, 202, 119, 144, 20.5, "smooth"),
    (40, 220, 200, 120, 143, 20.0, "plateau"),
    (38, 180, 196, 121, 140, 19.5, "early_peak"),

    # Week 6
    (35, 300, 204, 119, 146, 21.0, "classic"),
    (33, 220, 202, 119, 144, 20.5, "late_push"),
    (31, 180, 197, 120, 141, 20.0, "smooth"),

    # Week 7 — quality aerobic
    (28, 280, 206, 118, 147, 21.0, "plateau"),
    (26, 220, 204, 119, 145, 20.5, "choppy"),
    (24, 180, 199, 120, 142, 20.0, "classic"),

    # Week 8
    (21, 300, 207, 118, 148, 21.5, "smooth"),
    (19, 220, 205, 118, 146, 21.0, "early_peak"),
    (17, 180, 200, 120, 143, 20.0, "late_push"),

    # Week 9 — peak aerobic
    (14, 320, 209, 117, 149, 21.5, "classic"),
    (12, 240, 207, 118, 148, 21.0, "plateau"),
    (10, 200, 203, 119, 145, 20.5, "smooth"),

    # Week 10 — consolidation
    (7,  280, 208, 117, 149, 21.5, "early_peak"),
    (5,  220, 205, 118, 147, 21.0, "classic"),
    (2,  200, 203, 119, 145, 20.0, "late_push"),
]

today = datetime.now().replace(hour=7, minute=30, second=0, microsecond=0)

print(f"{'Date':<12} {'Strokes':>7} {'Watts':>6} {'HR':>5} {'AvgDT':>6} {'TSS':>6}  Shape")
print("-" * 60)

for offset, n, watts, split, hr, rate, shape in SESSIONS:
    date    = today - timedelta(days=offset)
    workout = make_workout(date, n, watts, split, hr, rate, shape)
    path    = DATA / f"{workout['id']}.json"
    path.write_text(json.dumps(workout, indent=2))

    m     = workout["metrics"]
    avg_dt = round(sum(m["drive_time_per_stroke"]) / len(m["drive_time_per_stroke"]), 2)
    print(f"  {date.strftime('%Y-%m-%d')}  {n:>5} strokes"
          f"  {m['average_watts']:>5.0f}W"
          f"  {m['average_hr']:>5.0f} bpm"
          f"  {avg_dt:.2f}s"
          f"  TSS {workout['tss']:>5.1f}"
          f"  [{shape}]")

print(f"\nGenerated {len(SESSIONS)} workouts -> {DATA}")
