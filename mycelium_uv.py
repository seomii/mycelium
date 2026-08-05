import time
import sys
from ctypes import *
import numpy as np
import matplotlib.pyplot as plt

# Load WaveForms DLL
if sys.platform.startswith("win"):
    dwf = cdll.dwf
elif sys.platform.startswith("darwin"):
    dwf = cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
else:
    dwf = cdll.LoadLibrary("libdwf.so")


# C-Type Prototypes
dwf.FDwfDeviceOpen.argtypes = [c_int, POINTER(c_int)]
dwf.FDwfDeviceOpen.restype = c_int

dwf.FDwfDeviceClose.argtypes = [c_int]
dwf.FDwfDeviceClose.restype = c_int

dwf.FDwfDeviceAutoConfigureSet.argtypes = [c_int, c_int]
dwf.FDwfDeviceAutoConfigureSet.restype = c_int

dwf.FDwfDigitalIOOutputEnableSet.argtypes = [c_int, c_uint]
dwf.FDwfDigitalIOOutputEnableSet.restype = c_int

dwf.FDwfDigitalIOOutputSet.argtypes = [c_int, c_uint]
dwf.FDwfDigitalIOOutputSet.restype = c_int

dwf.FDwfDigitalIOConfigure.argtypes = [c_int]
dwf.FDwfDigitalIOConfigure.restype = c_int

# Oscilloscope Engine Prototypes
dwf.FDwfAnalogInReset.argtypes = [c_int]
dwf.FDwfAnalogInReset.restype = c_int

dwf.FDwfAnalogInChannelEnableSet.argtypes = [c_int, c_int, c_int]
dwf.FDwfAnalogInChannelRangeSet.argtypes = [c_int, c_int, c_double]
dwf.FDwfAnalogInChannelOffsetSet.argtypes = [c_int, c_int, c_double]
dwf.FDwfAnalogInFrequencySet.argtypes = [c_int, c_double]
dwf.FDwfAnalogInAcquisitionModeSet.argtypes = [c_int, c_int]
dwf.FDwfAnalogInRecordLengthSet.argtypes = [c_int, c_double]
dwf.FDwfAnalogInConfigure.argtypes = [c_int, c_int, c_int]
dwf.FDwfAnalogInStatus.argtypes = [c_int, c_int, POINTER(c_ubyte)]
dwf.FDwfAnalogInStatusRecord.argtypes = [c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int)]
dwf.FDwfAnalogInStatusData.argtypes = [c_int, c_int, POINTER(c_double), c_int]

dwf.FDwfGetLastErrorMsg.argtypes = [c_char_p]
dwf.FDwfGetLastErrorMsg.restype = c_int

# Experimental Parameters

NUM_CYCLES                  = 30      # Total number of UV ON/OFF cycles
PRE_UV_DURATION_SEC         = 90.0    # Baseline time before the 1st pulse (s)
UV_ON_DURATION_SEC          = 60.0    # Duration light stays ON per cycle (s)
CYCLE_INTERVAL_SEC          = 180.0   # Pause/recovery time between pulses (3 mins)
POST_EXPERIMENT_DURATION_SEC= 90.0    # Final recovery baseline after last pulse (s)

SAMPLE_RATE_HZ              = 100.0   # 100 Hz sampling rate
VOLTAGE_RANGE_V             = 0.25    # ± 250mV range

AUTOSAVE_INTERVAL_SEC       = 60.0    # Time-based disk autosave frequency (s)

# Channel Mapping
CH_TARGET_INDEX             = 0       # Mycelium Plate (Channel 1)
CH_CONTROL_INDEX            = 2       # Pure Agar Control Plate (Channel 3)

DIO_PIN_MASK                = c_uint(1 << 0)   # DIO 0 (Bit 0)
DIO_ALL_LOW                 = c_uint(0)
ACQTYPE_RECORD              = c_int(3)

# Build cycle timing schedule automatically
UV_CYCLES = []
for i in range(NUM_CYCLES):
    t_on = PRE_UV_DURATION_SEC + i * (UV_ON_DURATION_SEC + CYCLE_INTERVAL_SEC)
    t_off = t_on + UV_ON_DURATION_SEC
    UV_CYCLES.append((t_on, t_off))

TOTAL_DURATION_SEC = UV_CYCLES[-1][1] + POST_EXPERIMENT_DURATION_SEC


# Pulse Trigger Functions 
def send_trigger_pulse(dwf, hdwf):
    """Sends a brief 100ms HIGH pulse on DIO 0 to toggle the UV lamp state."""
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)
    
    # 1. Pulse HIGH (3.3V)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK)
    dwf.FDwfDigitalIOConfigure(hdwf)
    time.sleep(0.1)
    
    # 2. Return to LOW (0V)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)
    time.sleep(0.05)

