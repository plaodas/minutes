from fastapi import APIRouter, File, Form, Header, UploadFile

from minutes import bg_store
from minutes.schemas import CreateTaskResponse
from minutes.upload_service import handle_audio_upload

router = APIRouter(tags=["uploads"])


@router.post("/transcribe-upload", response_model=CreateTaskResponse)
def transcribe_upload(
    file: UploadFile = File(...),  # noqa: B008
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    return handle_audio_upload(
        file,
        x_user_id=x_user_id,
        authorization=authorization,
        language=language,
        include_actions=include_actions,
        create_task_record=bg_store.create_task,
        include_filename=True,
    )


@router.post("/transcribe-upload-bg", response_model=CreateTaskResponse)
def transcribe_upload_background(
    file: UploadFile = File(...),  # noqa: B008
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    return handle_audio_upload(
        file,
        x_user_id=x_user_id,
        authorization=authorization,
        language=language,
        include_actions=include_actions,
        create_task_record=bg_store.create_task,
        include_filename=False,
    )
