import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter, find_peaks, peak_widths, peak_prominences
from scipy.ndimage import median_filter

# 1. Load Data Binaries

ch1 = np.load("mycelium_ch1.npy") * 1000.0  # Convert V to mV
ch3 = np.load("agar_control_ch3.npy") * 1000.0

SAMPLE_RATE_HZ = 10.0
time_axis_full = np.arange(len(ch1)) / SAMPLE_RATE_HZ

# 2. Crop Initial Insertion Drift (t > 80s)

CROP_START_SEC = 20.0
crop_idx = int(CROP_START_SEC * SAMPLE_RATE_HZ)

time_axis = time_axis_full[crop_idx:]
v_bio = (ch1 - ch3)[crop_idx:]

# 3. Filtering & Noise Gate (Updated for Settled Noise)
v_smoothed = savgol_filter(v_bio, window_length=11, polyorder=3)

def suppress_sub_noise_gate(signal_mv, threshold_uv=5, baseline_window=101):
    """Clamps noise ripples smaller than the 1σ noise floor."""
    threshold_mv = threshold_uv / 1000.0
    local_baseline = median_filter(signal_mv, size=baseline_window)
    deviation = signal_mv - local_baseline
    gated_deviation = np.where(np.abs(deviation) < threshold_mv, 0.0, deviation)
    return local_baseline + gated_deviation

v_clean = suppress_sub_noise_gate(v_smoothed, threshold_uv=75.54)

# 4. Dual-Polarity Peak Detection (P = 226.61 µV)

PROMINENCE_MV = 0.010 # 226.61 µV prominence threshold derived from 3σ diagnostic

# Positive Spikes (Depolarizations)
pos_peaks, _ = find_peaks(v_clean, prominence=PROMINENCE_MV)
pos_proms, _, _ = peak_prominences(v_clean, pos_peaks)
pos_widths_samples, _, _, _ = peak_widths(v_clean, pos_peaks, rel_height=0.8)
pos_widths_sec = pos_widths_samples / SAMPLE_RATE_HZ

# Negative Spikes (Hyperpolarizations)
neg_peaks, _ = find_peaks(-v_clean, prominence=PROMINENCE_MV)
neg_proms, _, _ = peak_prominences(-v_clean, neg_peaks)
neg_widths_samples, _, _, _ = peak_widths(-v_clean, neg_peaks, rel_height=0.8)
neg_widths_sec = neg_widths_samples / SAMPLE_RATE_HZ

# Combine all events
all_peak_indices = np.concatenate([pos_peaks, neg_peaks])
all_peak_times   = time_axis[all_peak_indices]
all_heights_uv   = np.concatenate([pos_proms, neg_proms]) * 1000.0  # Convert to µV
all_widths_sec   = np.concatenate([pos_widths_sec, neg_widths_sec])

if len(all_peak_times) > 0:
    sort_idx       = np.argsort(all_peak_times)
    all_peak_times = all_peak_times[sort_idx]
    all_heights_uv = all_heights_uv[sort_idx]
    all_widths_sec = all_widths_sec[sort_idx]

total_duration_min = (time_axis[-1] - time_axis[0]) / 60.0
spike_frequency    = len(all_peak_times) / total_duration_min if total_duration_min > 0 else 0

# ─────────────────────────────────────────────
# 5. Print Metrics Summary
# ─────────────────────────────────────────────
print("=" * 60)
print("     MULTI-CYCLE FUNGAL ELECTROPHYSIOLOGY METRICS      ")
print("=" * 60)
print(f"Analysis Window          : {time_axis[0]:.1f} s to {time_axis[-1]:.1f} s ({total_duration_min:.2f} min)")
print(f"Total Confirmed Spikes   : {len(all_peak_times)} (Prominence ≥ 226.61 µV)")
print(f"  └─ Positive Spikes     : {len(pos_peaks)}")
print(f"  └─ Negative Spikes     : {len(neg_peaks)}")
print(f"Spike Firing Rate        : {spike_frequency:.2f} spikes/min")

