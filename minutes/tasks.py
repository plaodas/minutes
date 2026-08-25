import datetime
import os
from minutes.celery_app import celery
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw


@celery.task(bind=True)
def process_audio(self, input_path: str):
    """Celery task: preprocess -> transcribe -> format.

    Returns a dict with status and output_file path.
    """
    try:
        mono, norm, clean = preprocess(input_path)
        raw_text, segments = transcribe(clean, model_size="medium", prompt=None)
        final_minutes = format_minutes_from_raw(raw_text)

        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        out_file = f"minutes_{now}.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)

        return {"status": "success", "output_file": out_file}
    except Exception as e:
        raise e
