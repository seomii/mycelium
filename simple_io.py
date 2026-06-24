import time
import numpy as np
import matplotlib.pyplot as plt
from sys import platform, path
from ctypes import *

# Path to find dwfconstants 
constants_path = "/Volumes/WaveForms/WaveForms.app/Contents/Resources/SDK/samples/py"
path.append(constants_path)

try:
    from dwfconstants import *
except ImportError: 
    print(f"ERROR: Could not find 'dwfconstants.py' at: {constants_path}")
    print("Please verify that the WaveForms volume is mounted and the path is correct.")
    exit()

lib_path = "/Library/Frameworks/dwf.framework/dwf"
try:
    dwf = cdll.LoadLibrary(lib_path)
except OSError:
    print(f"ERROR: Could not load the DWF library framework at: {lib_path}")
    print("Please make sure the WaveForms Runtime/Application is fully installed on your Mac.")
    exit()

def main():
    hdwf = c_int()
    
    # opening the digilent device 
    print("Opening first available Digilent device...")
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    
    if hdwf.value == hdwfNone.value:
        print("ERROR: No Digilent device detected. Check your USB connection.")
        return

    print(f"Device successfully opened! Handle ID: {hdwf.value}")

    try:
    
        print("Configuring WaveGen CH1 ")
        channel_out = c_int(0) # 0 = WaveGen CH1
        
        # Enable the generator channel
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, channel_out, AnalogOutNodeCarrier, c_int(1))
        # Set waveform type to Square wave
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, channel_out, AnalogOutNodeCarrier, funcSquare)
        # Set frequency to 10 Hz
        dwf.FDwfAnalogOutNodeFrequencySet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(10.0))
        # Set amplitude to 2.5 V (Peak-to-Peak will be 5.0V if offset is 0)
        dwf.FDwfAnalogOutNodeAmplitudeSet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(2.5))
        # Set offset to 2.5V (Swings from 0V to 5V with a 2.5V offset)
        # The resulting boundaries:
        # The High Peak = Offset + {Amplitude = 2.5V + 2.5V 
        # The Low Peak = Offset - Amplitude = 2.5V - 2.5V
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, channel_out, AnalogOutNodeCarrier, c_double(2.5))
        
        # Start the generator hardware
        dwf.FDwfAnalogOutConfigure(hdwf, channel_out, c_int(1))

        # configuring scope channel 1 to read incoming voltages
        print("Configuring Scope CH1 to read incoming voltages...")
        channel_in = c_int(0) # 0 = Scope CH1
        sample_rate = 1000.0   # Sample at 1,000 measurements per second (1 kHz)
        num_samples = 200      # Capture 200 total snapshots (0.2 seconds of data)

        # Enable Scope Channel 1
        dwf.FDwfAnalogInChannelEnableSet(hdwf, channel_in, c_int(1))
        # Set expected voltage range scale (5V total range)
        dwf.FDwfAnalogInChannelRangeSet(hdwf, channel_in, c_double(5.0))
        # Set the sampling frequency
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(sample_rate))
        # Set the internal storage buffer size
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(num_samples))
        # Set acquisition mode to a single buffer shot
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeSingle)
        
        # Start the recording scope
        dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(1))

        # aquire data from the scope until the buffer is full
        print("Waiting for buffer data collection...")
        status = c_byte()
        
        # Loop until the hardware finishes filling up its sample buffer
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(status))
            if status.value == DwfStateDone.value:
                break
            time.sleep(0.01) # Small delay to avoid overloading CPU

        print("Data collection complete. Transferring to laptop...")
        
        # Create a C-compatible array container for the raw floating-point values
        c_samples_buffer = (c_double * num_samples)()
        # Read data from the hardware buffer into our Python script container
        dwf.FDwfAnalogInStatusData(hdwf, channel_in, c_samples_buffer, num_samples)
        
        # Convert the raw C buffer into a standard Python list/Numpy array
        voltages = list(c_samples_buffer)

        # plotting the results. 
        print("Rendering graph...")
        # Build a time array mapping every sample to fractions of a second
        time_axis = [i / sample_rate for i in range(num_samples)]
        
        plt.figure(figsize=(9, 5))
        plt.plot(time_axis, voltages, label="Measured Signal (Scope CH1)", color='blue', linewidth=2)
        plt.xlabel("Time (Seconds)")
        plt.ylabel("Voltage (Volts)")
        plt.title("Analog Discovery Pro - Loopback Test (0V to 5V Square Wave)")
        
        plt.ylim(-0.5, 6.0) 
        
        plt.legend(loc="upper right")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.show()

    finally:
        # SAFE DISCONNECT 
        # This block ALWAYS runs, even if your code crashes halfway through.
        # It ensures your DAQ channels turn off cleanly.
        print("Closing hardware connections safely...")
        dwf.FDwfDeviceCloseAll()
        print("Device disconnected.")

if __name__ == "__main__":
    
    main()