import sys
from minutes.transcribe import transcribe


def main():
    if len(sys.argv) < 2:
        print("Usage: python fw.py <audio_file>")
        sys.exit(1)

    audio = sys.argv[1]
    raw_text, segments = transcribe(audio, model_size="medium", prompt=None)

    for seg in segments:
        print(seg.text)


if __name__ == "__main__":
    main()

