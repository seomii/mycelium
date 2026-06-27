'''
import time
import numpy as np
import matplotlib.pyplot as plt
from sys import platform, path
from os import sep
from ctypes import *

# Load the Digilent WaveForms SDK
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
    
    # Connect to the Analog Discovery Pro
    print("Opening first available device...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == hdwfNone.value:
        check_error()
        return

    print(f"Device opened. Handle: {hdwf.value}")

    try:
        # --- test settings ---
        hzAcq = 10.0              # 10 measurements per second
        record_time = 120.0        # Record for 120 seconds total
        nSamples = int(hzAcq * record_time)  # Total of 1200 samples
        
        pulse_frequency = 0.05    # Very slow wave (1 full cycle takes 20 seconds)
        pulse_duration = 10.0     # Turn the UV light ON for exactly 10 seconds
        
        # --- configure the Analog Out channel to generate a solid DC voltage for UV excitation ---
        print("Configuring UV Pulse (Analog Out CH1 as a DC Trigger)...")
        channel_out = c_int(0) 
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, channel_out, AnalogOutNodeCarrier, c_int(1))
        
        # FIX 1: Change funcSquare to funcDC for a steady, constant voltage
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, channel_out, AnalogOutNodeCarrier, funcDC)
        
        # FIX 2: Set the Offset to 5.0V. In DC mode, Offset dictates the final output voltage.
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(5.0))    
        
        # Keep these the same: Run for 10 seconds, then stop automatically
        dwf.FDwfAnalogOutRunSet(hdwf, channel_out, c_double(pulse_duration)) 
        dwf.FDwfAnalogOutRepeatSet(hdwf, channel_out, c_int(1))            # UV pulse only once (10 seconds ON then OFF until 300 seconds total)
        
        # --- configure the Analog In channels to record the UV pulse and mycelium response ---
        print("Configuring Recording (Analog In CH1 & CH2)...")
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_int(1)) # CH1
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_int(1)) # CH2
        
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeSingle)
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(hzAcq))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(nSamples))
        
        # FIX: Remove the physical hardware trigger mapping to prevent deadlocks.
        # Instead, we will use a software-driven start command.
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcNone) 
        
        time.sleep(2) # Give the DAQ circuits a moment to stabilize

        # --- Test execution ---
        print("Starting Acquisition and firing UV Pulse simultaneously...")
        
        # We start both the reader and the writer at the exact same moment in software
        dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(1))    # Start the Scope recording
        dwf.FDwfAnalogOutConfigure(hdwf, channel_out, c_int(1)) # Fire the UV Pulse

        # --- Waiting for data ---
        status = c_byte()
        print("Recording in progress... Please wait 2 minutes.") # Updated text
        start_wait = time.time()
        
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(status))
            if status.value == DwfStateDone.value:
                break
            
            # Print a progress update every 10 seconds so you know it hasn't crashed
            elapsed = time.time() - start_wait
            if int(elapsed) % 10 == 0:
                # Updated to dynamically show the actual record_time variable (120)
                print(f"Elapsed recording time: {int(elapsed)} / {int(record_time)} seconds...", end="\r")
                
            time.sleep(1.0)

        # --- retrieving data  ---
        rgdSamples1 = (c_double * nSamples)() 
        rgdSamples2 = (c_double * nSamples)() 
        
        # Now reading Mycelium from CH1 (index 0) and UV Pulse from CH2 (index 1)
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), rgdSamples1, nSamples) # CH1 is Mycelium
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), rgdSamples2, nSamples) # CH2 is UV Pulse

        data_mycelium = np.array(rgdSamples1)
        data_uv_pulse = np.array(rgdSamples2)

        # --- saving data ---
        print("Saving data to disk...")
        np.save("mycelium_electrode_response.npy", data_mycelium)
        np.save("uv_pulse_verification.npy", data_uv_pulse)

        # --- plotting data ---
        time_axis = np.linspace(0, record_time, nSamples)
        plt.figure(figsize=(10, 6))
        plt.plot(time_axis, data_uv_pulse, label="UV Light Pulse (CH2)", color='orange')
        plt.plot(time_axis, data_mycelium, label="Mycelium Response (CH1)", color='green')
        plt.xlabel("Time (s)")
        plt.ylabel("Voltage (V)")
        plt.title("Mycelium UV Excitation Response")
        plt.legend()
        plt.grid(True)
        plt.show()

    finally:
        # Always close the device safely!!!!
        print("Closing device...")
        dwf.FDwfDeviceCloseAll()

if __name__ == "__main__":
    main()
    '''

