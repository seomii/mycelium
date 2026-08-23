import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

# 1. LOAD & CROP DATA (Skip initial 200s electrode settling shock)

SAMPLE_RATE_HZ = 100.0
CROP_START_SEC = 90.0

ch1_raw = np.load("mycelium_ch1.npy") * 1000.0  # Convert V to mV
ch3_raw = np.load("agar_control_ch3.npy") * 1000.0

n_samples = min(len(ch1_raw), len(ch3_raw))
time_full = np.arange(n_samples) / SAMPLE_RATE_HZ

crop_idx  = int(CROP_START_SEC * SAMPLE_RATE_HZ)
time_axis = time_full[crop_idx:]
ch1_crop  = ch1_raw[crop_idx:n_samples]
ch3_crop  = ch3_raw[crop_idx:n_samples]

# 2. SAVITZKY-GOLAY FILTER

WINDOW_LENGTH = 101
POLYORDER     = 3

ch1_sg = savgol_filter(ch1_crop, window_length=WINDOW_LENGTH, polyorder=POLYORDER)
ch3_sg = savgol_filter(ch3_crop, window_length=WINDOW_LENGTH, polyorder=POLYORDER)

# Reconstruction of UV cycle timing overlays
NUM_CYCLES         = 30
PRE_UV_START_SEC   = 90.0
UV_ON_SEC          = 60.0
CYCLE_INTERVAL_SEC = 180.0

UV_CYCLES = []
for i in range(NUM_CYCLES):
    t_on = PRE_UV_START_SEC + i * (UV_ON_SEC + CYCLE_INTERVAL_SEC)
    t_off = t_on + UV_ON_SEC
    UV_CYCLES.append((t_on, t_off))

def add_uv_overlays(ax, x_min, x_max):
    """Adds violet shaded regions and boundary lines for active UV cycles."""
    span_added = False
    for t_on, t_off in UV_CYCLES:
        if t_off >= x_min and t_on <= x_max:
            label = 'UV Exposure (60s)' if not span_added else None
            ax.axvspan(t_on, t_off, color='violet', alpha=0.2, label=label)
            ax.axvline(t_on, color='purple', linestyle='--', linewidth=1.0)
            ax.axvline(t_off, color='purple', linestyle=':', linewidth=1.0)
            span_added = True

# 3. FIGURE 1: FULL EXPERIMENT OVERVIEW (POST-SETTLING)

fig1, axes1 = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

# Channel 1 - Mycelium
axes1[0].plot(time_axis, ch1_sg, color='#1f77b4', linewidth=0.8, label='Channel 1 — Mycelium (SG Filtered)')
axes1[0].set_ylabel('Voltage (mV)')
axes1[0].set_title('Step 1: Full Sequence Savitzky-Golay Filtering (Poly 3, Window 11)', fontsize=12, fontweight='bold')
axes1[0].grid(True, alpha=0.3)
add_uv_overlays(axes1[0], time_axis[0], time_axis[-1])
axes1[0].legend(loc='upper right')

# Set tight Y-bounds around cropped Mycelium baseline
ch1_rng = np.max(ch1_sg) - np.min(ch1_sg)
axes1[0].set_ylim(np.min(ch1_sg) - 0.1 * ch1_rng, np.max(ch1_sg) + 0.1 * ch1_rng)

# Channel 3 - Control
axes1[1].plot(time_axis, ch3_sg, color='#ff7f0e', linewidth=0.8, label='Channel 3 — Pure Agar Control (SG Filtered)')
axes1[1].set_ylabel('Voltage (mV)')
axes1[1].set_xlabel('Time (s)')
axes1[1].grid(True, alpha=0.3)
add_uv_overlays(axes1[1], time_axis[0], time_axis[-1])
axes1[1].legend(loc='upper right')

plt.tight_layout()
plt.savefig('step1_savgol_full_overview.png', dpi=200)
print("Full overview saved to step1_savgol_full_overview.png")

# =============================================================================
# 4. FIGURE 2: ZOOMED-IN VIEW (3 FULL UV CYCLES: 800s to 1520s)
# =============================================================================
ZOOM_START_SEC = 800.0
ZOOM_END_SEC   = 1520.0  # Spans 3 complete cycles (Cycles 4, 5, and 6)

zoom_mask = (time_axis >= ZOOM_START_SEC) & (time_axis <= ZOOM_END_SEC)
t_zoom    = time_axis[zoom_mask]
ch1_zoom  = ch1_sg[zoom_mask]
ch3_zoom  = ch3_sg[zoom_mask]

fig2, axes2 = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

# Zoomed Mycelium
axes2[0].plot(t_zoom, ch1_zoom, color='#1f77b4', linewidth=1.0, label='Channel 1 — Mycelium')
axes2[0].set_ylabel('Voltage (mV)')
axes2[0].set_title(f'Step 1 Detail: Zoomed 3-Cycle View ({ZOOM_START_SEC:.0f}s to {ZOOM_END_SEC:.0f}s)', fontsize=12, fontweight='bold')
axes2[0].grid(True, alpha=0.3)
add_uv_overlays(axes2[0], ZOOM_START_SEC, ZOOM_END_SEC)
axes2[0].legend(loc='upper right')

# Tight Y-bounds for zoomed Mycelium trace
z_rng = np.max(ch1_zoom) - np.min(ch1_zoom)
axes2[0].set_ylim(np.min(ch1_zoom) - 0.1 * z_rng, np.max(ch1_zoom) + 0.1 * z_rng)

# Zoomed Control
axes2[1].plot(t_zoom, ch3_zoom, color='#ff7f0e', linewidth=1.0, label='Channel 3 — Pure Agar Control')
axes2[1].set_ylabel('Voltage (mV)')
axes2[1].set_xlabel('Time (s)')
axes2[1].grid(True, alpha=0.3)
add_uv_overlays(axes2[1], ZOOM_START_SEC, ZOOM_END_SEC)
axes2[1].legend(loc='upper right')

# Tight Y-bounds for zoomed Control trace
c_rng = np.max(ch3_zoom) - np.min(ch3_zoom)
axes2[1].set_ylim(np.min(ch3_zoom) - 0.1 * c_rng, np.max(ch3_zoom) + 0.1 * c_rng)

plt.tight_layout()
plt.savefig('step1_savgol_zoomed_3cycles.png', dpi=200)
print("Zoomed 3-cycle view saved to step1_savgol_zoomed_3cycles.png")
plt.show()