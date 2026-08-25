import sys
from faster_whisper import WhisperModel

audio = sys.argv[1]

# medium が一番安定
model = WhisperModel("medium", device="cpu")

prompt = (
    "意向調査, GIS, 調査対象ポリゴン, 登記情報, 京都市, 森林組合, 集約化構想, "
    "年間スケジュール, 分析, 調査地域, 昨年度の調査"
)

segments, info = model.transcribe(
    audio,
    language="ja",
    initial_prompt=prompt,
    beam_size=5,
    vad_filter=True,          # 無音区切り（チャンクの代替）
    vad_parameters=dict(
        min_silence_duration_ms=500,
        speech_pad_ms=200,
    ),
)

with open("raw_transcript.txt", "w", encoding="utf-8") as f:
    for seg in segments:
        f.write(seg.text + "\n")

print("raw_transcript.txt に書き出したよ")
