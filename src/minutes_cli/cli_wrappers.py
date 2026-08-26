import sys
import datetime
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw


def run_minute_pipeline(audio: str) -> str:
    output_date = datetime.datetime.now().strftime("%Y%m%d")
    raw_file = f"raw_{output_date}.txt"
    final_file = f"minutes_{output_date}.txt"

    mono, norm, clean = preprocess(audio)
    prompt = ()
    raw_text, segments = transcribe(clean, model_size="medium", prompt=prompt, raw_out=raw_file)
    final_minutes = format_minutes_from_raw(raw_text)
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(final_minutes)
    return final_file


def auto_minutes_ollama(audio: str, prompt: str | None = None) -> str:
    output_date = datetime.datetime.now().strftime("%Y%m%d")
    raw_file = f"raw_{output_date}.txt"
    final_file = f"minutes_{output_date}.txt"

    mono, norm, clean = preprocess(audio)
    if prompt is None:
        prompt = (
            ""
        )
    raw_text, segments = transcribe(clean, model_size="medium", prompt=prompt, raw_out=raw_file)
    final_minutes = format_minutes_from_raw(raw_text)
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(final_minutes)
    return final_file


def _main_from_argv():
    if len(sys.argv) < 3:
        print("Usage: minutes_cli <command> <audio_file>")
        sys.exit(1)
    cmd = sys.argv[1]
    audio = sys.argv[2]
    if cmd == "run":
        out = run_minute_pipeline(audio)
    elif cmd == "auto":
        out = auto_minutes_ollama(audio)
    else:
        print("Unknown command")
        sys.exit(2)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    _main_from_argv()