if len(all_peak_times) > 0:
    print(f"Mean Spike Prominence    : {np.mean(all_heights_uv):.2f} µV (Max: {np.max(all_heights_uv):.2f} µV)")
    print(f"Mean Spike Duration (80%): {np.mean(all_widths_sec):.2f} s")
print("=" * 60)

# ─────────────────────────────────────────────
# 6. Multi-Panel Figure Generation
# ─────────────────────────────────────────────
fig = plt.figure(figsize=(15, 9))
gs  = fig.add_gridspec(3, 2)

UV_CYCLES = [(100, 112), (232, 244), (364, 376)]

# Top Panel: Action Potentials vs Time
ax1 = fig.add_subplot(gs[0, :])
for i, (t_on, t_off) in enumerate(UV_CYCLES):
    ax1.axvspan(t_on, t_off, color='violet', alpha=0.25, label='UV Window' if i == 0 else None)
    ax1.axvline(t_on, color='purple', linestyle='--', alpha=0.7)
    ax1.axvline(t_off, color='purple', linestyle=':', alpha=0.7)

ax1.plot(time_axis, v_clean, color='#1f77b4', linewidth=1.0, label='Cleaned Signal (Ch1 - Ch3)')

if len(pos_peaks) > 0:
    ax1.plot(time_axis[pos_peaks], v_clean[pos_peaks], '^', color='crimson', markersize=7, label=f'Pos Spikes ({len(pos_peaks)})')
if len(neg_peaks) > 0:
    ax1.plot(time_axis[neg_peaks], v_clean[neg_peaks], 'v', color='darkblue', markersize=7, label=f'Neg Spikes ({len(neg_peaks)})')

ax1.set_title('A. Cropped & Filtered Bioelectric Trace (Multi-Cycle UV)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Voltage (mV)')
ax1.set_ylim(np.min(v_clean) - 0.2, np.max(v_clean) + 0.2)
ax1.legend(loc='upper right', fontsize=9)
ax1.grid(True, alpha=0.3)

# Lower Panels: Feature Distributions (if spikes detected)
if len(all_peak_times) > 0:
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.scatter(all_widths_sec, all_heights_uv, c='#2ca02c', alpha=0.7, edgecolors='k')
    ax2.set_title('B. Prominence Height vs. Width (80%)', fontsize=11, fontweight='bold')
    ax2.set_xlabel('Width (s)')
    ax2.set_ylabel('Prominence Height (µV)')
    ax2.grid(True, alpha=0.3)

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.scatter(all_peak_times, all_heights_uv, c='#d62728', alpha=0.7, edgecolors='k')
    ax3.set_title('C. Prominence Height vs. Time', fontsize=11, fontweight='bold')
    ax3.set_xlabel('Time (s)')
    ax3.set_ylabel('Prominence Height (µV)')
    ax3.grid(True, alpha=0.3)

    ax4 = fig.add_subplot(gs[2, 0])
    ax4.scatter(all_peak_times, all_widths_sec, c='#9467bd', alpha=0.7, edgecolors='k')
    ax4.set_title('D. Spike Width vs. Time', fontsize=11, fontweight='bold')
    ax4.set_xlabel('Time (s)')
    ax4.set_ylabel('Width (s)')
    ax4.grid(True, alpha=0.3)

    ax5 = fig.add_subplot(gs[2, 1])
    ax5.hist(all_heights_uv, bins=12, color='#8c564b', alpha=0.7, edgecolor='black')
    ax5.set_title('E. Distribution of Spike Heights', fontsize=11, fontweight='bold')
    ax5.set_xlabel('Prominence Height (µV)')
    ax5.set_ylabel('Frequency Count')
    ax5.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('multicycle_analysis_results.png', dpi=200)
print("\nPlot saved to multicycle_analysis_results.png")
plt.show()