import subprocess
import sys
import os

# ====== 入力ファイル ======
input_file = sys.argv[1]

# ====== 出力ファイル名 ======
base = os.path.splitext(input_file)[0]
mono_file = f"{base}_mono.wav"
norm_file = f"{base}_norm.wav"
clean_file = f"{base}_clean.wav"

# ====== 1. モノラル化 ======
print("=== Step 1: モノラル化中 ===")
subprocess.run([
    "ffmpeg", "-y",
    "-i", input_file,
    "-ac", "1",
    mono_file
])

# ====== 2. 音量正規化（loudnorm） ======
print("=== Step 2: 音量正規化中 ===")
subprocess.run([
    "ffmpeg", "-y",
    "-i", mono_file,
    "-af", "loudnorm",
    norm_file
])

# ====== 3. ハイパスフィルタ（机の振動音を除去） ======
print("=== Step 3: ハイパスフィルタ適用中 ===")
subprocess.run([
    "ffmpeg", "-y",
    "-i", norm_file,
    "-af", "highpass=f=120",
    clean_file
])

print("\n=== 完了！前処理済みファイル ===")
print(f"モノラル化: {mono_file}")
print(f"正規化:     {norm_file}")
print(f"最終出力:   {clean_file}")
