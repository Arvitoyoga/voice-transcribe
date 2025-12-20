import queue
import sys
import sounddevice as sd
import json
import os
from vosk import Model, KaldiRecognizer
from df.enhance import enhance, init_df, load_audio, save_audio
import numpy as np
import time
import torch
# from torchaudio.backend.common import AudioMetaData

MODEL = "vosk-model-small-en-us-0.15"
model_path = "model/" + MODEL 
SAMPLE_RATE = 16000

COMMAND = ['payload', 'camera', 'switch']
VALUE = ['alpha', 'beta', 'delta']

grammar_json = json.dumps(COMMAND + VALUE + ["[unk]"]) 

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}. Please download and extract.")
    sys.exit()

model = Model(model_path)
rec = KaldiRecognizer(model, SAMPLE_RATE, grammar_json)

q = queue.Queue()



df_model, df_state, _ = init_df()
# Load DeepFilterNet (this will download models on first run)
df_model, df_state, _ = init_df()

# Load Vosk
if not torch.cuda.is_available():
    print("Running on CPU. DeepFilterNet might be slow.")
else:
    print("CUDA available. DeepFilterNet will be fast.")



def audio_callback(indata, frames, time, status):
    """
    1. Capture at 48kHz (Required by DeepFilterNet)
    2. Enhance (Remove Drone Noise)
    3. Downsample to 16kHz (Required by Vosk)
    """
    # Convert to torch tensor
    audio = torch.from_numpy(indata.copy()).float().mean(dim=1).unsqueeze(0) # Convert to mono
    
    # Run through DeepFilterNet
    enhanced = enhance(df_model, df_state, audio)
    
    # Convert back to numpy
    enhanced_np = enhanced.squeeze().numpy()
    
    # Downsample from 48k to 16k for Vosk
    # We take every 3rd sample (48000 / 3 = 16000)
    downsampled = enhanced_np[::3]
    
    # Convert to Int16 for Vosk
    final_audio = (downsampled * 32768).astype(np.int16)
    
    q.put(final_audio.tobytes())

def run():
    
    buffer = {"command": None, "value": None}
    buf_time = [0.0]  
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
                    # Only update and print if it's a NEW command or a change
                    if buffer["command"] != word:
                        buffer["command"] = word
                        buffer["value"] = None 
                        buf_time[0] = time.time()
                        print(f"\n-> Command identified: {word}")

                elif word in VALUE:
                    # Only update if we have a command and it's a new value
                    if buffer["command"] and buffer["value"] != word:
                        buffer["value"] = word
                        print(f"\n-> Value identified: {word}")

            # 4. EXECUTION LOGIC
            if buffer["command"] and buffer["value"]:
                cmd = buffer["command"]
                val = buffer["value"]
                
                print(f"\n[!] EXECUTE: {cmd.upper()} {val.upper()}")
                
                # Success! Reset everything
                buffer = {"command": None, "value": None}
                buf_time[0] = 0.0
                rec.Reset() 
                print("Ready for next command...")
            
            else:
                # 5. UI FEEDBACK (Prevents duplicate line spam)
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