def uv_toggle_on(dwf, hdwf):
    send_trigger_pulse(dwf, hdwf)

def uv_toggle_off(dwf, hdwf):
    send_trigger_pulse(dwf, hdwf)


# Device & Hardware Initialization

def initialize_device(dwf):
    hdwf = c_int()
    print("Opening Digilent Analog Discovery Pro...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == 0:
        szerr = create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(szerr)
        print(f"Error: {szerr.value.decode()}")
        sys.exit(1)
    print(f"Device opened successfully (handle: {hdwf.value})")
    return hdwf

def configure_dio(dwf, hdwf):
    dwf.FDwfDeviceAutoConfigureSet(hdwf, c_int(1))
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)
    print("DIO 0 initialized (Idle LOW: 0V). Ready for trigger pulses.")

def configure_oscilloscope(dwf, hdwf):
    dwf.FDwfAnalogInReset(hdwf)

    total_samples = int(TOTAL_DURATION_SEC * SAMPLE_RATE_HZ)

    # Configure Target Channel (Index 0 / Channel 1)
    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(CH_TARGET_INDEX), c_int(1))               
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(CH_TARGET_INDEX), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(CH_TARGET_INDEX), c_double(0.0))

    # Configure Control Channel (Index 2 / Channel 3)
    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(CH_CONTROL_INDEX), c_int(1))               
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(CH_CONTROL_INDEX), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(CH_CONTROL_INDEX), c_double(0.0))

    dwf.FDwfAnalogInFrequencySet(hdwf,      c_double(SAMPLE_RATE_HZ))
    dwf.FDwfAnalogInAcquisitionModeSet(hdwf, ACQTYPE_RECORD)
    dwf.FDwfAnalogInRecordLengthSet(hdwf,   c_double(TOTAL_DURATION_SEC))

    print(f"Oscilloscope armed: {SAMPLE_RATE_HZ:.0f} Hz | ±{VOLTAGE_RANGE_V}V | {TOTAL_DURATION_SEC:.0f}s total run time")
    return total_samples


# Data Export & Multi-Cycle Plotting

def save_data_arrays(samples_ch1, samples_ch3, is_autosave=False):
    """Saves raw numpy arrays to disk."""
    ch1_arr = np.array(samples_ch1)
    ch3_arr = np.array(samples_ch3)
    
    np.save("mycelium_ch1.npy", ch1_arr)
    np.save("agar_control_ch3.npy", ch3_arr)
    
    if not is_autosave:
        print("\nData saved successfully:")
        print("  └─ Mycelium Stream:      mycelium_ch1.npy")
        print("  └─ Agar Control Stream:  agar_control_ch3.npy")


# Execution Loop with Periodic Autosave

def run_experiment(dwf, hdwf, total_samples):
    all_samples_ch1 = []
    all_samples_ch3 = []
    
    # Flags to track ON, OFF, and Autosave for each cycle
    cycle_on_done   = [False] * NUM_CYCLES
    cycle_off_done  = [False] * NUM_CYCLES
    
    available   = c_int()
    lost        = c_int()
    corrupt     = c_int()
    sts         = c_ubyte()

    dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(1))
    time.sleep(1.0)

    t_start = time.time()
    t_last_autosave = t_start

    print(f"\nExperiment started → t = 0.0s ({NUM_CYCLES} UV Cycles scheduled)")
    for i, (t_on, t_off) in enumerate(UV_CYCLES):
        print(f"  └─ Cycle {i+1}: ON at {t_on:.1f}s | OFF at {t_off:.1f}s")

    while True:
        elapsed = time.time() - t_start

        # Check and handle pulse events for each cycle
        for i, (t_on, t_off) in enumerate(UV_CYCLES):
            if not cycle_on_done[i] and elapsed >= t_on:
                uv_toggle_on(dwf, hdwf)
                cycle_on_done[i] = True
                print(f"\n>>> SENT ON PULSE (Cycle {i+1}/{NUM_CYCLES}) → t = {elapsed:.1f}s (UV Light ON) <<<")

            if cycle_on_done[i] and not cycle_off_done[i] and elapsed >= t_off:
                uv_toggle_off(dwf, hdwf)
                cycle_off_done[i] = True
                print(f"\n>>> SENT OFF PULSE (Cycle {i+1}/{NUM_CYCLES}) → t = {elapsed:.1f}s (UV Light OFF) <<<")
                
                # Autosave immediately after every cycle completes
                if len(all_samples_ch1) > 0:
                    save_data_arrays(all_samples_ch1, all_samples_ch3, is_autosave=True)
                    print(f"  [Disk Autosave] Saved Cycle {i+1} data ({len(all_samples_ch1)} samples)")

        # Stream Oscilloscope Buffer
        dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
        dwf.FDwfAnalogInStatusRecord(hdwf, byref(available), byref(lost), byref(corrupt))

        if available.value > 0:
            chunk1 = (c_double * available.value)()
            chunk3 = (c_double * available.value)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(CH_TARGET_INDEX), chunk1, c_int(available.value))
            dwf.FDwfAnalogInStatusData(hdwf, c_int(CH_CONTROL_INDEX), chunk3, c_int(available.value))
            all_samples_ch1.extend(chunk1)
            all_samples_ch3.extend(chunk3)

        # Periodic time-based autosave (e.g. every 60 seconds)
        if (time.time() - t_last_autosave) >= AUTOSAVE_INTERVAL_SEC:
            if len(all_samples_ch1) > 0:
                save_data_arrays(all_samples_ch1, all_samples_ch3, is_autosave=True)
            t_last_autosave = time.time()

        # Check if UV light is currently active
        is_uv_active = any(cycle_on_done[i] and not cycle_off_done[i] for i in range(NUM_CYCLES))
        phase = "ON" if is_uv_active else "OFF"
        
        print(f"  t={elapsed:6.1f}s | samples={len(all_samples_ch1):6d}/{total_samples} | UV State={phase}  ", end="\r")

        if elapsed >= TOTAL_DURATION_SEC:
            break

        time.sleep(0.005)

    print(f"\nData collection complete. {len(all_samples_ch1)} samples collected per channel.")
    return np.array(all_samples_ch1), np.array(all_samples_ch3)


