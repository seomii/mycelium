import time
import numpy as np
import matplotlib.pyplot as plt
from sys import platform, path
from os import sep
from ctypes import *

# 1. Load the Digilent WaveForms SDK
if platform.startswith("win"):
    dwf = cdll.dwf
    constants_path = "C:" + sep + "Program Files (x86)" + sep + "Digilent" + sep + "WaveFormsSDK" + sep + "samples" + sep + "py"
elif platform.startswith("darwin"):
    lib_path = sep + "Library" + sep + "Frameworks" + sep + "dwf.framework" + sep + "dwf"
    dwf = cdll.LoadLibrary(lib_path)
    constants_path = sep + "Applications" + sep + "WaveForms.app" + sep + "Contents" + sep + "Resources" + sep + "SDK" + sep + "samples" + sep + "py"
else:
    dwf = cdll.LoadLibrary("libdwf.so")
    constants_path = sep + "usr" + sep + "share" + sep + "digilent" + sep + "waveforms" + sep + "samples" + sep + "py"

path.append(constants_path)

from dwfconstants import *

def check_error():
    err_msg = create_string_buffer(512)
    dwf.FDwfGetLastErrorMsg(err_msg)
    err_msg = err_msg.value.decode("ascii")
    if err_msg != "":
        raise Exception(f"DWF Error: {err_msg}")

def main():
    hdwf = c_int()
    
    # 2. Connect to the Analog Discovery Pro
    print("Opening first available device...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == hdwfNone.value:
        check_error()
        return

    print(f"Device opened. Handle: {hdwf.value}")

    try:
        # --- TEST SETTINGS (10 Hz Sampling Rate) ---
        hzAcq = 10.0              # 10 measurements per second
        record_time = 30.0        # Record for 30 seconds total
        nSamples = int(hzAcq * record_time)  # Total of 300 samples
        
        pulse_frequency = 0.05    # Very slow wave (1 full cycle takes 20 seconds)
        pulse_duration = 10.0     # Turn the UV light ON for exactly 10 seconds
        
        # --- CONFIGURE ANALOG OUT (The UV Light Pulse) ---
        print("Configuring UV Pulse (Analog Out CH1)...")
        channel_out = c_int(0) 
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, channel_out, AnalogOutNodeCarrier, c_int(1))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, channel_out, AnalogOutNodeCarrier, funcSquare)
        dwf.FDwfAnalogOutNodeFrequencySet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(pulse_frequency))
        dwf.FDwfAnalogOutNodeAmplitudeSet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(2.5)) 
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(2.5))    
        dwf.FDwfAnalogOutRunSet(hdwf, channel_out, c_double(pulse_duration)) # Runs for 10 seconds
        dwf.FDwfAnalogOutRepeatSet(hdwf, channel_out, c_int(1))              # Fires only once
        
        # --- CONFIGURE ANALOG IN (The Recording Scope) ---
        print("Configuring Recording (Analog In CH1 & CH2)...")
        # Enable CH1 (Verify Pulse) and CH2 (Electrode Data)
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_int(1)) # CH1
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_int(1)) # CH2
        
        # Set ranges (e.g., 5V range to easily capture the UV pulse and small electrode signals)
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        
        # Set Sample Rate and Buffer
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeSingle)
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(hzAcq))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(nSamples))
        
        # Set Trigger: Tell the recording to start exactly when Analog Out 1 fires
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcAnalogOut1)
        dwf.FDwfAnalogInTriggerPositionSet(hdwf, c_double(record_time / 2.0)) # Position trigger at the start of the buffer
        
        time.sleep(2) # Give the DAQ circuits a moment to stabilize

        # --- EXECUTE TEST ---
        print("Starting Acquisition and firing UV Pulse...")
        dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(1))    # Start the Scope (it will wait for the trigger)
        dwf.FDwfAnalogOutConfigure(hdwf, channel_out, c_int(1)) # Fire the Pulse (this triggers the scope)

        # --- WAIT FOR DATA ---
        status = c_byte()
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(status))
            if status.value == DwfStateDone.value:
                break
            time.sleep(0.1)

        print("Acquisition complete. Downloading data...")

        # --- RETRIEVE DATA ---
        rgdSamples1 = (c_double * nSamples)() # Buffer for CH1 (Pulse verification)
        rgdSamples2 = (c_double * nSamples)() # Buffer for CH2 (Electrode response)
        
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), rgdSamples1, nSamples)
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), rgdSamples2, nSamples)

        data_ch1 = np.array(rgdSamples1)
        data_ch2 = np.array(rgdSamples2)

        # --- SAVE DATA ---
        print("Saving data to disk...")
        np.save("uv_pulse_verification.npy", data_ch1)
        np.save("mycelium_electrode_response.npy", data_ch2)

        # --- PLOT DATA ---
        time_axis = np.linspace(0, record_time, nSamples)
        plt.figure(figsize=(10, 6))
        plt.plot(time_axis, data_ch1, label="UV Light Pulse (CH1)", color='orange')
        plt.plot(time_axis, data_ch2, label="Mycelium Response (CH2)", color='green')
        plt.xlabel("Time (s)")
        plt.ylabel("Voltage (V)")
        plt.title("Mycelium UV Excitation Response")
        plt.legend()
        plt.grid(True)
        plt.show()

    finally:
        # 3. Always close the device safely
        print("Closing device...")
        dwf.FDwfDeviceCloseAll()

if __name__ == "__main__":
    main()