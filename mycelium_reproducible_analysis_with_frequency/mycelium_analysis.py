#!/usr/bin/env python3
"""
Reproducible analysis of mycelium extracellular voltage recordings under UV stimulation.

Expected directory structure:
    mycelium_analysis.py
    data/
        mycelium_ch1.npy
        mycelium_ch1_weight.npy
        mycelium_ch1_weight2.npy
        agar_control_ch3.npy

The script reproduces:
  - cycle-aligned median response
  - cycle-by-cycle kinetic descriptors
  - refined t50 for biphasic responses
  - recovery half-time
  - UV AUC
  - publication figures
  - CSV summary tables
  - a LaTeX summary table for inclusion in the report

Dependencies:
    numpy, pandas, matplotlib, scipy
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

# -----------------------------
# Configuration
# -----------------------------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIG = ROOT / "figures"
RESULTS = ROOT / "results"
FIG.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)

FS = 100.0                 # Hz
UV_START = 90.0            # s
CYCLE_PERIOD = 240.0       # s = 60 s UV + 180 s recovery
UV_ON = 60.0               # s
PRE = 30.0                 # baseline window before UV
POST = 180.0               # common recovery window

FILES = {
    "No weight": DATA / "mycelium_ch1.npy",
    "Weight 1": DATA / "mycelium_ch1_weight.npy",
    "Weight 2": DATA / "mycelium_ch1_weight2.npy",
    "Agar control": DATA / "agar_control_ch3.npy",
}


# -----------------------------
# Data handling
# -----------------------------
def load_and_filter(path):
    """Load voltage in V, convert to mV, and apply the student's SG filter."""
    x = np.load(path).astype(float) * 1000.0
    # Same processing used in the student's spike_analysis.py:
    # window = 101 samples = 1.01 s at 100 Hz; polynomial order = 3.
    return x, savgol_filter(x, 101, 3)


def aligned_cycles(path, ncycles=30, post_window=180):
    """
    Extract cycles aligned to UV ON.

    Each cycle is baseline-subtracted by the median voltage in the
    preceding 30 s. Returns time relative to UV ON and a cycle matrix.
    """
    _, y = load_and_filter(path)
    duration = len(y) / FS

    traces, ids = [], []
    for c in range(ncycles):
        t0 = UV_START + c * CYCLE_PERIOD
        ia = int((t0 - PRE) * FS)
        ib = int((t0 + post_window) * FS)

        if ia < 0 or ib > len(y):
            continue

        tr = y[ia:ib].copy()
        baseline = np.median(y[ia:int(t0 * FS)])
        tr -= baseline
        traces.append(tr)
        ids.append(c + 1)

    if not traces:
        return None, None, []

    arr = np.vstack(traces)
    t = np.arange(arr.shape[1]) / FS - PRE
    return t, arr, ids


# -----------------------------
# Kinetic descriptors
# -----------------------------
def first_crossing(t, y, target, direction="up"):
    """Linear-interpolated first threshold crossing."""
    if direction == "up":
        idx = np.where(y >= target)[0]
    else:
        idx = np.where(y <= target)[0]

    if len(idx) == 0:
        return np.nan

    i = idx[0]
    if i == 0:
        return float(t[0])

    if y[i] == y[i - 1]:
        return float(t[i])

    return float(
        t[i - 1]
        + (target - y[i - 1]) * (t[i] - t[i - 1]) / (y[i] - y[i - 1])
    )


