import sys
from minutes.transcribe import transcribe


def main():
    if len(sys.argv) < 2:
        print("Usage: python fw_transcribe.py <audio_file>")
        sys.exit(1)

    audio = sys.argv[1]

    prompt = (
        "意向調査, GIS, 調査対象ポリゴン, 登記情報, 京都市, 森林組合, 集約化構想, "
        "年間スケジュール, 分析, 調査地域, 昨年度の調査"
    )

    raw_text, segments = transcribe(audio, model_size="medium", prompt=prompt, raw_out="raw_transcript.txt")

    print("raw_transcript.txt に書き出したよ")


if __name__ == "__main__":
    main()
