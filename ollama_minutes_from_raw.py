import sys
import datetime
import requests
import json

RAW_FILE = sys.argv[1]
OUTPUT_DATE = datetime.datetime.now().strftime("%Y%m%d")
FINAL_FILE = f"minutes_{OUTPUT_DATE}.txt"

# OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_MODEL = "gemma4:e4b"

print("=== Step 1: raw_transcript.txt を読み込み中 ===")

with open(RAW_FILE, "r", encoding="utf-8") as f:
    raw_loaded = f.read()

print("=== Step 2: Ollama で議事録補正中 ===")

system_prompt = """
あなたは会議の議事録を整形する専門家です。
以下の文字起こしは、話し言葉・誤変換・文脈の乱れが多い生データです。

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

user_prompt = f"以下は会議の生文字起こしです。議事録として整形してください。\n\n{raw_loaded}"

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

# JSON を確認
try:
    response_json = response.json()
except json.JSONDecodeError:
    print("❌ Ollama から JSON が返ってきませんでした")
    print("レスポンス内容：")
    print(response.text)
    sys.exit(1)

# デバッグ用にレスポンス全体を表示
print("=== Ollama Response ===")
print(json.dumps(response_json, indent=2, ensure_ascii=False))

# 正常時の取り出し
if "message" in response_json and "content" in response_json["message"]:
    final_minutes = response_json["message"]["content"]
else:
    print("❌ 'message' フィールドがありません。Ollama のエラーかもしれません。")
    sys.exit(1)

with open(FINAL_FILE, "w", encoding="utf-8") as f:
    f.write(final_minutes)

print(f"=== 完成！議事録 saved → {FINAL_FILE} ===")
