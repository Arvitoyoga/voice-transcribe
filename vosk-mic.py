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

MODEL_PATH = "model/vosk-model-en-us-0.22-lgraph"
SAMPLE_RATE = 16000

ERROR = 1 #data yang dikirim jika terjadi error (trash word detected, urutan salah, dll) maybe it could be displayed on the drone later



ACTION_MAP = {
    "deliver": {
        "clockwise": 2, 
        "reverse":   3
    },
    "vision": {
        "capture":   4, 
    },
    "control": {
        "override":  5 # 
    }
}

TRAP_WORDS = [ #buang beberapa kata kalau susah di detek (deliver kedetek delivery misal, tes pronounciation pilot)
    # 1. Traps for 'DELIVER' (dih-liv-er)
    "liver", "river", "driver", "diver", "silver", 
    "clever", "shiver", "sliver", "ever", "never", 
    "lever", "believer", "delivery", "defer", "differ",

    # 2. Traps for 'CLOCKWISE' (klok-waiz)
    "clock", "wise", "ways", "lock", "block", "dock", 
    "flock", "walks", "likes", "clocks", "watch",
    "twice", "price", "rise", "size", "lies",

    # 3. Traps for 'REVERSE' (ri-vurs)
    "verse", "universe", "adverse", "diverse", 
    "traverse", "converse", "nurse", "purse", "worse",
    "reserve", "rehearse", "first", "burst", "force",

    # 4. Traps for 'VISION' (viz-zhun)
    "mission", "fission", "fusion", "version", "session",
    "prison", "piston", "listen", "ocean", "lotion",
    "visor", "visit", "visual", "fishing", "fiction",

    # 5. Traps for 'CAPTURE' (kap-chur)
    "captain", "caption", "rapture", "fracture", 
    "pasture", "picture", "pitcher", "catcher", 
    "patch", "catch", "cap", "culture", "sculpture",
    "chapter", "future", "nature",

    # 6. Traps for 'CONTROL' (kun-trol)
    "troll", "roll", "poll", "pole", "coal", "goal",
    "patrol", "stroll", "scroll", "console", "role",
    "toll", "hole", "whole", "soul", "enroll",

    # 7. Traps for 'OVERRIDE' (oh-ver-ride)
    "over", "ride", "ride", "wide", "side", "tide",
    "bride", "pride", "guide", "hide", "slide",
    "write", "right", "white", "overrate", "overnight",
    "overwrite", "overt", "offer",

    # 8. General Noise / Common Short Words
    # Vosk often aligns breath/static to these
    "the", "a", "an", "it", "is", "to", "in", "on", 
    "and", "that", "this", "no", "yes", "stop", "go",
    "[unk]" # The built-in 'unknown' token
]


command_words = list(ACTION_MAP.keys())
key_words = []
for cmd in ACTION_MAP:
    key_words.extend(list(ACTION_MAP[cmd].keys()))

grammar_list = command_words + key_words + TRAP_WORDS
grammar_json = json.dumps(grammar_list)

if not os.path.exists(MODEL_PATH):
    print(f"Model not found at {MODEL_PATH}")
    sys.exit()
def send_error(ser):
    if USE_SERIAL:
        send_serial(ser, ERROR)

model = Model(MODEL_PATH)
rec = KaldiRecognizer(model, SAMPLE_RATE, grammar_json)
rec.SetWords(True)
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
        print(f"-> [SERIAL TX] ID: {cmd_id} | HEX: {packet.hex()}")
    except Exception as e:
        print(f"Serial Error: {e}")

def process_data(data, active_ser):
    global last_time, buffer

    # 1. Timeout Check
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
        if word == "[unk]" or word in TRAP_WORDS:
            send_error(active_ser)
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
                send_error(active_ser)
                return 


            valid_keys_map = ACTION_MAP[buffer["cmd"]] 

            if word in valid_keys_map:
                # MATCH!
                serial_id = valid_keys_map[word]
                print(f"[KEY] {word.upper()} ACCEPTED!")
                print(f"!!! EXECUTING: {buffer['cmd'].upper()} {word.upper()} (ID: {serial_id}) !!!")
                
                send_serial(active_ser, serial_id)
                
                # Reset
                buffer["cmd"] = None
                rec.Reset()
                if USE_MIC:
                    with q.mutex: q.queue.clear()
                return
            
            else:
                send_error(active_ser)
                print(f"[ERR] Key '{word}' invalid for command '{buffer['cmd']}'")
                buffer["cmd"] = None
                rec.Reset()
                return


def run():
    ser = None
    if USE_SERIAL:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            print(f"Serial Connected: {ser.name}")
        except Exception as e:
            print(f"Serial Error: {e}")

    if USE_MIC:
        print(f"Listening... Valid Commands: {list(ACTION_MAP.keys())}")
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                               channels=1, callback=audio_callback):
            while True:
                data = q.get()
                process_data(data, ser)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")