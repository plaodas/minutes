from typing import Any

from pydantic import BaseModel


class TaskIdResponse(BaseModel):
    task_id: str


class CreateTaskResponse(BaseModel):
    task_id: str


class StatusResponse(BaseModel):
    task_id: str
    status: str
    error: str | None = None


class ResultSuccess(BaseModel):
    status: str
    result: dict[str, Any]


class FormatRawRequest(BaseModel):
    raw: str


class FormatRawResponse(BaseModel):
    minutes: str
