"""
Training load calculations using the Banister impulse-response model.

TSS  — Training Stress Score for one workout
CTL  — Chronic Training Load  (fitness)   42-day exponential decay
ATL  — Acute Training Load    (fatigue)    7-day exponential decay
TSB  — Training Stress Balance (form)  =  CTL - ATL

TSS is calculated from power when FTP is set, otherwise falls back to
heart-rate-based hrTSS.
"""
from __future__ import annotations
import math
from datetime import date, timedelta

TAU_CTL = 42   # days — fitness time constant
TAU_ATL = 7    # days — fatigue time constant

# decay factors (recomputed once at import time)
_K_CTL = math.exp(-1 / TAU_CTL)
_K_ATL = math.exp(-1 / TAU_ATL)


# ────────────────────────────────────────────── per-workout TSS
def tss_power(avg_watts: float, duration_secs: float, ftp: float) -> float:
    """Power-based TSS.  Requires FTP > 0 and avg_watts > 0."""
    if ftp <= 0 or avg_watts <= 0 or duration_secs <= 0:
        return 0.0
    intensity_factor = avg_watts / ftp
    return round((duration_secs * avg_watts * intensity_factor) / (ftp * 3600) * 100, 1)


def tss_hr(avg_hr: float, duration_secs: float,
           threshold_hr: float, rest_hr: float) -> float:
    """Heart-rate-based TSS (hrTSS).  Falls back when power is unavailable."""
    hr_range = threshold_hr - rest_hr
    if hr_range <= 0 or avg_hr <= rest_hr or duration_secs <= 0:
        return 0.0
    hrr = (avg_hr - rest_hr) / hr_range          # HR reserve ratio
    return round(duration_secs / 3600 * hrr ** 2 * 100, 1)


def workout_tss(metrics: dict, settings: dict) -> tuple[float, str]:
    """
    Return (tss, method) for a single workout.
    Prefers power-based TSS; falls back to hrTSS; returns (0, 'none') if
    neither is possible.
    """
    ftp          = settings.get("ftp", 0)
    threshold_hr = settings.get("threshold_hr", 175)
    rest_hr      = settings.get("rest_hr", 55)
    avg_watts    = metrics.get("average_watts") or 0
    avg_hr       = metrics.get("average_hr")    or 0
    duration     = metrics.get("duration", 0)

    if ftp > 0 and avg_watts > 0:
        return tss_power(avg_watts, duration, ftp), "power"
    if avg_hr > 0 and threshold_hr > rest_hr:
        return tss_hr(avg_hr, duration, threshold_hr, rest_hr), "hr"
    return 0.0, "none"


# ────────────────────────────────────────────── history computation
def compute_history(workouts: list[dict], settings: dict) -> list[dict]:
    """
    Given a list of workout dicts (each containing 'date' ISO string and
    'metrics' sub-dict), compute day-by-day CTL/ATL/TSB.

    Returns a list of dicts, one per training day (plus gaps filled in
    so chart lines are continuous), sorted chronologically.
    """
    if not workouts:
        return []

    # Build date → TSS map (multiple workouts in one day accumulate)
    tss_map: dict[str, float] = {}
    for w in workouts:
        d = w.get("date", "")[:10]
        if not d:
            continue
        tss, _ = workout_tss(w.get("metrics", {}), settings)
        tss_map[d] = tss_map.get(d, 0.0) + tss

    if not tss_map:
        return []

    dates = sorted(tss_map)
    start = date.fromisoformat(dates[0])
    end   = date.fromisoformat(dates[-1])

    ctl = 0.0
    atl = 0.0
    results: list[dict] = []
    current = start

    while current <= end:
        ds  = current.isoformat()
        tss = tss_map.get(ds, 0.0)
        ctl = ctl * _K_CTL + tss * (1 - _K_CTL)
        atl = atl * _K_ATL + tss * (1 - _K_ATL)
        tsb = ctl - atl
        results.append({
            "date": ds,
            "tss":  round(tss, 1),
            "ctl":  round(ctl, 1),
            "atl":  round(atl, 1),
            "tsb":  round(tsb, 1),
        })
        current += timedelta(days=1)

    return results
