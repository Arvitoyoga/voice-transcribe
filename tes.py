import sounddevice as sd
import numpy as np
import keyboard
import time
from resemblyzer import VoiceEncoder
from scipy import signal

TARGET_RATE = 16000  
CHANNELS = 1

def get_device_samplerate():
    """Queries the default input device to find its native sample rate."""
    try:
        device_info = sd.query_devices(kind='input')
        rate = int(device_info['default_samplerate'])
        print(f"Microphone Native Rate: {rate} Hz")
        return rate
    except Exception as e:
        print(f"Could not query device: {e}")
        return 44100 

NATIVE_RATE = get_device_samplerate()

def record_while_pressed(key='space'):
    """
    Records at NATIVE_RATE while key is held, then resamples to 16k.
    """
    print(f"Hold '{key.upper()}' to speak...", end="\r")
    
    keyboard.wait(key)
    print(f"Recording... (Release '{key.upper()}' to stop)   ", end="\r")
    
    recording = []
    
    def callback(indata, frames, time, status):
        recording.append(indata.copy())

    stream = sd.InputStream(samplerate=NATIVE_RATE, channels=CHANNELS, callback=callback)
    with stream:
        while keyboard.is_pressed(key):
            time.sleep(0.01)
            
    if len(recording) == 0:
        return np.array([])
        
    audio_native = np.concatenate(recording, axis=0)
    audio_native = np.squeeze(audio_native)
    

    num_samples = int(len(audio_native) * TARGET_RATE / NATIVE_RATE)
    audio_16k = signal.resample(audio_native, num_samples)
    
    return audio_16k


print("Loading Resemblyzer model...")
encoder = VoiceEncoder()
print("Model loaded.\n")

print("-" * 50)
print("STEP 1: ENROLLMENT")
print("Please record a reference clip (5-10 seconds is best).")
print("Hold SPACE, speak a full sentence, then release.")
print("-" * 50)

ref_wav = record_while_pressed('space')
print("\nProcessing reference audio...")

ref_embed = encoder.embed_utterance(ref_wav)
print("Reference voice enrolled!\n")


print("-" * 50)
print("STEP 2: TESTING (Push-to-Talk)")
print("Hold SPACE to say a word.")
print("Press 'q' to quit.")
print("-" * 50)

while True:
    if keyboard.is_pressed('q'):
        print("\nExiting...")
        break
        
    if keyboard.is_pressed('space'):
        candidate_wav = record_while_pressed('space')
        
        # Check length (0.5 seconds @ 16k is 8000 samples)
        if len(candidate_wav) < 8000:
            print("\n[!] Audio too short. Hold the key longer.\n")
            time.sleep(0.5)
            continue
            
        candidate_embed = encoder.embed_utterance(candidate_wav)
        score = np.dot(ref_embed, candidate_embed)
        
        status = "MATCH" if score > 0.75 else "NO MATCH"
        color = "\033[92m" if score > 0.75 else "\033[91m"
        reset = "\033[0m"
        
        print(f"\nSimilarity: {score:.3f} -> {color}{status}{reset}")
        print("Ready for next attempt...\n")
        
    time.sleep(0.05)