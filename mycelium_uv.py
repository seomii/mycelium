'''
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

# --- Configuration ---
UV_ON_DURATION_SEC  = 10.0
TOTAL_DURATION_SEC  = 20.0
SAMPLE_RATE_HZ      = 1000.0   # 1 kHz — adjust if needed
VOLTAGE_RANGE_V     = 5.0      # ±5V oscilloscope range; lower for small signals
DIO_PIN_MASK        = c_uint(1 << 0)   # DIO pin 0
DIO_ALL_LOW         = c_uint(0)

# WaveForms SDK constants
ACQTYPE_RECORD  = c_int(3)
DWF_STATE_DONE  = c_ubyte(2)

# ─────────────────────────────────────────────
# UV helpers — direct DIO control, no relay
# ─────────────────────────────────────────────
def uv_on(dwf, hdwf):
    """DIO 0 HIGH → current flows through UV light → ON."""
    dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(1 << 0))
    dwf.FDwfDigitalIOConfigure(hdwf)

def uv_off(dwf, hdwf):
    """DIO 0 LOW → no current → UV OFF."""
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)

# ─────────────────────────────────────────────
# Device init
# ─────────────────────────────────────────────
def initialize_device(dwf):
    hdwf = c_int()
    print("Opening Digilent Analog Discovery Pro...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == 0:
        szerr = create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(szerr)
        print(f"Error: {szerr.value.decode()}")
        sys.exit(1)
    print(f"Device opened (handle: {hdwf.value})")
    return hdwf

# ─────────────────────────────────────────────
# DIO config — just set pin 0 as output
# ─────────────────────────────────────────────
def configure_dio(dwf, hdwf):
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)  # pin 0 = output
    uv_off(dwf, hdwf)                                      # safe initial state
    print("DIO 0 configured as output. UV OFF.")

# ─────────────────────────────────────────────
# Oscilloscope config — Channel 1 = mycelium
# ─────────────────────────────────────────────
def configure_oscilloscope(dwf, hdwf):
    total_samples = int(TOTAL_DURATION_SEC * SAMPLE_RATE_HZ)

    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(0), c_int(1))               # enable Ch1
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(0), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(0), c_double(0.0))
    dwf.FDwfAnalogInFrequencySet(hdwf,      c_double(SAMPLE_RATE_HZ))
    dwf.FDwfAnalogInAcquisitionModeSet(hdwf, ACQTYPE_RECORD)
    dwf.FDwfAnalogInRecordLengthSet(hdwf,   c_double(TOTAL_DURATION_SEC))

    print(f"Oscilloscope: {SAMPLE_RATE_HZ:.0f} Hz | ±{VOLTAGE_RANGE_V}V | {TOTAL_DURATION_SEC:.0f}s")
    return total_samples

# ─────────────────────────────────────────────
# Main loop — UV trigger + data acquisition
# ─────────────────────────────────────────────
def run_experiment(dwf, hdwf, total_samples):
    all_samples = []
    uv_off_done = False
    available   = c_int()
    lost        = c_int()
    corrupt     = c_int()
    sts         = c_ubyte()

    # Arm oscilloscope
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))
    time.sleep(0.2)  # let it settle before triggering UV

    # Always explicitly start UV ON
    uv_on(dwf, hdwf)
    t_start = time.time()
    print("UV ON  → t = 0.0s")
    print(f"Recording for {TOTAL_DURATION_SEC:.0f}s total...\n")

    # --- BEFORE THE LOOP (Initial Safe State) ---
    # With a pull-up resistor, driving HIGH or letting it float (Z) keeps it OFF
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK) # 3.3V = OFF
    dwf.FDwfDigitalIOConfigure(hdwf)

    # --- START EXPERIMENT (UV ON) ---
    # Drive the pin to Ground (0V) to turn the active-low circuit ON
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)  # 0V = ON
    dwf.FDwfDigitalIOConfigure(hdwf)
    t_start = time.time()

    while True:
        elapsed = time.time() - t_start  

        # ── UV OFF at exactly 10s ──
        if not uv_off_done and elapsed >= UV_ON_DURATION_SEC:
            # Drive it HIGH to turn it off, matching the pull-up resistor
            dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK) # 3.3V = OFF
            dwf.FDwfDigitalIOConfigure(hdwf)
            uv_off_done = True

        # ── Poll oscilloscope ──
        dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
        dwf.FDwfAnalogInStatusRecord(hdwf, byref(available), byref(lost), byref(corrupt))

        if lost.value > 0:
            print(f"\n  WARNING: {lost.value} samples lost.")
        if corrupt.value > 0:
            print(f"\n  WARNING: {corrupt.value} samples corrupted.")

        if available.value > 0:
            chunk = (c_double * available.value)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(0), chunk, c_int(available.value))
            all_samples.extend(chunk)

        print(f"  t={elapsed:6.1f}s | samples={len(all_samples):7d}/{total_samples} "
              f"| UV={'ON ' if not uv_off_done else 'OFF'}", end="\r")

        # ── Exit based on wall clock, NOT oscilloscope status ──
        # (sts == DONE can fire immediately and break the loop too early)
        if elapsed >= TOTAL_DURATION_SEC:
            break

        time.sleep(0.02)

    print(f"\nDone. {len(all_samples)} samples collected.")
    return np.array(all_samples)

# ─────────────────────────────────────────────
# Plot
# ─────────────────────────────────────────────
def plot_results(samples):
    time_axis = np.arange(len(samples)) / SAMPLE_RATE_HZ

    fig, ax = plt.subplots(figsize=(14, 5))

    # Shade UV ON window
    ax.axvspan(0, UV_ON_DURATION_SEC, color='violet', alpha=0.15,
               label=f'UV ON (0 – {UV_ON_DURATION_SEC:.0f}s)')
    ax.axvline(UV_ON_DURATION_SEC, color='purple', linestyle='--',
               linewidth=1.2, label='UV OFF')

    ax.plot(time_axis, samples, color='steelblue', linewidth=0.5,
            label='Ch1 — Mycelium voltage')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Voltage (V)', fontsize=12)
    ax.set_title('Mycelium Electrophysiology — UV Stimulus Response', fontsize=14)
    ax.set_xlim(0, TOTAL_DURATION_SEC)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('mycelium_uv_response.png', dpi=150)
    print("Plot saved → mycelium_uv_response.png")
    plt.show()

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
hdwf = initialize_device(dwf)

try:
    configure_dio(dwf, hdwf)
    total_samples = configure_oscilloscope(dwf, hdwf)
    samples = run_experiment(dwf, hdwf, total_samples)
    plot_results(samples)

except KeyboardInterrupt:
    print("\nInterrupted by user.")

finally:
    print("\nSafety teardown...")
    uv_off(dwf, hdwf)
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(0))  # stop oscilloscope
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)
    dwf.FDwfDeviceClose(hdwf)
    print("Device closed safely.")

'''

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

