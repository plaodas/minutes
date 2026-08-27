from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
from minutes.transcribe import transcribe

app = FastAPI(title="Minutes Inference Service")


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    dest_path = os.path.join(uploads_dir, file.filename)
    try:
        with open(dest_path, "wb") as out:
            content = await file.read()
            out.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        # Use the project's transcribe wrapper (this will import faster_whisper)
        raw_text, segments = transcribe(dest_path, model_size="medium", prompt=None)
        return JSONResponse({"raw_text": raw_text, "segments": segments})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
