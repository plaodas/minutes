import sys
import datetime
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_minute_pipeline.py <audio_file>")
        sys.exit(1)

    audio = sys.argv[1]
    output_date = datetime.datetime.now().strftime("%Y%m%d")
    raw_file = f"raw_{output_date}.txt"
    final_file = f"minutes_{output_date}.txt"

    print("--- preprocessing audio")
    mono, norm, clean = preprocess(audio)
    print(f"preprocessed -> {clean}")

    print("--- transcribing")
    prompt = ()
    raw_text, segments = transcribe(clean, model_size="medium", prompt=prompt, raw_out=raw_file)
    print(f"raw saved -> {raw_file}")

    print("--- formatting minutes with Ollama")
    final_minutes = format_minutes_from_raw(raw_text)

    with open(final_file, "w", encoding="utf-8") as f:
        f.write(final_minutes)

    print(f"=== Done: {final_file} ===")


if __name__ == "__main__":
    main()
