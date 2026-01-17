#NOT USED

import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
import time
import serial

# --- CONFIGURATION ---
USE_MIC = True
USE_SERIAL = False 
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600

# JAPANESE MODEL
MODEL = "vosk-model-small-ja-0.22"
model_path = "model/" + MODEL 
SAMPLE_RATE = 16000

# --- THE TRANSLATION LAYER (Katakana -> Latin/English) ---
# Vosk will hear the Key (Left), we convert it to Value (Right)
JP_TO_EN_MAP = {
    # COMMANDS
    'ペイロード': 'payload',   # Pe-i-rō-do
    'カメラ':    'camera',    # Ka-me-ra
    'スイッチ':  'switch',    # Su-i-cchi
    
    # VALUES (Using Phonetic Alphabet in Katakana)
    'アルファ':   'papa',      # A-ru-fa (Mapped to Papa for your logic)
    'チャーリー': 'charlie',   # Chā-rī
    'シエラ':     'sierra',    # Shi-e-ra
    'ブラボー':   'bravo',     # Bu-ra-bō
    'ワン':       'one',       # Wan
    'ツー':       'two'        # Tsū
}

# We define specific lists for logic checking
# But we generate the Grammar from the Japanese Keys
COMMAND_EN = ['payload', 'camera', 'switch']
KEY_EN     = ['papa', 'charlie', 'sierra', 'bravo', 'one', 'two']

# Create the Grammar List using the JAPANESE keys
GRAMMAR_LIST = list(JP_TO_EN_MAP.keys()) + ["[unk]"]
grammar_json = json.dumps(GRAMMAR_LIST) 

# global buffer
buffer = {"cmd": None, "key": None}
buf_time = [0.0]

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}")
    sys.exit()

model = Model(model_path)
rec = KaldiRecognizer(model, SAMPLE_RATE)
q = queue.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

def send_serial(ser, command, key):
    if not USE_SERIAL or ser is None:
        return
    try:
        # We look up the IDs based on the English/Latin translation
        cmd_id = COMMAND_EN.index(command)
        key_id = KEY_EN.index(key) 
        
        header = 0xAA
        checksum = (cmd_id + key_id) & 0xFF
        packet = bytearray([header, cmd_id, key_id, checksum])
        
        ser.write(packet)
        print(f"-> SENT SERIAL: {command} {key}")
    except Exception as e:
        print(f"Serial Error: {e}")

def run():
    buffer = {"cmd": None, "key": None} 

    ser = None
    if USE_SERIAL:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
        except:
            pass

    print(f"Listening in JAPANESE ({SAMPLE_RATE}Hz)...")
    print(f"Say: 'Peiroodo', 'Kamera', 'Suicchi'...")

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                           channels=1, callback=audio_callback):
        while True:
            data = q.get()

            # Buffer Timeout
            if buffer['cmd'] and not buffer['key']:
                if (time.time() - buf_time[0]) > 5.0:
                    print("[Buffer] Timeout. reset.")
                    buffer['cmd'] = None
                    buffer['key'] = None
                    rec.Reset()

            # Vosk Processing
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text_jp = res.get("text", "")
            else:
                partial = json.loads(rec.PartialResult())
                text_jp = partial.get("partial", "")

            if not text_jp:
                continue

            # Split into words (Japanese uses spaces in Vosk output usually)
            words_jp = text_jp.split()

            for word_jp in words_jp:
                if word_jp == "[unk]": continue
                
                # --- TRANSLATE TO LATIN ---
                if word_jp in JP_TO_EN_MAP:
                    word_latin = JP_TO_EN_MAP[word_jp]
                    
                    # Debug Print (Japanese -> Latin)
                    # print(f"Heard: {word_jp} -> {word_latin}")

                    # --- LOGIC (Uses Latin Words) ---
                    if word_latin in COMMAND_EN:
                        if buffer['cmd'] != word_latin:
                            buffer['cmd'] = word_latin
                            buffer['key'] = None
                            buf_time[0] = time.time()
                            print(f"-> CMD: {word_latin.upper()} ({word_jp})")

                    elif word_latin in KEY_EN:
                        if buffer['cmd']:
                            buffer['key'] = word_latin
                            print(f"-> KEY: {word_latin.upper()} ({word_jp})")
                
            # Execute
            if buffer['cmd'] and buffer['key']:
                cmd = buffer['cmd']
                key = buffer['key']
                
                print(f"\n[!] ACTION: {cmd.upper()} - {key.upper()}")
                
                send_serial(ser, cmd, key)
                
                buffer = {"cmd": None, "key": None}
                rec.Reset()
                with q.mutex:
                    q.queue.clear() # Clear audio tail
                print("Ready...")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")