# --- Configuration ---
UV_ON_DURATION_SEC  = 10.0
TOTAL_DURATION_SEC  = 20.0
SAMPLE_RATE_HZ      = 1000.0   # 1 kHz
VOLTAGE_RANGE_V     = 0.1      # ± 100µV oscilloscope range 
DIO_PIN_MASK        = c_uint(1 << 0)   # DIO pin 0
DIO_ALL_LOW         = c_uint(0)

# WaveForms SDK constants
ACQTYPE_RECORD  = c_int(3)
DWF_STATE_DONE  = c_ubyte(2)

# UV helpers
'''
Background: 

VIO (3.3V) ──── UV (-)
DIO 0      ──── UV (+)

Each DIO pins have internal pull-up resistors. 
It connects each pin to VIO (3.3V) when the pin is not actively driven. 

UV ON:

    VIO (3.3V)
        │
    [pull-up resistor]   ← internal to ADP
        │
    DIO 0 ──── UV (+)
                    │
                UV light
                    │
                UV (-)  ──── VIO = 3.3V 

UV OFF:

    DIO 0 = 3.3V ──── UV (+)
                      │
                   UV light     ← both sides at 3.3V
                      │
    VIO   = 3.3V ──── UV (-)

'''
def uv_on(dwf, hdwf):
    """
    Disables output and forces internal hardware resistors to float (0.5).

    """
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_ALL_LOW)  
    # 0.0 = Pull Down, 1.0 = Pull Up, 0.5 = Float
    if hasattr(dwf, 'FDwfDigitalIOPullSet'):
        dwf.FDwfDigitalIOPullSet(hdwf, DIO_PIN_MASK, c_double(0.5))
    dwf.FDwfDigitalIOConfigure(hdwf)

def uv_off(dwf, hdwf):
    """
    Drives the pin HIGH (3.3V).

    """
    if hasattr(dwf, 'FDwfDigitalIOPullSet'):
        dwf.FDwfDigitalIOPullSet(hdwf, DIO_PIN_MASK, c_double(1.0)) # Pull up to help drive
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK)       
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK) 
    dwf.FDwfDigitalIOConfigure(hdwf)


# Device init
def initialize_device(dwf):
    hdwf = c_int()
    print("Opening Digilent Analog Discovery Pro...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == 0:
        szerr = create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(szerr)
        print(f"Error: {szerr.value.decode()}")
        sys.exit(1)
    print(f"Device opened (handle: {hdwf.value})")
    return hdwf


# DIO config — just set pin 0 as output
def configure_dio(dwf, hdwf):
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)  # pin 0 = output
    uv_off(dwf, hdwf)                                      # safe initial state
    print("DIO 0 configured as output. UV OFF.")


