"""
Training load calculations using the Banister impulse-response model,
plus heart-rate zone formulas.

TSS  — Training Stress Score for one workout
CTL  — Chronic Training Load  (fitness)   42-day exponential decay
ATL  — Acute Training Load    (fatigue)    7-day exponential decay
TSB  — Training Stress Balance (form)  =  CTL - ATL

HR Zones are computed two ways:
  • % of Max HR  (simple, widely used)
  • Karvonen / HRR  (heart-rate reserve — more accurate when resting HR is known)
    Target HR = Rest HR + (Max HR − Rest HR) × zone %

Max HR estimation formulas (when measured max HR is unavailable):
  • Tanaka  (default / male):  208 − 0.7  × age
  • Gulati  (female):          206 − 0.88 × age
  • Fox     (classic):         220 − age
"""
from __future__ import annotations
import math
from datetime import date, timedelta

TAU_CTL = 42   # days — fitness time constant
TAU_ATL = 7    # days — fatigue time constant

_K_CTL = math.exp(-1 / TAU_CTL)
_K_ATL = math.exp(-1 / TAU_ATL)

# ────────────────────────────────────────────── HR zone definitions
# Each zone defined as (min%, max%) of the reference value
_ZONE_DEFS = [
    ("Zone 1", "Recovery",    0.50, 0.60, "#60a5fa"),
    ("Zone 2", "Aerobic",     0.60, 0.70, "#34d399"),
    ("Zone 3", "Tempo",       0.70, 0.80, "#fbbf24"),
    ("Zone 4", "Threshold",   0.80, 0.90, "#f97316"),
    ("Zone 5", "VO2 Max",     0.90, 1.00, "#ef4444"),
]


def max_hr_estimate(age: int, formula: str = "tanaka") -> int:
    """
    Estimate maximum heart rate from age.
      tanaka  — 208 − 0.7 × age   (default, accurate for most adults)
      gulati  — 206 − 0.88 × age  (validated for women)
      fox     — 220 − age          (classic, tends to overestimate for older adults)
    """
    formula = formula.lower()
    if formula == "gulati":
        return round(206 - 0.88 * age)
    if formula == "fox":
        return round(220 - age)
    return round(208 - 0.7 * age)   # tanaka


def hr_zones_max(max_hr: int) -> list[dict]:
    """5-zone system based on percentage of maximum heart rate."""
    return [
        {
            "zone":    name,
            "label":   label,
            "min_hr":  round(max_hr * lo),
            "max_hr":  round(max_hr * hi),
            "min_pct": round(lo * 100),
            "max_pct": round(hi * 100),
            "color":   color,
            "method":  "max_hr",
        }
        for name, label, lo, hi, color in _ZONE_DEFS
    ]


def hr_zones_karvonen(max_hr: int, rest_hr: int) -> list[dict]:
    """
    Karvonen / heart-rate-reserve zones.
    HRR = Max HR − Resting HR
    Zone boundary = Resting HR + HRR × zone_pct
    Requires resting HR; preferred when available.
    """
    hrr = max_hr - rest_hr
    return [
        {
            "zone":    name,
            "label":   label,
            "min_hr":  round(rest_hr + hrr * lo),
            "max_hr":  round(rest_hr + hrr * hi),
            "min_pct": round(lo * 100),
            "max_pct": round(hi * 100),
            "color":   color,
            "method":  "karvonen",
        }
        for name, label, lo, hi, color in _ZONE_DEFS
    ]


def classify_hr(hr: float, zones: list[dict]) -> dict:
    """Return the zone dict that contains this HR value."""
    for z in zones:
        if hr <= z["max_hr"]:
            return z
    return zones[-1]   # above Zone 5 — still Zone 5


def zone_distribution(hr_samples: list[int], zones: list[dict]) -> list[dict]:
    """
    Given a list of HR samples and zone definitions, return the % of
    samples spent in each zone.
    """
    if not hr_samples:
        return []
    counts = {z["zone"]: 0 for z in zones}
    for hr in hr_samples:
        counts[classify_hr(hr, zones)["zone"]] += 1
    total = len(hr_samples)
    return [
        {**z, "pct": round(counts[z["zone"]] / total * 100, 1)}
        for z in zones
    ]


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
    hrr = (avg_hr - rest_hr) / hr_range
    return round(duration_secs / 3600 * hrr ** 2 * 100, 1)


def workout_tss(metrics: dict, settings: dict) -> tuple[float, str]:
    """
    Return (tss, method) for a single workout.
    Prefers power-based TSS; falls back to hrTSS.
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


# ────────────────────────────────────────────── training history
def compute_history(workouts: list[dict], settings: dict) -> list[dict]:
    """Day-by-day CTL/ATL/TSB from all saved workouts."""
    if not workouts:
        return []

    tss_map: dict[str, float] = {}
    for w in workouts:
        d = w.get("date", "")[:10]
        if not d:
            continue
        tss, _ = workout_tss(w.get("metrics", {}), settings)
        tss_map[d] = tss_map.get(d, 0.0) + tss

    if not tss_map:
        return []

    dates   = sorted(tss_map)
    start   = date.fromisoformat(dates[0])
    end     = date.fromisoformat(dates[-1])
    ctl = atl = 0.0
    results: list[dict] = []
    current = start

    while current <= end:
        ds  = current.isoformat()
        tss = tss_map.get(ds, 0.0)
        ctl = ctl * _K_CTL + tss * (1 - _K_CTL)
        atl = atl * _K_ATL + tss * (1 - _K_ATL)
        results.append({
            "date": ds,
            "tss":  round(tss, 1),
            "ctl":  round(ctl, 1),
            "atl":  round(atl, 1),
            "tsb":  round(ctl - atl, 1),
        })
        current += timedelta(days=1)

    return results
