import sys
import datetime
import requests
from faster_whisper import WhisperModel

# ====== 設定 ======
AUDIO = sys.argv[1]
MODEL_SIZE = "medium"
OUTPUT_DATE = datetime.datetime.now().strftime("%Y%m%d")
RAW_FILE = f"raw_{OUTPUT_DATE}.txt"
FINAL_FILE = f"minutes_{OUTPUT_DATE}.txt"

# Ollama のモデル名（必要に応じて変更）
# OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_MODEL = "gemma4:e4b"


# ====== Step 1: faster-whisper で文字起こし ======
print("=== Step 1: faster-whisper で文字起こし中 ===")

prompt = (
    "意向調査, GIS, 調査対象ポリゴン, 登記情報, 京都市, 森林組合, 集約化構想, "
    "年間スケジュール, 分析, 調査地域, 昨年度の調査"
)

model = WhisperModel(MODEL_SIZE, device="cpu")

segments, info = model.transcribe(
    AUDIO,
    language="ja",
    initial_prompt=prompt,
    beam_size=7,
    temperature=0.0,
    vad_filter=False,
    best_of=5,
    patience=0.2,
)

raw_text = "\n".join([seg.text for seg in segments])

with open(RAW_FILE, "w", encoding="utf-8") as f:
    f.write(raw_text)

print(f"raw transcript saved → {RAW_FILE}")

# ====== Step 2: raw_transcript.txt を読み込む ======
print("=== Step 2: raw_transcript.txt を読み込み中 ===")

with open(RAW_FILE, "r", encoding="utf-8") as f:
    raw_loaded = f.read()

# ====== Step 3: Ollama で議事録補正 ======
print("=== Step 3: Ollama で議事録補正中 ===")

system_prompt = """
あなたは議事録を整形する専門家です。
以下の文字起こしを、文脈・固有名詞・誤変換を補正し、
読みやすい議事録として整形してください。

【会議の背景】
- 意向調査
- GIS を使った調査対象ポリゴンの特定
- 登記情報の紐づけ
- 調査地域は京都市
- 昨年度の調査をベースにした年間スケジュール
- 今年度は森林組合と協力し、集約化構想を前提に調査
- 成果物の分析は集約化構想に役立つ内容が求められている

あなたのタスクは次の通りです：

1. 文脈を読み取り、意味が通るように文章を再構成する
2. 誤変換・聞き間違いを修正する
3. 話者の意図を保ちながら、読みやすい文章に整える
4. 不明瞭な箇所は推測せず、「不明」と記載する
5. 箇条書き・段落分けを適切に行う
6. 会議の流れが分かるように構造化する（議題 → 発言 → 決定事項）

出力形式：

【議題】
…

【議論内容】
…

【決定事項】
…

【TODO】
…

"""

user_prompt = f"【文字起こし】\n{raw_loaded}"

payload = {
    "model": OLLAMA_MODEL,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "stream": False
}

response = requests.post("http://localhost:11434/api/chat", json=payload)
response_json = response.json()
msg = response_json.get("message", {})
content = msg.get("content")

if not content:
    # fallback
    content = response_json.get("response")

if not content:
    raise ValueError(f"Unexpected response format: {response_json}")

final_minutes = content

with open(FINAL_FILE, "w", encoding="utf-8") as f:
    f.write(final_minutes)

print(f"=== 完成！議事録 saved → {FINAL_FILE} ===")
