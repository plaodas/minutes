from typing import Any, Dict, Optional
from pydantic import BaseModel


class TaskIdResponse(BaseModel):
    task_id: str


class CreateTaskResponse(BaseModel):
    task_id: str


class StatusResponse(BaseModel):
    task_id: str
    status: str
    error: Optional[str] = None


class ResultSuccess(BaseModel):
    status: str
    result: Dict[str, Any]


class FormatRawRequest(BaseModel):
    raw: str


class FormatRawResponse(BaseModel):
    minutes: str
