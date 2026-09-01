import sys
import datetime
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw


def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_minutes_ollama.py <audio_file>")
        sys.exit(1)

    audio = sys.argv[1]
    OUTPUT_DATE = datetime.datetime.now().strftime("%Y%m%d")
    RAW_FILE = f"raw_{OUTPUT_DATE}.txt"
    FINAL_FILE = f"minutes_{OUTPUT_DATE}.txt"

    print("=== Step 1: preprocess audio ===")
    mono, norm, clean = preprocess(audio)

    print("=== Step 2: transcribe ===")
    prompt = ()
    raw_text, segments = transcribe(clean, model_size="medium", prompt=prompt, raw_out=RAW_FILE)
    print(f"raw transcript saved → {RAW_FILE}")

    print("=== Step 3: format minutes with Ollama ===")
    final_minutes = format_minutes_from_raw(raw_text)

    with open(FINAL_FILE, "w", encoding="utf-8") as f:
        f.write(final_minutes)

    print(f"=== 完成！議事録 saved → {FINAL_FILE} ===")


if __name__ == "__main__":
    main()
