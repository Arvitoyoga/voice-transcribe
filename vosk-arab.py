#NOT USED

import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
import time
import serial
import wave

# --- LIBRARIES FOR PROPER TERMINAL DISPLAY ---
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print("Please run: pip install arabic-reshaper python-bidi")
    sys.exit()

USE_MIC = True  
WAV_FILE_PATH = "dataset/tes-noise-drone-lab2.wav" 
USE_SERIAL = False
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600

# ARABIC MODEL
MODEL = "vosk-model-ar-mgb2-0.4"
model_path = "model/" + MODEL 
SAMPLE_RATE = 16000

# --- MAPPING ENGLISH SOUNDS TO ARABIC SCRIPT ---
# The model doesn't know "Payload", but it knows "Bayload" written in Arabic.
COMMAND_MAP = {
    'بايلود': 'payload',   # Phonetic: Bay-lood
    'كاميرا': 'camera',    # Phonetic: Ka-me-ra
    'سويتش': 'switch',     # Phonetic: Swit-ch
    'أهلا': 'hello'        # Ahlan (Normalized)
}

# Phonetic Keys
KEY_MAP = {
    'بابا': 'papa',        # Baba
    'شارلي': 'charlie',    # Shar-lee
    'سييرا': 'sierra'      # See-ye-ra
}

# Create lists for Vosk Grammar
COMMAND_AR = list(COMMAND_MAP.keys())
KEY_AR = list(KEY_MAP.keys())

buffer = {"cmd": None, "key": None}
buf_time = [0.0]

# Add [unk] to grammar
grammar_json = json.dumps(COMMAND_AR + KEY_AR + ["[unk]"]) 

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}")
    sys.exit()

model = Model(model_path)
rec = KaldiRecognizer(model, SAMPLE_RATE)
q = queue.Queue()

def fix_text(text):
    """Reshapes Arabic text to look correct in terminals"""
    reshaped_text = arabic_reshaper.reshape(text)    # Connect letters
    bidi_text = get_display(reshaped_text)           # Fix direction (Right-to-Left)
    return bidi_text

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

def send_serial(ser, command, key):
    if not USE_SERIAL or ser is None:
        return
    # Map back to English logic for ID generation if needed
    eng_cmd = COMMAND_MAP.get(command, "unknown")
    eng_key = KEY_AR.get(key, "unknown")
    print(f"Sending: {eng_cmd} {eng_key}")
    # ... your serial logic here ...

def run():
    ser = None
    if USE_SERIAL:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
        except:
            pass

    state = {'last_time': 0}

    def process_data(data):
        # Buffer Timeout Logic
        if buffer['cmd'] and not buffer['key']:
            now = time.time()
            if (now - buf_time[0]) > 5.0:
                print("[Buffer] Timeout. Clearing buffer.")
                buffer['cmd'] = None
                buffer['key'] = None
                rec.Reset()

        if rec.AcceptWaveform(data):
            res_json = json.loads(rec.Result())
            current_text = res_json.get("text", "")
        else:
            partial_json = json.loads(rec.PartialResult())
            current_text = partial_json.get("partial", "")

        if not current_text:
            return

        words = current_text.split()
        if not words:
            return
        print(f"\n[Detected Text]: {fix_text(words[0])}")

        # for word in words:
        #     # Skip [unk]
        #     if word == "[unk]":
        #         continue

        #     # Print what we heard (Visually fixed)
        #     print(f"Detected: {fix_text(word)}  (Raw: {word})")

        #     # Check Commands
        #     if word in COMMAND_AR:
        #         if buffer['cmd'] != word:
        #             buffer['cmd'] = word
        #             buffer['key'] = None
        #             buf_time[0] = time.time()
        #             print(f"-> Command Locked: {fix_text(word)} ({COMMAND_MAP[word]})")
            
        #     # Check Keys
        #     elif word in KEY_AR:
        #         if buffer["cmd"] and buffer["key"] is None:
        #             # Here you can implement the specific matching logic
        #             # For now, we accept any key
        #             buffer['key'] = word
        #             print(f"-> Key Locked: {fix_text(word)} ({KEY_MAP[word]})")

        # Execute
        if buffer['cmd'] and buffer['key']:
            cmd_ar = buffer['cmd']
            key_ar = buffer["key"]
            
            # Translate back to English for logging/Serial
            cmd_en = COMMAND_MAP[cmd_ar]
            key_en = KEY_MAP[key_ar]

            print(f"\n[!] EXECUTE: {cmd_en.upper()} - {key_en.upper()}")
            
            # send_serial(ser, cmd_en, key_en) 
            
            buffer["cmd"] = None
            buffer["key"] = None
            buf_time[0] = 0.0
            rec.Reset()
            print("Ready...")
            if USE_MIC:
                with q.mutex:
                    q.queue.clear()

    if USE_MIC:
        print(f"Listening... (Say 'Bay-lood', 'Ka-me-ra', etc)")
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                               channels=1, callback=audio_callback):
            while True:
                data = q.get()
                process_data(data)
    # ... file reading logic ...

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")