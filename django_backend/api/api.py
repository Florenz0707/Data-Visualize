from pathlib import Path
from typing import List

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.http import HttpRequest
from ninja import NinjaAPI
from ninja.errors import HttpError

from .auth import (
    create_access_token, create_refresh_token,
    auth_from_header, verify_refresh_token,
)
from .models import Task, TaskSegment, Resource, WorkflowDefinition
from .schemas import (
    RegisterIn, RegisterOut, LoginIn, LoginOut,
    WorkflowItem, TaskNewIn, TaskNewOut, TaskProgressOut,
    TaskListOut, ResourceOut, ExecuteOut,
)
# Import Celery async task
from .tasks import execute_task_segment

api = NinjaAPI(title="MM-StoryAgent Backend")


@api.post("/register", response={200: RegisterOut})
def register(request: HttpRequest, payload: RegisterIn):
    if User.objects.filter(username=payload.username).exists():
        raise HttpError(400, "Username already exists")
    user = User.objects.create(username=payload.username, password=make_password(payload.password))
    return RegisterOut(id=user.id, username=user.username)


@api.post("/login", response={200: LoginOut})
def login(request: HttpRequest, payload: LoginIn):
    user = User.objects.filter(username=payload.username).first()
    if not user or not check_password(payload.password, user.password):
        raise HttpError(401, "Invalid credentials")

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)

    # Build response and set cookie (no extra response param needed)
    data = LoginOut(access_token=access_token).model_dump()
    response = api.create_response(request, data, status=200)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "REFRESH_COOKIE_SECURE", False),
        max_age=getattr(settings, "REFRESH_TOKEN_LIFETIME", 7*24*3600),
    )
    return response


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
    from django.utils import timezone

    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")

    if segmentId != task.current_segment + 1:
        raise HttpError(400, "Segment cannot be executed out of order")

    # mark segment running and enqueue async job
    task.ensure_story_dir()
    seg = task.segments.filter(segment_id=segmentId).first()
    if not seg:
        raise HttpError(400, "Unknown segment")

    if seg.status == "running":
        # already queued/running, idempotent response
        async_id = None
    else:
        seg.status = "running"
        if not seg.started_at:
            seg.started_at = timezone.now()
        seg.error_message = ""
        seg.save(update_fields=["status", "started_at", "error_message"])
        if task.status in ("pending", "failed"):
            task.status = "running"
            task.save(update_fields=["status"])
        async_res = execute_task_segment.delay(task.id, segmentId)
        async_id = async_res.id

    data = ExecuteOut(accepted=True, celery_task_id=async_id, message="Execution queued")
    # Return 202 Accepted
    return api.create_response(request, data.model_dump(), status=202)


@api.delete("/task/{task_id}")
def delete_task(request: HttpRequest, task_id: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")
    task.purge_files()
    task.delete()
    return {"deleted": True}
