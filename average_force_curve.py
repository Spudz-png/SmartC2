import numpy as np
import matplotlib.pyplot as plt

SAMPLE_INTERVAL = 0.1   # seconds per force-plot sample (10 Hz CSAFE polling)

all_strokes = []
all_durations = []   # drive duration in seconds for each stroke

def normalize_curve(curve, n_points=100):
    old_x = np.linspace(0, 1, len(curve))
    new_x = np.linspace(0, 1, n_points)
    return np.interp(new_x, old_x, curve)

def add_stroke(raw_curve):
    duration = len(raw_curve) * SAMPLE_INTERVAL
    all_durations.append(duration)
    normalized = normalize_curve(raw_curve, 100)
    all_strokes.append(normalized)

def generate_average_force_curve():
    curves = np.array(all_strokes)
    avg_curve = curves.mean(axis=0)
    avg_duration = np.mean(all_durations)

    x = np.linspace(0, avg_duration, len(avg_curve))

    plt.figure(figsize=(8, 5))
    plt.plot(x, avg_curve, linewidth=2, color="steelblue")
    plt.xlabel("Time (s)")
    plt.ylabel("Force (N)")
    plt.title("Average Force Curve")
    plt.xlim(left=0)
    plt.ylim(bottom=0)
    plt.grid(True)
    plt.tight_layout()
    plt.show(block=True)

    return avg_curve
