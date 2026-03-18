"""List available audio input devices. Use to find microphone device index for config."""

import pyaudio

p = pyaudio.PyAudio()
print("PyAudio input devices (microphones):\n")
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if dev["maxInputChannels"] > 0:
        print(f"  [{i}] {dev['name']} (in:{dev['maxInputChannels']}, sr:{int(dev['defaultSampleRate'])})")
p.terminate()
