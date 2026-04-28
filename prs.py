"""Personal Records — storage, detection, and comparison."""
from __future__ import annotations
import json
from pathlib import Path

_DATA_DIR  = Path(__file__).parent / "data"
_PR_FILE   = _DATA_DIR / "prs.json"

DISTANCE_TARGETS = {"2k": 2000, "5k": 5000, "6k": 6000, "10k": 10000}
TOLERANCE        = 0.05   # ±5% — a 2 050 m row still counts as a 2K

_DEFAULTS: dict = {"2k": None, "5k": None, "6k": None,
                   "10k": None, "max_watts": None}


# ─────────────────────────── persistence
def load() -> dict:
    if _PR_FILE.exists():
        try:
            return {**_DEFAULTS, **json.loads(_PR_FILE.read_text())}
        except Exception:
            pass
    return _DEFAULTS.copy()


def save(prs: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PR_FILE.write_text(json.dumps(prs, indent=2))


# ─────────────────────────── comparison
def _is_better(key: str, new_val: float, old_val: float | None) -> bool:
    if old_val is None:
        return True
    return new_val > old_val if key == "max_watts" else new_val < old_val


# ─────────────────────────── detection
def scan_workout(total_distance: float, duration: float,
                 watts_list: list[int]) -> dict:
    """Return PR candidates from one workout's raw numbers."""
    candidates: dict = {}
    for key, target in DISTANCE_TARGETS.items():
        if target * (1 - TOLERANCE) <= total_distance <= target * (1 + TOLERANCE):
            candidates[key] = round(duration, 1)
    valid_w = [w for w in watts_list if w > 0]
    if valid_w:
        candidates["max_watts"] = int(max(valid_w))
    return candidates


def update(candidates: dict) -> tuple[dict, dict]:
    """
    Merge candidates into stored PRs.
    Returns (all_prs, newly_broken_prs).
    """
    prs     = load()
    new_prs: dict = {}
    for key, val in candidates.items():
        if _is_better(key, val, prs.get(key)):
            new_prs[key] = val
            prs[key]     = val
    if new_prs:
        save(prs)
    return prs, new_prs


def scan_all(data_dir: Path) -> dict:
    """Rebuild PRs from scratch by scanning every saved workout JSON."""
    prs = _DEFAULTS.copy()
    for f in sorted(data_dir.glob("*.json")):
        try:
            d       = json.loads(f.read_text())
            strokes = d.get("strokes", [])
            if not strokes:
                continue
            dist    = strokes[-1].get("distance", 0)
            dur     = d.get("metrics", {}).get("duration", 0)
            watts   = d.get("metrics", {}).get("watts_per_stroke", [])
            for key, val in scan_workout(dist, dur, watts).items():
                if _is_better(key, val, prs.get(key)):
                    prs[key] = val
        except Exception:
            pass
    save(prs)
    return prs
