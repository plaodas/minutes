import sys
import datetime
from minutes.ollama import format_minutes_from_raw


def main():
    if len(sys.argv) < 2:
        print("Usage: python ollama_minutes_from_raw.py <raw_transcript.txt>")
        sys.exit(1)

    RAW_FILE = sys.argv[1]
    OUTPUT_DATE = datetime.datetime.now().strftime("%Y%m%d")
    FINAL_FILE = f"minutes_{OUTPUT_DATE}.txt"

    print("=== Step 1: raw_transcript.txt を読み込み中 ===")
    with open(RAW_FILE, "r", encoding="utf-8") as f:
        raw_loaded = f.read()

    print("=== Step 2: Ollama で議事録補正中 ===")
    final_minutes = format_minutes_from_raw(raw_loaded)

    with open(FINAL_FILE, "w", encoding="utf-8") as f:
        f.write(final_minutes)

    print(f"=== 完成！議事録 saved → {FINAL_FILE} ===")


if __name__ == "__main__":
    main()
