import sys
from faster_whisper import WhisperModel

audio = sys.argv[1]
model = WhisperModel("medium", device="cpu")

segments, info = model.transcribe(audio, language="ja")

for seg in segments:
    print(seg.text)

