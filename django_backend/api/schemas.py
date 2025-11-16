from typing import List, Optional

from pydantic import BaseModel


class RegisterIn(BaseModel):
    username: str
    password: str


class RegisterOut(BaseModel):
    id: int
    username: str


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class WorkflowItem(BaseModel):
    id: int
    name: str


class TaskNewIn(BaseModel):
    topic: str
    main_role: Optional[str] = ""
    scene: Optional[str] = ""


class TaskNewOut(BaseModel):
    task_id: int


class TaskProgressOut(BaseModel):
    current_segment: int
    status: str


class TaskListOut(BaseModel):
    task_ids: List[int]


class ResourceOut(BaseModel):
    resources: List[str]


class ExecuteOut(BaseModel):
    accepted: bool
    celery_task_id: Optional[str] = None
    message: str = ""
