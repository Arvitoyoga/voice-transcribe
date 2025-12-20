import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer

import time


MODEL = "vosk-model-small-en-us-0.15"
model_path = "model/" + MODEL 
SAMPLE_RATE = 48000
buf_time = [0, 0]

COMMAND = ['payload', 'camera', 'switch']
VALUE = ['alpha', 'beta', 'delta']

grammar_json = json.dumps(COMMAND + VALUE + ["[unk]"]) 

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}. Please download and extract.")
    sys.exit()

model = Model(model_path)
rec = KaldiRecognizer(model, SAMPLE_RATE, grammar_json)

q = queue.Queue()



def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))



def run():
    # State tracking
    buffer = {"command": None, "value": None}
    buf_time = [0.0]  # Using a list to keep it mutable if needed
    last_state = ""   

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                           channels=1, callback=audio_callback):
        
        print("Listening for commands (X Y)...")
        
        while True:
            data = q.get()

            if buffer["command"] and not buffer["value"]:
                elapsed = time.time() - buf_time[0]
                if elapsed > 5.0:
                    print("\n[TIMEOUT] Command expired. Clearing buffer...")
                    buffer = {"command": None, "value": None}
                    rec.Reset() # Clear the engine too

            if rec.AcceptWaveform(data):
                res_json = json.loads(rec.Result())
                current_text = res_json.get("text", "")
            else:
                partial_json = json.loads(rec.PartialResult())
                current_text = partial_json.get("partial", "")

            if not current_text:
                continue

            words = current_text.split()
            
            for word in words:
                if word in COMMAND:
                    if buffer["command"] != word:
                        buffer["command"] = word
                        buffer["value"] = None 
                        buf_time[0] = time.time()
                        print(f"\n-> Command identified: {word}")

                elif word in VALUE:
                    if buffer["command"] and buffer["value"] != word:
                        buffer["value"] = word
                        print(f"\n-> Value identified: {word}")

            if buffer["command"] and buffer["value"]:
                cmd = buffer["command"]
                val = buffer["value"]
                
                print(f"\n[!] EXECUTE: {cmd.upper()} {val.upper()}")
                
                buffer = {"command": None, "value": None}
                buf_time[0] = 0.0
                rec.Reset() 
                print("Ready for next command...")
            
            else:
                c = buffer["command"] if buffer["command"] else "???"
                v = buffer["value"] if buffer["value"] else "???"
                current_state_string = f"Buffer: [{c}] + [{v}]"
                
                if current_state_string != last_state:
                    print(current_state_string)
                    last_state = current_state_string
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")