import time
import numpy as np
import matplotlib.pyplot as plt
from sys import platform, path
from os import sep
from ctypes import *

# Load the Digilent WaveForms SDK
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
    
    print("Opening first available device...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == hdwfNone.value:
        check_error()
        return

    print(f"Device opened. Handle: {hdwf.value}")

    try:
        # --- test settings ---
        hzAcq = 10.0              
        record_time = 120.0        
        nSamples = int(hzAcq * record_time)  
        pulse_duration = 10.0     # Keep UV light ON for exactly 10 seconds
        
        # --- CONFIGURE DIGITAL I/O PIN 0 (DIO 0) FOR UV TRIGGER ---
        print("Configuring Digital I/O Pin 0 (DIO 0)...")
        # Enable output mask for pin 0 (1 << 0 = 1)
        dwf.FDwfDigitalIOOutputEnableSet(hdwf, c_uint(1)) 
        # Set initial state to LOW (0V) so it starts turned OFF
        dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(0)) 
        
        # --- configure the Analog In channels to record ---
        print("Configuring Recording (Analog In CH1 & CH2)...")
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_int(1)) # CH1 is Mycelium
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_int(1)) # CH2 is UV Loopback
        
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeSingle)
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(hzAcq))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(nSamples))
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcNone) 
        
        time.sleep(2) 

        # --- Test execution ---
        print("Starting Acquisition and flipping DIO 0 HIGH (3.3V/5V)...")
        
        # 1. Start the oscilloscope recording
        dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(1))    
        
        # 2. Turn DIO 0 ON instantly (binary bitmask 1 means bit 0 is HIGH)
        dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(1)) 
        dwf.FDwfDigitalIOConfigure(hdwf)

        # --- Waiting for data ---
        status = c_byte()
        print("Recording in progress... Please wait 2 minutes.") 
        start_wait = time.time()
        pulse_turned_off = False
        
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(status))
            if status.value == DwfStateDone.value:
                break
            
            elapsed = time.time() - start_wait
            
            # TIMING CONTROL: Check if 10 seconds have passed to shut off the UV light
            if elapsed >= pulse_duration and not pulse_turned_off:
                print("\n10 seconds passed. Flipping DIO 0 LOW (0V)...")
                dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(0)) # Set all pins back to 0 (LOW)
                dwf.FDwfDigitalIOConfigure(hdwf)
                pulse_turned_off = True

            if int(elapsed) % 10 == 0:
                print(f"Elapsed recording time: {int(elapsed)} / {int(record_time)} seconds...", end="\r")
                
            time.sleep(0.5) # Kept a bit tighter to catch the 10-second mark accurately

        # --- retrieving data  ---
        print("\nAcquisition complete. Downloading data...")
        rgdSamples1 = (c_double * nSamples)() 
        rgdSamples2 = (c_double * nSamples)() 
        
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), rgdSamples1, nSamples) 
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), rgdSamples2, nSamples) 

        data_mycelium = np.array(rgdSamples1)
        data_uv_pulse = np.array(rgdSamples2)

        # --- saving data ---
        print("Saving data to disk...")
        np.save("mycelium_electrode_response.npy", data_mycelium)
        np.save("uv_pulse_verification.npy", data_uv_pulse)

        # --- plotting data ---
        time_axis = np.linspace(0, record_time, nSamples)
        plt.figure(figsize=(10, 6))
        plt.plot(time_axis, data_uv_pulse, label="UV Light Pulse (CH2)", color='orange')
        plt.plot(time_axis, data_mycelium, label="Mycelium Response (CH1)", color='green')
        plt.xlabel("Time (s)")
        plt.ylabel("Voltage (V)")
        plt.title("Mycelium UV Excitation Response")
        plt.legend()
        plt.grid(True)
        plt.show()

    finally:
        print("Closing device safely...")
        # Clean up: Force digital outputs off before leaving
        dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(0))
        dwf.FDwfDigitalIOConfigure(hdwf)
        dwf.FDwfDeviceCloseAll()

if __name__ == "__main__":
    main()