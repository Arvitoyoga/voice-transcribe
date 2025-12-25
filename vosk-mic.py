import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
import time
import serial
import wave


USE_MIC = True  
WAV_FILE_PATH = "dataset/tes-noise-drone-lab2.wav" 

USE_SERIAL = False
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600

MODEL = "vosk-model-small-en-us-0.15"
model_path = "model/" + MODEL 
SAMPLE_RATE = 16000

COMMAND = ['payload', 'camera', 'switch']
KEY = ['papa', 'charlie', 'sierra']

global buffer
buffer = {"cmd": None, "key": None}
buf_time = [0.0]

grammar_json = json.dumps(COMMAND + KEY  + ["[unk]"]) 

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}")
    sys.exit()

model = Model(model_path)
rec = KaldiRecognizer(model, SAMPLE_RATE, grammar_json)
q = queue.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

def send_serial(ser, command, key):
    if not USE_SERIAL or ser is None:
        return
    try:
        cmd_id = COMMAND.index(command)
        key_id = KEY.index(key)
        header = 0xAA
        checksum = (cmd_id + key_id) & 0xFF
        packet = bytearray([header, cmd_id, key_id, checksum])
        ser.write(packet)
        print(f"-> SENT SERIAL: {command} KEY: {key} (ID: {cmd_id})")
    except Exception as e:
        print(f"Serial Error: {e}")

def run():
    # 1. Setup Serial
    ser = None
    if USE_SERIAL:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            print(f"Serial Connected: {ser.name}")
        except Exception as e:
            print(f"Serial Failed: {e}")

    state = {'last_time': 0}

    def process_data(data):

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
        # print(f"Detected words: {words}")
        if not words:
            return

        for word in words:
            if word in COMMAND:
                if buffer['cmd'] != word:
                    buffer['cmd'] = word
                    buffer['key'] = None
                    buf_time[0] = time.time()
                    print(f"[Buffer] Command set to: {word}")
                    print(f"word index: {COMMAND.index(word)}, matching val {KEY[COMMAND.index(word)]}")
            elif word in KEY:
                # print(f"Key detected: {word}")
                if buffer["cmd"] and  buffer["key"] is None:
                    # print("[Buffer] Key detected:", word)
                    if word == KEY[COMMAND.index(buffer['cmd'])]:

                        buffer['key'] = word
                        # print(f"[Buffer] Key set to: {word}")
                    else:
                        print(f"[Buffer] Key '{word}' does not match Command '{buffer['cmd']}'. Ignored.")

        if buffer['cmd'] and buffer['key']:
            cmd = buffer['cmd']
            key = buffer["key"]

            print(f"\n[!] EXECUTE: {cmd.upper()} with KEY: {key.upper()}")
            send_serial(ser, cmd, key)
            buffer["cmd"] = None
            buffer["key"] = None
            buf_time[0] = 0.0
            rec.Reset()
            print("Ready for next command...")
            if USE_MIC:
                with q.mutex:
                    q.queue.clear()


    if USE_MIC:
        print(f"Listening on Microphone ({SAMPLE_RATE}Hz)...")
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype='int16',
                               channels=1, callback=audio_callback):
            while True:
                data = q.get()
                process_data(data)

    else:
        if not os.path.exists(WAV_FILE_PATH):
            print(f"Error: File {WAV_FILE_PATH} not found.")
            return

        print(f"Processing File: {WAV_FILE_PATH}...")
        wf = wave.open(WAV_FILE_PATH, "rb")

        if wf.getnchannels() != 1 or wf.getframerate() != SAMPLE_RATE:
            print("ERROR: Wav file must be Mono and 16000Hz.")
            return

        while True:
            data = wf.readframes(4000)
            
            if len(data) == 0:
                break 
            
            process_data(data)
            
            time.sleep(0.25) 
            
        print("\nEnd of file reached.")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExiting...")