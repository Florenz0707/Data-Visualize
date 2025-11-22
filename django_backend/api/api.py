import json
import mimetypes
import shutil
from pathlib import Path
from typing import List
import logging

import aiofiles
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest, StreamingHttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError
from typing import Optional

from .auth import (
    create_access_token, create_refresh_token,
    auth_from_header, verify_refresh_token,
)
from .models import Task, TaskSegment, Resource, WorkflowDefinition
from .schemas import (
    RegisterIn, RegisterOut, LoginIn, LoginOut,
    WorkflowItem, TaskNewIn, TaskNewOut, TaskProgressOut,
    TaskListOut, ExecuteOut, T2VExecuteIn,
)

api = NinjaAPI(title="MM-StoryAgent Backend")
logger = logging.getLogger("django")


# --- Helpers for redo semantics ---

def _safe_remove(p: Path):
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _prepare_redo(task: Task, start_segment: int) -> None:
    """Prepare redo starting from start_segment (1..5):
    - Reset TaskSegment >= start_segment to pending
    - Delete Resource rows for segments >= start_segment
    - Remove generated files on disk accordingly
    - Set task.current_segment = start_segment - 1 and status to running
    """
    if start_segment < 1 or start_segment > 5:
        raise HttpError(400, "Invalid segmentId")

    story_dir = Path(task.ensure_story_dir()).resolve()

    # DB updates
    with transaction.atomic():
        segs = task.segments.select_for_update().filter(segment_id__gte=start_segment)
        segs.update(status="pending", error_message="", started_at=None, ended_at=None)
        Resource.objects.filter(task=task, segment_id__gte=start_segment).delete()
        task.current_segment = start_segment - 1
        task.status = "running"
        task.save(update_fields=["current_segment", "status"])

    # Filesystem cleanup according to start_segment
    try:
        if start_segment <= 1:
            # wipe everything under story_dir
            for child in story_dir.iterdir():
                _safe_remove(child)
        elif start_segment == 2:
            _safe_remove(story_dir / "image")
            _safe_remove(story_dir / "speech")
            _safe_remove(story_dir / "output.mp4")
        elif start_segment == 3:
            _safe_remove(story_dir / "speech")
            _safe_remove(story_dir / "output.mp4")
            # remove segmented info from script_data.json
            sp = story_dir / "script_data.json"
            if sp.exists():
                try:
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "segmented_pages" in data:
                        data.pop("segmented_pages", None)
                        sp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
                except Exception:
                    pass
        elif start_segment == 4:
            _safe_remove(story_dir / "speech")
            _safe_remove(story_dir / "output.mp4")
        elif start_segment == 5:
            _safe_remove(story_dir / "output.mp4")
    finally:
        (story_dir / "image").mkdir(parents=True, exist_ok=True)
        (story_dir / "speech").mkdir(parents=True, exist_ok=True)


@api.get("/resource")
def download_resource(request: HttpRequest, url: str):
    user = auth_from_header(request.headers.get("Authorization"))
    if not user:
        logger.warning("/api/resource unauthorized: missing/invalid token")
        raise HttpError(401, "Unauthorized")

    try:
        rel = Path(url)
    except Exception:
        logger.warning("/api/resource invalid url param: %r", url)
        raise HttpError(400, "Invalid url")
    if rel.is_absolute() or ".." in rel.parts:
        logger.warning("/api/resource rejected absolute or traversal url: %r parts=%s", url, rel.parts)
        raise HttpError(400, "Invalid url")

    # Compute base/abs for potential fallbacks
    base_dir = Path(settings.BASE_DIR).resolve()
    abs_path = (base_dir / rel).resolve()

    # DB lookup (exact relative first)
    res_qs = Resource.objects.filter(path=str(rel), task__user=user)
    if not res_qs.exists():
        # Try absolute path variant (for legacy rows that stored abs paths)
        abs_qs = Resource.objects.filter(path=str(abs_path), task__user=user)
        if abs_qs.exists():
            res_qs = abs_qs
        else:
            # As a last resort, try suffix match under same user
            suffix_qs = Resource.objects.filter(path__endswith=str(rel), task__user=user)
            if suffix_qs.exists():
                res_qs = suffix_qs
            else:
                # Extra diagnostics: try to locate nearby matches for same user task
                similar = list(Resource.objects.filter(path__icontains=rel.name, task__user=user).values_list("path", flat=True)[:5])
                logger.warning("/api/resource not found in DB: user=%s url=%s similar_candidates=%s", user.id, str(rel), similar)
                raise HttpError(404, "Resource not found")

    res = res_qs.select_related("task").order_by("-id").first()
    task = res.task

    story_dir = Path(task.story_dir).resolve()

    # Filesystem & containment check
    try:
        if not abs_path.is_file() or not abs_path.is_relative_to(story_dir):
            logger.warning("/api/resource file missing or outside story_dir: file=%s story_dir=%s exists=%s", abs_path, story_dir, abs_path.exists())
            raise ValueError
    except AttributeError:
        if not abs_path.is_file() or str(abs_path).find(str(story_dir)) != 0:
            logger.warning("/api/resource forbidden path: file=%s story_dir=%s exists=%s", abs_path, story_dir, abs_path.exists())
            raise HttpError(403, "Forbidden")

    async def _iter_file_async(path: Path, chunk_size: int = 8192):
        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    mime, _ = mimetypes.guess_type(str(abs_path))
    resp = StreamingHttpResponse(_iter_file_async(abs_path), content_type=mime or "application/octet-stream")
    resp["Content-Disposition"] = f'attachment; filename="{abs_path.name}"'
    logger.info("/api/resource success: user=%s task=%s url=%s file=%s", user.id, task.id, str(rel), str(abs_path))
    return resp


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

    data = LoginOut(access_token=access_token).model_dump()
    response = api.create_response(request, data, status=200)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "REFRESH_COOKIE_SECURE", False),
        max_age=getattr(settings, "REFRESH_TOKEN_LIFETIME", 7 * 24 * 3600),
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
    wf_ver = (payload.workflow_version or "default").strip().lower()
    task = Task.objects.create(
        user=user,
        topic=payload.topic,
        main_role=payload.main_role or "",
        scene=payload.scene or "",
        status="pending",
        current_segment=0,
        workflow_version=wf_ver or "default",
    )
    task.ensure_story_dir()
    if wf_ver == "videogen":
        TaskSegment.objects.create(task=task, segment_id=1, name="VideoGen", status="pending")
    else:
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


