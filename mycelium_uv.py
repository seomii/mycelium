import time
import sys
from ctypes import *
import numpy as np
import matplotlib.pyplot as plt

# --- Load WaveForms DLL ---
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

# Experimental Parameters

PRE_UV_DURATION_SEC  = 100.0   # baseline duration before UV exposure (s) 
UV_ON_DURATION_SEC   = 20.0   # UV exposure time (s)
POST_UV_DURATION_SEC = 200.0   # recovery duration after UV exposure (s)
TOTAL_DURATION_SEC   = PRE_UV_DURATION_SEC + UV_ON_DURATION_SEC + POST_UV_DURATION_SEC

SAMPLE_RATE_HZ       = 10.0   # 10 Hz sampling rate
VOLTAGE_RANGE_V      = 0.1    # ± 100mV range

DIO_PIN_MASK         = c_uint(1 << 0)   # DIO 0 (Bit 0)
DIO_ALL_LOW          = c_uint(0)
ACQTYPE_RECORD       = c_int(3)


# Pulse Trigger Functions (For Latching UV Lamp)

def send_trigger_pulse(dwf, hdwf):
    """Sends a brief 100ms HIGH pulse on DIO 0 to toggle the UV lamp state."""
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)
    
    # 1. Pulse HIGH (3.3V)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK)
    dwf.FDwfDigitalIOConfigure(hdwf)
    time.sleep(0.1)  # 100ms pulse width
    
    # 2. Return to LOW (0V)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)
    time.sleep(0.05)

def uv_toggle_on(dwf, hdwf):
    """Triggers pulse 1 to turn the light ON."""
    send_trigger_pulse(dwf, hdwf)

def uv_toggle_off(dwf, hdwf):
    """Triggers pulse 2 to turn the light OFF."""
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
    total_samples = int(TOTAL_DURATION_SEC * SAMPLE_RATE_HZ)

    # Configure Channel 1 (Index 0)
    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(0), c_int(1))               
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(0), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(0), c_double(0.0))

    # Configure Channel 3 (Index 2)
    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(2), c_int(1))               
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(2), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(2), c_double(0.0))

    dwf.FDwfAnalogInFrequencySet(hdwf,      c_double(SAMPLE_RATE_HZ))
    dwf.FDwfAnalogInAcquisitionModeSet(hdwf, ACQTYPE_RECORD)
    dwf.FDwfAnalogInRecordLengthSet(hdwf,   c_double(TOTAL_DURATION_SEC))

    print(f"Oscilloscope armed: {SAMPLE_RATE_HZ:.0f} Hz | ±{VOLTAGE_RANGE_V}V | {TOTAL_DURATION_SEC:.0f}s recording window")
    return total_samples


# Execution Loop

def run_experiment(dwf, hdwf, total_samples):
    all_samples_ch1 = []
    all_samples_ch3 = []
    
    uv_on_done  = False
    uv_off_done = False
    
    available   = c_int()
    lost        = c_int()
    corrupt     = c_int()
    sts         = c_ubyte()

    # Start Oscilloscope
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))
    time.sleep(0.2)  

    t_start = time.time()
    print(f"\nExperiment started → t = 0.0s (Baseline phase: {PRE_UV_DURATION_SEC:.0f}s, UV OFF)")

    while True:
        elapsed = time.time() - t_start

        # --- Pulse 1: Turn UV ON at 10.0s ---
        if not uv_on_done and elapsed >= PRE_UV_DURATION_SEC:
            uv_toggle_on(dwf, hdwf)
            uv_on_done = True
            print(f"\n>>> SENT ON PULSE → t = {elapsed:.1f}s (UV Light ON) <<<")

        # --- Pulse 2: Turn UV OFF at 20.0s ---
        if uv_on_done and not uv_off_done and elapsed >= (PRE_UV_DURATION_SEC + UV_ON_DURATION_SEC):
            uv_toggle_off(dwf, hdwf)
            uv_off_done = True
            print(f"\n>>> SENT OFF PULSE → t = {elapsed:.1f}s (UV Light OFF) <<<")

        # --- Stream Oscilloscope Buffer ---
        dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
        dwf.FDwfAnalogInStatusRecord(hdwf, byref(available), byref(lost), byref(corrupt))

        if available.value > 0:
            chunk1 = (c_double * available.value)()
            chunk3 = (c_double * available.value)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(0), chunk1, c_int(available.value))
            dwf.FDwfAnalogInStatusData(hdwf, c_int(2), chunk3, c_int(available.value))
            all_samples_ch1.extend(chunk1)
            all_samples_ch3.extend(chunk3)

        phase = "ON" if (uv_on_done and not uv_off_done) else "OFF"
        print(f"  t={elapsed:6.1f}s | samples={len(all_samples_ch1):5d}/{total_samples} | UV State={phase}  ", end="\r")

        if elapsed >= TOTAL_DURATION_SEC:
            break

        time.sleep(0.02)

    print(f"\nData collection complete. {len(all_samples_ch1)} samples collected per channel.")
    return np.array(all_samples_ch1), np.array(all_samples_ch3)


# Plotting

def plot_results(samples_ch1, samples_ch3):
    n = min(len(samples_ch1), len(samples_ch3))
    time_axis = np.arange(n) / SAMPLE_RATE_HZ

    T_UV_ON  = PRE_UV_DURATION_SEC
    T_UV_OFF = PRE_UV_DURATION_SEC + UV_ON_DURATION_SEC

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    labels = ['Channel 1 — Electrode Pair 1', 'Channel 3 — Electrode Pair 2']
    colors = ['#1f77b4', '#ff7f0e']

    for ax, samples, label, color in zip(axes, [samples_ch1[:n], samples_ch3[:n]], labels, colors):
        ax.axvspan(T_UV_ON, T_UV_OFF, color='violet', alpha=0.2, label=f'UV Exposure ({T_UV_ON:.0f}s – {T_UV_OFF:.0f}s)')
        ax.axvline(T_UV_ON, color='purple', linestyle='--', linewidth=1.2, label='UV ON Pulse')
        ax.axvline(T_UV_OFF, color='purple', linestyle=':', linewidth=1.2, label='UV OFF Pulse')
        ax.plot(time_axis, samples, color=color, linewidth=0.8, label=label)
        ax.set_ylabel('Voltage (V)', fontsize=11)
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, alpha=0.3)

    axes[0].set_title('Mycelium Electrophysiology Response to UV Light Pulse', fontsize=13)
    axes[-1].set_xlabel('Time (s)', fontsize=11)
    axes[-1].set_xlim(0, TOTAL_DURATION_SEC)

    plt.tight_layout()
    plt.savefig('mycelium_uv_response.png', dpi=150)
    print("Plot saved to mycelium_uv_response.png")
    plt.show()


# Execution

hdwf = initialize_device(dwf)

try:
    configure_dio(dwf, hdwf)
    total_samples = configure_oscilloscope(dwf, hdwf)
    samples_ch1, samples_ch3 = run_experiment(dwf, hdwf, total_samples)
    plot_results(samples_ch1, samples_ch3)

except KeyboardInterrupt:
    print("\nScript interrupted by user.")

finally:
    print("\nExecuting safe teardown...")
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(0))  # Stop scope
    dwf.FDwfDeviceClose(hdwf)                            # Release hardware handle
    print("Hardware closed safely.")