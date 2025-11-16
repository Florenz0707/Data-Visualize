from ninja import NinjaAPI
from ninja.errors import HttpError
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.http import HttpRequest, HttpResponse

from django.conf import settings
from .schemas import (
    RegisterIn, RegisterOut, LoginIn, LoginOut,
    WorkflowItem, TaskNewIn, TaskNewOut, TaskProgressOut,
    TaskListOut, ResourceOut, ExecuteOut,
)
from .auth import (
    create_access_token, create_refresh_token,
    auth_from_header, verify_refresh_token,
)
from .models import Task, TaskSegment, Resource, WorkflowDefinition
from pathlib import Path
from typing import List

# Import real workflow runner (ensure api/services is a package)
from .services.workflow import WorkflowRunner

api = NinjaAPI(title="MM-StoryAgent Backend")


@api.post("/register", response={200: RegisterOut})
def register(request: HttpRequest, payload: RegisterIn):
    if User.objects.filter(username=payload.username).exists():
        raise HttpError(400, "Username already exists")
    user = User.objects.create(username=payload.username, password=make_password(payload.password))
    return RegisterOut(id=user.id, username=user.username)


@api.post("/login", response={200: LoginOut})
def login(request: HttpRequest, payload: LoginIn, response: HttpResponse):
    user = User.objects.filter(username=payload.username).first()
    if not user or not check_password(payload.password, user.password):
        raise HttpError(401, "Invalid credentials")

    access = create_access_token(user)
    refresh = create_refresh_token(user)

    # Build response and set cookie (no extra response param needed)
    data = LoginOut(access_token=access).dict()
    resp = api.create_response(request, data, status=200)
    resp.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "REFRESH_COOKIE_SECURE", False),
        max_age=getattr(settings, "REFRESH_TOKEN_LIFETIME", 7*24*3600),
    )
    return resp


@api.post("/refresh", response={200: LoginOut})
def refresh(request: HttpRequest):
    cookie = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
    user = verify_refresh_token(cookie) if cookie else None
    if not user:
        raise HttpError(401, "Invalid refresh token")

    access = create_access_token(user)
    return LoginOut(access_token=access)


@api.get("/task/workflow", response={200: list[WorkflowItem]})
def get_workflow(request: HttpRequest):
    segments = WorkflowDefinition.get_active_segments()
    return [WorkflowItem(**s) for s in segments]


def require_user(request: HttpRequest) -> User:
    user = auth_from_header(request.headers.get("Authorization"))
    if not user:
        raise HttpError(401, "Unauthorized")
    return user


@api.post("/task/new", response={200: TaskNewOut})
def task_new(request: HttpRequest, payload: TaskNewIn):
    user = require_user(request)
    task = Task.objects.create(
        user=user,
        topic=payload.topic,
        main_role=payload.main_role or "",
        scene=payload.scene or "",
        status="pending",
        current_segment=0,
    )
    task.ensure_story_dir()
    # Pre-create TaskSegment entries
    for segment in WorkflowDefinition.get_active_segments():
        TaskSegment.objects.create(task=task, segment_id=segment["id"], name=segment["name"], status="pending")
    return TaskNewOut(task_id=task.id)


@api.get("/task/{task_id}/progress", response={200: TaskProgressOut})
def task_progress(request: HttpRequest, task_id: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")
    return TaskProgressOut(current_segment=task.current_segment, status=task.status)


@api.get("/task/mytasks", response={200: TaskListOut})
def my_tasks(request: HttpRequest):
    user = require_user(request)
    ids = list(user.tasks.values_list("id", flat=True).order_by("-id"))
    return TaskListOut(task_ids=ids)


@api.get("/task/{task_id}/resource", response={200: ResourceOut})
def task_resource(request: HttpRequest, task_id: int, segmentId: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")

    if task.current_segment < segmentId:
        raise HttpError(400, "Segment not completed yet")

    # Return file paths as relative strings
    items = list(Resource.objects.filter(task=task, segment_id=segmentId).values_list("path", flat=True))
    return ResourceOut(resources=items)


def _record_resources(task: Task, segment_id: int, paths: List[str], rtype: str):
    for p in paths:
        Resource.objects.create(task=task, segment_id=segment_id, type=rtype, path=str(p))


@api.post("/task/{task_id}/execute/{segmentId}", response={200: ExecuteOut})
def execute_segment(request: HttpRequest, task_id: int, segmentId: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")

    if segmentId != task.current_segment + 1:
        raise HttpError(400, "Segment cannot be executed out of order")

    # Synchronous, single-user execution using real workflow
    runner = WorkflowRunner()
    task.ensure_story_dir()

    try:
        if segmentId == 1:
            pages = runner.run_story(task.story_dir, topic=task.topic, main_role=task.main_role, scene=task.scene)
            script_path = str(Path(task.story_dir) / "script_data.json")
            _record_resources(task, 1, [script_path], rtype="json")
        elif segmentId == 2:
            images = runner.run_image(task.story_dir)
            _record_resources(task, 2, images, rtype="image")
        elif segmentId == 3:
            runner.run_split(task.story_dir)
            script_path = str(Path(task.story_dir) / "script_data.json")
            _record_resources(task, 3, [script_path], rtype="json")
        elif segmentId == 4:
            wavs = runner.run_speech(task.story_dir)
            _record_resources(task, 4, wavs, rtype="audio")
        elif segmentId == 5:
            video = runner.run_video(task.story_dir)
            _record_resources(task, 5, [video], rtype="video")
        else:
            raise HttpError(400, "Unknown segment")
    except HttpError:
        raise
    except Exception as e:
        seg = task.segments.filter(segment_id=segmentId).first()
        if seg:
            seg.status = "failed"
            seg.error_message = str(e)
            seg.save(update_fields=["status", "error_message"])
        task.status = "failed"
        task.save(update_fields=["status"])
        raise HttpError(500, f"Segment execution failed: {e}")

    seg = task.segments.filter(segment_id=segmentId).first()
    if seg:
        seg.status = "completed"
        seg.save(update_fields=["status"])

    task.current_segment = segmentId
    task.status = "completed" if segmentId >= 5 else "running"
    task.save(update_fields=["current_segment", "status"])

    return ExecuteOut(accepted=True, message="Execution completed")


@api.delete("/task/{task_id}")
def delete_task(request: HttpRequest, task_id: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")
    task.purge_files()
    task.delete()
    return {"deleted": True}

