from fastapi import APIRouter, Depends, File, Form, UploadFile

from minutes import bg_store
from minutes.auth import require_current_user
from minutes.models import User
from minutes.schemas import CreateTaskResponse
from minutes.upload_service import handle_audio_upload

router = APIRouter(
    tags=["uploads"],
    dependencies=[Depends(require_current_user)],
)


@router.post("/transcribe-upload", response_model=CreateTaskResponse)
def transcribe_upload(
    file: UploadFile = File(...),  # noqa: B008
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
    user: User = Depends(require_current_user),  # noqa: B008
):
    return handle_audio_upload(
        file,
        owner_id=user.id,
        language=language,
        include_actions=include_actions,
        create_task_record=bg_store.create_task,
        include_filename=True,
    )


@router.post("/transcribe-upload-bg", response_model=CreateTaskResponse)
def transcribe_upload_background(
    file: UploadFile = File(...),  # noqa: B008
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
    user: User = Depends(require_current_user),  # noqa: B008
):
    return handle_audio_upload(
        file,
        owner_id=user.id,
        language=language,
        include_actions=include_actions,
        create_task_record=bg_store.create_task,
        include_filename=False,
    )
