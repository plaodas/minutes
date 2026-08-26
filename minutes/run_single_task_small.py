import os
import sys
import uuid
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw
from minutes.bg_store import update_task_success, update_task_failure


def run(upload_path: str, task_id: str):
    try:
        mono, norm, clean = preprocess(upload_path)
        # use a smaller model to reduce memory use
        model_size = os.environ.get("TRANSCRIBE_MODEL_SIZE", "small")
        raw_text, segments = transcribe(clean, model_size=model_size, prompt=None)
        try:
            final_minutes = format_minutes_from_raw(raw_text)
        except Exception as fe:
            # Ollama formatting failed; fall back to raw transcript with header
            final_minutes = "[FALLBACK] Ollama formatting failed: " + str(fe) + "\n\n" + raw_text

        outputs_dir = os.environ.get("OUTPUTS_DIR", "data/outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        now = uuid.uuid4().hex
        tmp_file = os.path.join(outputs_dir, f"minutes_{now}.txt.tmp")
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")

        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass

        os.replace(tmp_file, out_file)

        if not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
            raise RuntimeError(f"Output write failed: {out_file}")

        update_task_success(task_id, {"output_file": out_file})
        print("SUCCESS", out_file)
    except Exception as exc:
        try:
            update_task_failure(task_id, str(exc))
        except Exception:
            pass
        print("FAILED", repr(exc))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 minutes/run_single_task_small.py <upload_path> <task_id>")
        sys.exit(2)
    run(sys.argv[1], sys.argv[2])