@api.get("/task/{task_id}/resource")
def task_resource(request: HttpRequest, task_id: int, segmentId: int):
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")

    if task.current_segment < segmentId:
        raise HttpError(400, "Segment not completed yet")

    base_dir = Path(settings.BASE_DIR).resolve()

    urls_db = list(Resource.objects.filter(task=task, segment_id=segmentId).values_list("path", flat=True))
    if not urls_db:
        raise HttpError(404, "No resources for this segment")

    urls: List[str] = []
    for p in urls_db:
        try:
            pp = Path(p)
            if pp.is_absolute():
                try:
                    rel = Path(p).resolve().relative_to(base_dir)
                    urls.append(rel.as_posix())
                except Exception:
                    s = str(pp); bs = str(base_dir)
                    if s.startswith(bs):
                        urls.append(s[len(bs):].lstrip("/\\"))
                    else:
                        urls.append(pp.as_posix())
            else:
                urls.append(pp.as_posix())
        except Exception:
            continue

    if not urls:
        raise HttpError(404, "No resources for this segment")

    payload = {"segmentId": int(segmentId), "urls": urls}
    return api.create_response(request, payload, status=200)


@api.post("/task/{task_id}/execute/{segmentId}", response={200: ExecuteOut})
def execute_segment(request: HttpRequest, task_id: int, segmentId: int, redo: bool = False):
    from django.utils import timezone

    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")

    if redo and segmentId <= task.current_segment:
        running_exists = task.segments.filter(status="running").exists()
        if running_exists:
            raise HttpError(409, "Task is running, retry later")
        _prepare_redo(task, segmentId)
        task.refresh_from_db()

    if segmentId != task.current_segment + 1:
        raise HttpError(400, "Segment cannot be executed out of order")

    task.ensure_story_dir()
    seg = task.segments.filter(segment_id=segmentId).first()
    if not seg:
        raise HttpError(400, "Unknown segment")

    if seg.status == "running":
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
        from .tasks import execute_task_segment
        async_res = execute_task_segment.delay(task.id, segmentId)
        async_id = async_res.id

    data = ExecuteOut(accepted=True, celery_task_id=async_id, message="Execution queued")
    return api.create_response(request, data.model_dump(), status=202)


# --- Convenience endpoints for direct T2V (videogen) workflow ---
@api.post("/videogen/new", response={200: TaskNewOut})
def videogen_new(request: HttpRequest, payload: TaskNewIn):
    user = require_user(request)
    task = Task.objects.create(
        user=user,
        topic=payload.topic,  # used as prompt
        main_role=payload.main_role or "",
        scene=payload.scene or "",
        status="pending",
        current_segment=0,
        workflow_version="videogen",
    )
    task.ensure_story_dir()
    TaskSegment.objects.create(task=task, segment_id=1, name="VideoGen", status="pending")
    return TaskNewOut(task_id=task.id)


@api.post("/videogen/{task_id}/execute", response={200: ExecuteOut})
def videogen_execute(request: HttpRequest, task_id: int, payload: Optional[T2VExecuteIn] = None, redo: bool = False):
    from django.utils import timezone
    user = require_user(request)
    task = Task.objects.filter(id=task_id, user=user).first()
    if not task:
        raise HttpError(404, "Task not found")
    if (task.workflow_version or "default").lower() != "videogen":
        raise HttpError(400, "Not a videogen task")

    segmentId = 1
    if redo and segmentId <= task.current_segment:
        running_exists = task.segments.filter(status="running").exists()
        if running_exists:
            raise HttpError(409, "Task is running, retry later")
        _prepare_redo(task, segmentId)
        task.refresh_from_db()

    if segmentId != task.current_segment + 1:
        raise HttpError(400, "Segment cannot be executed out of order")

    task.ensure_story_dir()
    seg = task.segments.filter(segment_id=segmentId).first()
    if not seg:
        raise HttpError(400, "Unknown segment")

    # Merge overrides into metadata_json for the worker to pick up
    if payload is not None:
        meta = seg.metadata_json or {}
        for k, v in payload.model_dump(exclude_none=True).items():
            meta[k] = v
        seg.metadata_json = meta

    if seg.status == "running":
        async_id = None
    else:
        seg.status = "running"
        if not seg.started_at:
            seg.started_at = timezone.now()
        seg.error_message = ""
        seg.save(update_fields=["status", "started_at", "error_message", "metadata_json"])
        if task.status in ("pending", "failed"):
            task.status = "running"
            task.save(update_fields=["status"])
        from .tasks import execute_task_segment
        async_res = execute_task_segment.delay(task.id, segmentId)
        async_id = async_res.id

    data = ExecuteOut(accepted=True, celery_task_id=async_id, message="Execution queued")
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