# Oscilloscope config — Channel 1 = mycelium
def configure_oscilloscope(dwf, hdwf):
    total_samples = int(TOTAL_DURATION_SEC * SAMPLE_RATE_HZ)

    dwf.FDwfAnalogInChannelEnableSet(hdwf,  c_int(0), c_int(1))               # enable Ch1
    dwf.FDwfAnalogInChannelRangeSet(hdwf,   c_int(0), c_double(VOLTAGE_RANGE_V))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf,  c_int(0), c_double(0.0))
    dwf.FDwfAnalogInFrequencySet(hdwf,      c_double(SAMPLE_RATE_HZ))
    dwf.FDwfAnalogInAcquisitionModeSet(hdwf, ACQTYPE_RECORD)
    dwf.FDwfAnalogInRecordLengthSet(hdwf,   c_double(TOTAL_DURATION_SEC))

    print(f"Oscilloscope: {SAMPLE_RATE_HZ:.0f} Hz | ±{VOLTAGE_RANGE_V}V | {TOTAL_DURATION_SEC:.0f}s")
    return total_samples


# Main loop — UV trigger + data acquisition
def run_experiment(dwf, hdwf, total_samples):
    all_samples = []
    uv_off_done = False
    available   = c_int()
    lost        = c_int()
    corrupt     = c_int()
    sts         = c_ubyte()

    # Arm oscilloscope
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))
    time.sleep(0.2)  # let it settle before triggering UV

    # Always explicitly start UV ON
    uv_on(dwf, hdwf)
    t_start = time.time()
    print("UV ON  → t = 0.0s")
    print(f"Recording for {TOTAL_DURATION_SEC:.0f}s total...\n")


    # With a pull-up resistor, driving HIGH or letting it float (Z) keeps it OFF
    dwf.FDwfDigitalIOOutputEnableSet(hdwf, DIO_PIN_MASK)
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK) # 3.3V = OFF
    dwf.FDwfDigitalIOConfigure(hdwf)

    # --- START EXPERIMENT (UV ON) ---
    # Drive the pin to Ground (0V) to turn the active-low circuit ON
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)  # 0V = ON
    dwf.FDwfDigitalIOConfigure(hdwf)
    t_start = time.time()

    while True:
        elapsed = time.time() - t_start  

        # ── UV OFF at exactly 10s ──
        if not uv_off_done and elapsed >= UV_ON_DURATION_SEC:
            # Drive it HIGH to turn it off, matching the pull-up resistor
            dwf.FDwfDigitalIOOutputSet(hdwf, DIO_PIN_MASK) # 3.3V = OFF
            dwf.FDwfDigitalIOConfigure(hdwf)
            uv_off_done = True

        # ── Poll oscilloscope ──
        dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
        dwf.FDwfAnalogInStatusRecord(hdwf, byref(available), byref(lost), byref(corrupt))

        if lost.value > 0:
            print(f"\n  WARNING: {lost.value} samples lost.")
        if corrupt.value > 0:
            print(f"\n  WARNING: {corrupt.value} samples corrupted.")

        if available.value > 0:
            chunk = (c_double * available.value)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(0), chunk, c_int(available.value))
            all_samples.extend(chunk)

        print(f"  t={elapsed:6.1f}s | samples={len(all_samples):7d}/{total_samples} "
              f"| UV={'ON ' if not uv_off_done else 'OFF'}", end="\r")

        # ── Exit based on wall clock, NOT oscilloscope status ──
        # (sts == DONE can fire immediately and break the loop too early)
        if elapsed >= TOTAL_DURATION_SEC:
            break

        time.sleep(0.02)

    print(f"\nDone. {len(all_samples)} samples collected.")
    return np.array(all_samples)


# Plot
def plot_results(samples):
    time_axis = np.arange(len(samples)) / SAMPLE_RATE_HZ

    fig, ax = plt.subplots(figsize=(14, 5))

    # Shade UV ON window
    ax.axvspan(0, UV_ON_DURATION_SEC, color='violet', alpha=0.15,
               label=f'UV ON (0 – {UV_ON_DURATION_SEC:.0f}s)')
    ax.axvline(UV_ON_DURATION_SEC, color='purple', linestyle='--',
               linewidth=1.2, label='UV OFF')

    ax.plot(time_axis, samples, color='steelblue', linewidth=0.5,
            label='Ch1 — Mycelium voltage')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Voltage (V)', fontsize=12)
    ax.set_title('Mycelium Electrophysiology — UV Stimulus Response', fontsize=14)
    ax.set_xlim(0, TOTAL_DURATION_SEC)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('mycelium_uv_response.png', dpi=150)
    print("Plot saved → mycelium_uv_response.png")
    plt.show()


# Entry point
hdwf = initialize_device(dwf)

try:
    configure_dio(dwf, hdwf)
    total_samples = configure_oscilloscope(dwf, hdwf)
    samples = run_experiment(dwf, hdwf, total_samples)
    plot_results(samples)

except KeyboardInterrupt:
    print("\nInterrupted by user.")

finally:
    print("\nSafety teardown...")
    uv_off(dwf, hdwf)
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(0))  # stop oscilloscope
    dwf.FDwfDigitalIOOutputSet(hdwf, DIO_ALL_LOW)
    dwf.FDwfDigitalIOConfigure(hdwf)
    dwf.FDwfDeviceClose(hdwf)
    print("Device closed safely.")
