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
    topic: str  # For videogen, this serves as the prompt
    main_role: Optional[str] = ""
    scene: Optional[str] = ""
    description: Optional[str] = ""
    workflow_version: Optional[str] = "default"  # "default" or "videogen"


class TaskNewOut(BaseModel):
    task_id: int


class TaskProgressOut(BaseModel):
    current_segment: int
    status: str
    workflow_version: str
    total_segments: int
    segment_names: List[str]


class TaskListOut(BaseModel):
    task_ids: List[int]


class ResourceOut(BaseModel):
    resources: List[str]


class ExecuteOut(BaseModel):
    accepted: bool
    celery_task_id: Optional[str] = None
    message: str = ""


class T2VExecuteIn(BaseModel):
    prompt: Optional[str] = None
    model: Optional[str] = None         # e.g., "runway_gen4_turbo" or provider-native like "gen4_turbo"
    ratio: Optional[str] = None         # e.g., "1280:720"
    prompt_image_path: Optional[str] = None
    prompt_image_data_uri: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    duration: Optional[float] = None
    use_mock: Optional[bool] = None
