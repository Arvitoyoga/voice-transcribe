import sys
import wave
import time
from RealtimeSTT import AudioToTextRecorder
import logging


# Audio recording storage
recorded_frames = []

def audio_chunk_callback(chunk):
    """Save audio chunks for later WAV export"""
    recorded_frames.append(chunk)
import time

start_time = None

def process_text(text):
    """Called when speech ends"""
    global start_time
    
    if start_time is None:
        return
    
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    
    command = text.strip().lower()
    if command:
        print(f">>> COMMAND: {command:15} | Latency: {latency_ms:6.1f}ms")
    
    start_time = None

def save_recording(filename="session_record.wav"):
    """Save recorded audio to WAV file"""
    if not recorded_frames:
        print("No audio recorded.")
        return
    
    print(f"\nSaving recording to {filename}...")
    try:
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b''.join(recorded_frames))
        wf.close()
        print("Save successful.")
    except Exception as e:
        print(f"Error saving audio: {e}")

if __name__ == '__main__':
    print("Initializing Command Mode...")
    
    recorder_config = {
        'spinner': False,
        # 'level': logging.DEBUG,
        # 'model':'tiny.en',
        'model': 'deepdml/faster-distil-whisper-large-v3.5',

        # 'model': 'deepdml/faster-whisper-large-v3-turbo-ct2',
        'language': 'en',
        'device': 'cuda',
        'compute_type': 'float16',
        'use_microphone': True,
        
        # VAD Settings - CRITICAL FOR SINGLE WORDS
        'post_speech_silence_duration': 0.3,    # 300ms silence = speech ended
        'min_length_of_recording': 0.2,        # Ignore audio <150ms
        'silero_sensitivity': 0.45,              # Medium sensitivity
        'faster_whisper_vad_filter': True,  # ← Add this
        'initial_prompt':'keyboard',
        # DISABLE realtime transcription (not needed for commands)
        'enable_realtime_transcription': False,
        
        # Audio recording hook
        'on_recorded_chunk': audio_chunk_callback,
    }
    
    try:
        recorder = AudioToTextRecorder(**recorder_config)
        print("\nListening for commands... (Press Ctrl+C to stop)\n")
        
        while True:
            print("Say a word now...", end=' ', flush=True)
            start_time = time.time()
            # This blocks until speech is detected, transcribed
            recorder.text(process_text)
    
    except KeyboardInterrupt:
        print("\nStopping...")
        recorder.shutdown()
        save_recording()
        sys.exit(0)
