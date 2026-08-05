import numpy as np
import matplotlib.pyplot as plt

# -----------------------------------------------------------------------------
# 1. Experimental Parameters (Reconstructed to draw UV timing lines)
# -----------------------------------------------------------------------------
NUM_CYCLES                  = 30       # Total number of UV ON/OFF cycles
PRE_UV_DURATION_SEC         = 90.0     # Baseline time before 1st pulse (s)
UV_ON_DURATION_SEC          = 60.0     # Duration light stays ON per cycle (s)
CYCLE_INTERVAL_SEC          = 180.0    # Pause/recovery time between pulses (s)
POST_EXPERIMENT_DURATION_SEC= 90.0     # Final recovery baseline (s)
SAMPLE_RATE_HZ              = 100.0    # Sampling rate in Hz

# Build cycle timing schedule automatically
UV_CYCLES = []
for i in range(NUM_CYCLES):
    t_on = PRE_UV_DURATION_SEC + i * (UV_ON_DURATION_SEC + CYCLE_INTERVAL_SEC)
    t_off = t_on + UV_ON_DURATION_SEC
    UV_CYCLES.append((t_on, t_off))

TOTAL_DURATION_SEC = UV_CYCLES[-1][1] + POST_EXPERIMENT_DURATION_SEC

# -----------------------------------------------------------------------------
# 2. Load & Crop Data
# -----------------------------------------------------------------------------
ch1_raw = np.load("mycelium_ch1.npy") * 1000.0  # Convert Volts (V) to Millivolts (mV)
ch3_raw = np.load("agar_control_ch3.npy") * 1000.0

n = min(len(ch1_raw), len(ch3_raw))
time_axis = np.arange(n) / SAMPLE_RATE_HZ

# Crop out the first 90 seconds (electrode settling shock)
crop_seconds = 90.0
crop_idx = int(crop_seconds * SAMPLE_RATE_HZ)

time_cropped = time_axis[crop_idx:]
ch1_cropped  = ch1_raw[crop_idx:n]
ch3_cropped  = ch3_raw[crop_idx:n]

# -----------------------------------------------------------------------------
# 3. Plotting (Matching Original Aesthetics & Legends)
# -----------------------------------------------------------------------------
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

labels = ['Channel 1 — Mycelium Response', 'Channel 3 — Pure Agar Control']
colors = ['#1f77b4', '#ff7f0e']
datasets = [ch1_cropped, ch3_cropped]

for ax, samples, label, color in zip(axes, datasets, labels, colors):
    span_added = False
    on_added   = False
    off_added  = False

    # Draw shaded spans and vertical lines for all UV cycles
    for (t_on, t_off) in UV_CYCLES:
        if t_off >= crop_seconds:
            # Add labels only once so legend entries don't duplicate
            span_label = f'UV Exposure ({UV_ON_DURATION_SEC:.0f}s)' if not span_added else None
            on_label   = 'UV ON Pulse' if not on_added else None
            off_label  = 'UV OFF Pulse' if not off_added else None

            ax.axvspan(t_on, t_off, color='violet', alpha=0.2, label=span_label)
            ax.axvline(t_on, color='purple', linestyle='--', linewidth=1.2, label=on_label)
            ax.axvline(t_off, color='purple', linestyle=':', linewidth=1.2, label=off_label)

            if span_label: span_added = True
            if on_label:   on_added = True
            if off_label:  off_added = True

    # Plot the signal trace
    ax.plot(time_cropped, samples, color=color, linewidth=0.8, label=label)
    ax.set_ylabel('Voltage (mV)', fontsize=11)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

# Tightly scale Channel 1 Y-axis around the stabilized baseline (with 10% padding)
ch1_range = np.max(ch1_cropped) - np.min(ch1_cropped)
ch1_padding = max(ch1_range * 0.1, 0.1)  # Ensure minimum visible range
axes[0].set_ylim(np.min(ch1_cropped) - ch1_padding, np.max(ch1_cropped) + ch1_padding)

# Figure Titles & Axis Limits
axes[0].set_title(f'Mycelium Multi-Cycle UV Response ({NUM_CYCLES} Cycles — Cropped)', fontsize=13)
axes[-1].set_xlabel('Time (s)', fontsize=11)
axes[-1].set_xlim(crop_seconds, TOTAL_DURATION_SEC)

plt.tight_layout()
plt.savefig('mycelium_uv_response_cropped.png', dpi=150)
print("Cropped plot saved to mycelium_uv_response_cropped.png")
plt.show()