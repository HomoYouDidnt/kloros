import json
import queue
import time

import sounddevice as sd
import vosk

# Test 1: Check available audio devices
if __name__ == "__main__":
    print("Available audio devices:")
    print(sd.query_devices())

    # Test 2: Simple audio capture test
    print("\nTesting audio capture for 5 seconds...")
    # Annotate queue contents as bytes for mypy
    audio_queue: queue.Queue[bytes] = queue.Queue()

    def audio_callback(indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        audio_queue.put(bytes(indata))

    try:
        with sd.RawInputStream(
            samplerate=16000,
            blocksize=8000,
            device=None,
            dtype="int16",
            channels=1,
            callback=audio_callback,
        ):
            print("Recording... say something!")

            # Test Vosk
            model = vosk.Model("/home/adam/kloros_models/vosk/model")
            rec = vosk.KaldiRecognizer(model, 16000)

            start_time = time.time()
            while time.time() - start_time < 5:
                try:
                    data = audio_queue.get(timeout=0.1)
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        print(f"Recognized: {result.get('text', '')}")
                    else:
                        partial = json.loads(rec.PartialResult())
                        if partial.get("partial"):
                            print(f"Partial: {partial.get('partial')}")

                except queue.Empty:
                    continue

            # Final result
            final = json.loads(rec.FinalResult())
            print(f"Final: {final.get('text', '')}")

    except Exception as e:
        print(f"Error: {e}")
