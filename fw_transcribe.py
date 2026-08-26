import sys
from minutes.transcribe import transcribe


def main():
    if len(sys.argv) < 2:
        print("Usage: python fw_transcribe.py <audio_file>")
        sys.exit(1)

    audio = sys.argv[1]

    prompt = ()

    raw_text, segments = transcribe(audio, model_size="medium", prompt=prompt, raw_out="raw_transcript.txt")

    print("raw_transcript.txt に書き出したよ")


if __name__ == "__main__":
    main()