def cycle_metrics(t, arr, ids, condition):
    """
    Calculate model-independent descriptors for each cycle.

    t50 is measured after the early minimum:
        target50 = V_min + 0.5*(V_sustained - V_min)

    where V_sustained is the median response from 50-60 s.
    """
    rows = []

    for j, cycle in enumerate(ids):
        tr = arr[j]

        early_mask = (t >= 0) & (t < 20)
        sustained_mask = (t >= 50) & (t < 60)
        uv_mask = (t >= 0) & (t < 60)
        recovery_mask = (t >= 60) & (t < 180)

        early_indices = np.where(early_mask)[0]
        i_min = early_indices[np.argmin(tr[early_indices])]
        t_min = t[i_min]
        v_min = tr[i_min]

        v_sustained = np.median(tr[sustained_mask])
        target50 = v_min + 0.5 * (v_sustained - v_min)
        target90 = v_min + 0.9 * (v_sustained - v_min)

        post_min = (t >= max(0, t_min)) & (t < 60)
        t_uv = t[post_min]
        y_uv = tr[post_min]

        t50 = first_crossing(t_uv, y_uv, target50, "up")
        t90 = first_crossing(t_uv, y_uv, target90, "up")

        amax = np.max(tr[uv_mask])
        t_peak = t[uv_mask][np.argmax(tr[uv_mask])]

        v_off = np.median(tr[(t >= 59.5) & (t < 60)])
        t_rec = t[recovery_mask] - 60
        y_rec = tr[recovery_mask]
        target_rec = 0.5 * v_off

        if v_off >= 0:
            idx = np.where(y_rec <= target_rec)[0]
        else:
            idx = np.where(y_rec >= target_rec)[0]

        recovery_half = np.nan if len(idx) == 0 else float(t_rec[idx[0]])

        auc = np.trapezoid(tr[uv_mask], t[uv_mask])

        rows.append({
            "Condition": condition,
            "Cycle": cycle,
            "Amax_mV": amax,
            "t_peak_s": t_peak,
            "t_min_s": t_min,
            "early_min_mV": v_min,
            "sustained_mV": v_sustained,
            "t50_refined_s": t50,
            "t90_refined_s": t90,
            "recovery_half_s": recovery_half,
            "UV_AUC_mV_s": auc,
        })

    return pd.DataFrame(rows)


