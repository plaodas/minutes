import sys
from minutes.audio import preprocess


def main():
    if len(sys.argv) < 2:
        print("Usage: python preprocess_audio.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    print("=== Step 1-3: preprocessing audio (ffmpeg) ===")
    mono_file, norm_file, clean_file = preprocess(input_file)

    print("\n=== 完了！前処理済みファイル ===")
    print(f"モノラル化: {mono_file}")
    print(f"正規化:     {norm_file}")
    print(f"最終出力:   {clean_file}")


if __name__ == "__main__":
    main()
