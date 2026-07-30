import numpy as np
from scipy.signal import savgol_filter

# 1. Load raw data and convert V -> mV
ch1 = np.load("mycelium_ch1.npy") * 1000.0  
ch3 = np.load("agar_control_ch3.npy") * 1000.0  

SAMPLE_RATE_HZ = 10.0

# 2. Extract a SETTLED region (t = 150s to 180s, between Cycle 1 and Cycle 2)
start_idx = int(150.0 * SAMPLE_RATE_HZ)
end_idx   = int(180.0 * SAMPLE_RATE_HZ)

v_bio_settled = (ch1 - ch3)[start_idx:end_idx]
v_clean_settled = savgol_filter(v_bio_settled, window_length=15, polyorder=2)

# 3. Calculate 1σ and 3σ noise metrics on the settled signal
std_noise_uv = np.std(v_clean_settled) * 1000.0  # mV -> µV
three_sigma_uv = 3 * std_noise_uv

print("=" * 55)
print(f"Settled Noise Floor (1σ)     : {std_noise_uv:.2f} µV")
print(f"True Prominence Threshold (3σ): {three_sigma_uv:.2f} µV")
print("=" * 55)