# -----------------------------
# Figure generation
# -----------------------------
def make_figures(myel, agar):
    # Figure 1: protocol
    fig = plt.figure(figsize=(10, 4.8))
    ax = fig.add_subplot(111)
    ax.axis("off")

    ax.plot([0, 510], [0, 0], linewidth=1.5)
    segments = [
        (0, 90, "Baseline\nDark"),
        (90, 150, "UV ON\n60 s"),
        (150, 330, "Recovery\n180 s"),
        (330, 390, "UV ON\n60 s"),
        (390, 510, "Recovery\n120 s*"),
    ]
    for a, b, label in segments:
        ax.plot([a, b], [0, 0], linewidth=12, solid_capstyle="butt")
        ax.text((a+b)/2, 0.18, label, ha="center", va="bottom", fontsize=11)

    for x, lab in [(0, "0"), (90, "90 s"), (150, "150 s"),
                   (330, "330 s"), (390, "390 s")]:
        ax.text(x, -0.22, lab, ha="center")

    ax.set_xlim(-10, 520)
    ax.set_ylim(-0.45, 0.55)
    ax.set_title("Experimental stimulation protocol", fontsize=14)
    ax.text(
        510, -0.38,
        "*schematic; final cycle has incomplete recovery in the recordings",
        ha="right", fontsize=8
    )
    fig.tight_layout()
    fig.savefig(FIG / "Figure_1_experimental_protocol.png", dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    # Figure 2: phase-aligned median
    fig = plt.figure(figsize=(10, 5.5))
    ax = fig.add_subplot(111)
    for label, (t, arr, ids) in myel.items():
        med = np.median(arr, axis=0)
        q25 = np.percentile(arr, 25, axis=0)
        q75 = np.percentile(arr, 75, axis=0)
        ax.fill_between(t, q25, q75, alpha=0.12)
        ax.plot(t, med, linewidth=2, label=label)

    if agar[0] is not None:
        t, arr, ids = agar
        ax.plot(t, np.median(arr, axis=0), linewidth=1.7,
                label="Agar control")

    ax.axvspan(0, 60, alpha=0.10, label="UV ON")
    ax.axhline(0, linewidth=0.8)
    ax.set_xlim(-30, 180)
    ax.set_xlabel("Time relative to UV ON (s)")
    ax.set_ylabel("ΔV relative to pre-UV baseline (mV)")
    ax.set_title("Cycle-aligned extracellular voltage response")
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "Figure_2_cycle_aligned_response.png", dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    # Figure 3: kinetic descriptors
    descriptors = [
        ("Amax_mV", "Maximum response, Amax (mV)",
         "UV response amplitude", "Figure_3_Amax_mV.png"),
        ("t50_refined_s", "t50 after early minimum (s)",
         "Response kinetics", "Figure_3_t50_refined_s.png"),
        ("recovery_half_s", "Recovery half-time (s)",
         "Post-UV recovery", "Figure_3_recovery_half_s.png"),
        ("UV_AUC_mV_s", "UV response AUC (mV·s)",
         "Integrated UV response", "Figure_3_UV_AUC_mV_s.png"),
    ]

    for col, ylabel, title, fname in descriptors:
        fig = plt.figure(figsize=(9.5, 4.6))
        ax = fig.add_subplot(111)
        for label in ["No weight", "Weight 1", "Weight 2"]:
            d = all_kin[all_kin.Condition == label]
            ax.plot(d.Cycle, d[col], "o-", ms=3, linewidth=1.1, label=label)
        ax.set_xlabel("UV cycle")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(alpha=0.2)
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG / fname, dpi=300, bbox_inches="tight")
        plt.close(fig)

    # Figure 4: heatmaps
    for label, (t, arr, ids) in myel.items():
        fig = plt.figure(figsize=(10, 5.6))
        ax = fig.add_subplot(111)
        im = ax.imshow(
            arr, aspect="auto", origin="upper",
            extent=[t[0], t[-1], len(ids)+0.5, 0.5],
            interpolation="nearest"
        )
        ax.axvspan(0, 60, alpha=0.10)
        ax.set_xlabel("Time relative to UV ON (s)")
        ax.set_ylabel("UV cycle")
        ax.set_title(f"{label}: cycle-by-cycle response")
        cb = fig.colorbar(im, ax=ax)
        cb.set_label("ΔV (mV)")
        fig.tight_layout()
        fname = f"Figure_4_heatmap_{label.replace(' ', '_')}.png"
        fig.savefig(FIG / fname, dpi=300, bbox_inches="tight")
        plt.close(fig)


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    myel = {}
    for label in ["No weight", "Weight 1", "Weight 2"]:
        t, arr, ids = aligned_cycles(FILES[label], 30, POST)
        myel[label] = (t, arr, ids)

    # Agar is short; only the available cycles are used.
    agar = aligned_cycles(FILES["Agar control"], 2, 80)

    all_tables = []
    for label, (t, arr, ids) in myel.items():
        all_tables.append(cycle_metrics(t, arr, ids, label))
    all_kin = pd.concat(all_tables, ignore_index=True)

    make_figures(myel, agar)

    summary = all_kin.groupby("Condition").agg(
        n=("Cycle", "count"),
        Amax_mean=("Amax_mV", "mean"),
        Amax_median=("Amax_mV", "median"),
        Amax_sd=("Amax_mV", "std"),
        t50_mean=("t50_refined_s", "mean"),
        t50_median=("t50_refined_s", "median"),
        t50_sd=("t50_refined_s", "std"),
        recovery_half_mean=("recovery_half_s", "mean"),
        recovery_half_median=("recovery_half_s", "median"),
        recovery_half_sd=("recovery_half_s", "std"),
        AUC_mean=("UV_AUC_mV_s", "mean"),
        AUC_median=("UV_AUC_mV_s", "median"),
    ).reset_index()

    all_kin.to_csv(RESULTS / "cycle_kinetics_refined.csv", index=False)
    summary.to_csv(RESULTS / "kinetics_summary_refined.csv", index=False)

    # LaTeX table for direct inclusion.
    tex_table = summary[[
        "Condition", "n", "Amax_mean", "Amax_sd",
        "t50_mean", "t50_sd",
        "recovery_half_mean", "recovery_half_sd",
        "AUC_mean"
    ]].copy()

    tex_table.columns = [
        "Condition", "$n$", "$A_{\\max}$ (mV)",
        "SD", "$t_{50}$ (s)", "SD",
        "$t_{1/2,\\mathrm{rec}}$ (s)", "SD",
        "AUC (mV s)"
    ]

    tex = tex_table.to_latex(
        index=False,
        escape=False,
        float_format=lambda x: f"{x:.3f}",
        column_format="lrrrrrrrr"
    )
    (RESULTS / "kinetics_summary_table.tex").write_text(tex)

    print("Analysis complete.")
    print(f"Figures: {FIG}")
    print(f"Results: {RESULTS}")
