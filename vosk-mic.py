import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
import time
import serial

USE_MIC = True  
USE_SERIAL = True
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

MODEL_PATH = "model/vosk-model-en-us-0.22-lgraph"
SAMPLE_RATE = 16000

AUDIO_BLOCKSIZE = 1000 

ERROR = 0 

ACTION_MAP = {
    "distribute": { "scarlet": 2, "blacky": 3, "fertilizer": 8 },
    "clearance": { "scarlet": 7, "blacky": 9, "fertilizer": 6 },
    "evening": { "scarlet": 4 },
    "selection": { "vehicle": 5 }
}

TRAP_WORDS_LIST = [
    "district", "disturb", "[unk]", "the", "is", "stop"
]

TRAP_WORDS = set(TRAP_WORDS_LIST)

command_words = list(ACTION_MAP.keys())
key_words = []
for cmd in ACTION_MAP:
    key_words.extend(list(ACTION_MAP[cmd].keys()))

grammar_list = command_words + key_words + list(TRAP_WORDS)
grammar_json = json.dumps(grammar_list)

if not os.path.exists(MODEL_PATH):
    print(f"Model not found at {MODEL_PATH}")
    sys.exit()

def send_error(ser):
    if USE_SERIAL:
        send_serial(ser, ERROR)

model = Model(MODEL_PATH)
rec = KaldiRecognizer(model, SAMPLE_RATE, grammar_json)

# Optimasi: Matikan SetWords karena tidak digunakan di logika Anda (.split() sudah cukup)
# Ini menghemat CPU dan mempercepat proses pengenalan
rec.SetWords(False) 

q = queue.Queue()

buffer = {"cmd": None, "key": None}
last_time = 0.0
TIMEOUT_SEC = 5.0

def audio_callback(indata, frames, time, status):
    if status: print(status, file=sys.stderr)
    q.put(bytes(indata))

def send_serial(serial_conn, cmd_id):
    if not USE_SERIAL or serial_conn is None:
        return
    try:
        header = 0xAA
        checksum = (cmd_id) & 0xFF
        packet = bytearray([header, cmd_id, checksum])
        
        serial_conn.write(packet)
        
        # OPTIMASI: flush() memastikan data langsung dikirim ke hardware serial
        serial_conn.flush() 
        
        print(f"-> [SERIAL TX] ID: {cmd_id} | HEX: {packet.hex()}")
    except Exception as e:
        print(f"Serial Error: {e}")

def process_data(data, active_ser):
    global last_time, buffer

    if buffer['cmd'] and (time.time() - last_time > TIMEOUT_SEC):
        print("\n[TIMEOUT] Buffer cleared.")
        buffer['cmd'] = None
        rec.Reset()

    detected_text = ""
    if rec.AcceptWaveform(data):
        res = json.loads(rec.Result())    
        detected_text = res.get("text", "")
    else:
        res = json.loads(rec.PartialResult())
        detected_text = res.get("partial", "")

    if not detected_text: return

    words = detected_text.split()
    
    for word in words:
        # Optimasi: Sekarang menggunakan SET (TRAP_WORDS) yang sudah dibuat di atas
        if word == "[unk]" or word in TRAP_WORDS:
            print(f"[ERR] {word}")
            continue

        if word in ACTION_MAP.keys():
            if buffer["cmd"] != word:
                buffer["cmd"] = word
                last_time = time.time()
                valid_options = list(ACTION_MAP[word].keys())
                print(f"[CMD] {word.upper()} -> WAITING FOR: {valid_options}")

        elif word in key_words:
            if buffer["cmd"] is None:
                print(f"[ERR] Ignored key '{word}' (No command armed)")
                return 

            valid_keys_map = ACTION_MAP[buffer["cmd"]] 

            if word in valid_keys_map:
                serial_id = valid_keys_map[word]
                print(f"[KEY] {word.upper()} ACCEPTED!")
                print(f"!!! EXECUTING: {buffer['cmd'].upper()} {word.upper()} (ID: {serial_id}) !!!")
                
                send_serial(active_ser, serial_id)
                
                buffer["cmd"] = None
                rec.Reset()
                if USE_MIC:
                    with q.mutex: q.queue.clear()
                return
            
            else:
                print(f"[ERR] Key '{word}' invalid for command '{buffer['cmd']}'")
                buffer["cmd"] = None
                rec.Reset()
                return

def run():
    ser = None
    if USE_SERIAL:
        try:
            # Optimasi: Tambah write_timeout agar write tidak menggantung jika buffer penuh
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1, write_timeout=0.1)
            time.sleep(2)
            print(f"Serial Connected: {ser.name}")
        except Exception as e:
            print(f"Serial Error: {e}")

    if USE_MIC:
        print(f"Listening... Valid Commands: {list(ACTION_MAP.keys())}")
        # Optimasi Utama: blocksize dari 4000 jadi 1000 (atau 800)
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=AUDIO_BLOCKSIZE, dtype='int16',
                               channels=1, callback=audio_callback):
            while True:
                data = q.get()
                process_data(data, ser)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")