def plot_results(samples_ch1, samples_ch3):
    n = min(len(samples_ch1), len(samples_ch3))
    time_axis = np.arange(n) / SAMPLE_RATE_HZ

    # Convert Volts (V) to Millivolts (mV)
    ch1_mv = samples_ch1[:n] * 1000.0
    ch3_mv = samples_ch3[:n] * 1000.0

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    labels = ['Channel 1 — Mycelium Response', 'Channel 3 — Pure Agar Control']
    colors = ['#1f77b4', '#ff7f0e']

    for ax, samples, label, color in zip(axes, [ch1_mv, ch3_mv], labels, colors):
        # Draw shaded spans and markers for all UV stimulation cycles
        for i, (t_on, t_off) in enumerate(UV_CYCLES):
            span_label = f'UV Exposure ({UV_ON_DURATION_SEC:.0f}s)' if i == 0 else None
            on_label   = 'UV ON Pulse' if i == 0 else None
            off_label  = 'UV OFF Pulse' if i == 0 else None

            ax.axvspan(t_on, t_off, color='violet', alpha=0.2, label=span_label)
            ax.axvline(t_on, color='purple', linestyle='--', linewidth=1.2, label=on_label)
            ax.axvline(t_off, color='purple', linestyle=':', linewidth=1.2, label=off_label)

        ax.plot(time_axis, samples, color=color, linewidth=0.8, label=label)
        ax.set_ylabel('Voltage (mV)', fontsize=11)
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, alpha=0.3)

    axes[0].set_title(f'Mycelium Multi-Cycle UV Response ({NUM_CYCLES} Cycles)', fontsize=13)
    axes[-1].set_xlabel('Time (s)', fontsize=11)
    axes[-1].set_xlim(0, TOTAL_DURATION_SEC)

    plt.tight_layout()
    plt.savefig('mycelium_uv_response.png', dpi=150)
    print("Plot saved to mycelium_uv_response.png")
    plt.show()


# Execution Block

if __name__ == "__main__":
    hdwf = initialize_device(dwf)
    samples_ch1, samples_ch3 = [], []

    try:
        configure_dio(dwf, hdwf)
        total_samples = configure_oscilloscope(dwf, hdwf)
        
        # 1. Collect Data
        samples_ch1, samples_ch3 = run_experiment(dwf, hdwf, total_samples)
        
        # 2. Final Save
        save_data_arrays(samples_ch1, samples_ch3)
        
        # 3. Plot & Save Graph
        plot_results(samples_ch1, samples_ch3)

    except KeyboardInterrupt:
        print("\n\nScript interrupted by user.")
        if len(samples_ch1) > 0:
            print("Saving partial data to disk before exit...")
            save_data_arrays(samples_ch1, samples_ch3, is_autosave=True)

    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        if len(samples_ch1) > 0:
            print("Emergency autosave executed...")
            save_data_arrays(samples_ch1, samples_ch3, is_autosave=True)

    finally:
        print("\nExecuting safe teardown...")
        dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(0))  # Stop scope
        dwf.FDwfDeviceClose(hdwf)                            # Release hardware handle
        print("Hardware closed safely.")