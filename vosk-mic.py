import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
import time
import serial

USE_MIC = True  
USE_SERIAL = False
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600

MODEL_PATH = "model/vosk-model-en-us-0.22-lgraph"
SAMPLE_RATE = 16000

ERROR = 0 #data yang dikirim jika terjadi error (trash word detected, urutan salah, dll) maybe it could be displayed on the drone later



ACTION_MAP = {
    "distribute": { # D, deliver / payload
        "scarlet": 2, 
        "cobalt":   3
    },
    "virginia": { # V, video / cam switch
        "scarlet":   4, 
    },
    "subdural": { # S, switch / drone switch
        "scarlet":  5 # 
    }
}


TRAP_PHRASES = [
    "go bold", 
    "hold the", 
    "hold the bolt",
    "go ball",
    "go bald"
]


TRAP_WORDS = [ #buang beberapa kata kalau susah di detek (distribute kedetek distributer, tes pronounciation pilot)
    
    # --- 1. Traps for 'DISTRIBUTE' (dih-stri-byoot) ---
    # Sound-alikes: "Dis-" start or "-bute" end
    "district", "disturb", "dispute", "display", "distinct",
    "tribute", "attribute", "contribute", "statute",
    "this", "tree", "three", "street", "mute", "but",
    "distributer", "distribution", # Variations of the word itself |MATIIN KALO SUSAH DETEK|
   "destitute", "institute", "constitute", "prostitute", # -tute endings
    "dispute", "repute", "impute",
    "street", "straight", "strut", "strip", # Strong "Str" sounds
    "dish", "fish", "wish", # Soft "sh" sounds similar to "dis"
    "boot", "root", "shoot", # "bute" sound
    "this three", "is three", "tree root", # Phrases that sound like it



    # --- 2. Traps for 'VIRGINIA' (ver-jin-ya) ---
    # Sound-alikes: "Vir-" start or "-nia" end
    "virgin", "version", "vertical", "virtual", "virtue",
    "engineer", "junior", "senior", "linear", "genius",
    "india", "media", "area", "near", "here",
    "gin", "engine", "general", "journey",
    "regina", "vagina", "angina", "arena", "hyena", # -ina/-ena endings
    "gardenia", "ammonia", "pneumonia", "mania",
    "venue", "menu", "sinew", "continue",
    "verdant", "verdict", "vermin", # Ver- starts
    "genie", "genius", "genus", 

    # --- 3. Traps for 'SUBDURAL' (sub-door-al) ---
    # Sound-alikes: "Sub-" start or "-ral" end
    "subway", "subject", "suburb", "subtle", "sub",
    "rural", "plural", "mural", "neural", "natural",
    "federal", "several", "general", "admiral", "mineral",
    "durable", "door", "dual", "during",
      "subzero", "subtotal", "subtitle", "subtle",
    "sudden", "sadden", "madden",
    "spiral", "viral", "oral", "moral", "coral", "floral", # -ral endings
    "barrel", "peril", "sterile", 
    "dural", "durable", "during", "jury",



 # --- TRAPS FOR 'SCARLET' (Skar-let) ---
    # Sound-alikes: "Skar-" start or "-let" end
    "starlet", "charlotte", "harlot", "varlet",
    "scar", "star", "car", "far", "bar",
    "let", "net", "set", "bet", "wet",
    "wallet", "bullet", "skillet", "toilet", "pilot",
    "garlic", "target", "market", "carpet",
    "skeleton", "scatter", "scholar",
     "starlit", "harlot", "varlet",
    "scared", "sacred", "scary", "score",
    "skillet", "spill it", "kill it", "still it", # -ill it rhymes with -arlet loosely
    "carl", "earl", "pearl", "girl", # -ar/-erl sounds
    "solid", "salad", "valid", "pallid", # rhythm traps,
    "cigarrete", "carrot", "carpet", "secret", "circuit", 

    # --- TRAPS FOR 'COBALT' (Ko-balt) ---
    # Sound-alikes: "Ko-" start or "-alt" end
    "bolt", "colt", "jolt", "volt", "fault","gobble", "cobble", "kabob",
    "salt", "halt", "malt", "vault",
    "default", "asphalt", "assault", "exalt",
    "cobble", "bubble", "double", "trouble",
    "robot", "goblet", "global", "mobile",
    "cold", "bold", "old", "hold", "gold"
    "cobble", "wobble", "gobble", "hobble",
    "cable", "table", "label", "stable", "fable", # -able sounds like -alt
    "global", "noble", "mobile",
    "ball", "bald", "bold", "bowl",
    "code", "coat", "boat", "goat", "vote", # -oat sounds like -alt
    "result", "insult", "adult", "consult" # -ult sounds like -alt
    "cable", "table", "label", "stable", "fable", # -able sounds like -alt

    "bold", "cold", "gold", "hold", "fold", "mold", "sold", "told",
    "scold", "old", "bowl", "roll", "poll", "goal",

    "bolt", "jolt", "volt", "colt", "dolt", "molt", "revolt",
    "fault", "salt", "halt", "malt", "vault", "default",


    # 8. General Noise / Common Short Words
    # Vosk often aligns breath/static to these
    "the", "a", "an", "it", "is", "to", "in", "on", "at", "of",
    "and", "that", "this", "no", "yes", "stop", "go", "up",
    "okay", "hey", "hi", "hello", "right", "left",


    # 9. Drone-Specific Words
    "battery", "voltage", "signal", "gps", "mode",
    "stable", "hover", "launch", "land", "arm", "disarm",
    "ready", "check", "clear", "prop", "motor",
    "one", "two", "three", "four", "five", # Numbers are often confused with syllables
    "six", "seven", "eight", "nine", "ten",
    "error", "fire", "fail", "cancel",  "reset",



    "[unk]" # The built-in 'unknown' token
]


command_words = list(ACTION_MAP.keys())
key_words = []
for cmd in ACTION_MAP:
    key_words.extend(list(ACTION_MAP[cmd].keys()))

grammar_list = command_words + key_words + TRAP_WORDS + TRAP_PHRASES
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
            # send_error(active_ser)
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
                # send_error(active_ser)
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
                # send_error(active_ser)
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