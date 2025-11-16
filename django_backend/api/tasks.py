from __future__ import annotations

import json
from pathlib import Path
from typing import List

import redis
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Task, TaskSegment, Resource


def _record_resources(task: Task, segment_id: int, paths: List[str], rtype: str):
    for p in paths:
        Resource.objects.create(task=task, segment_id=segment_id, type=rtype, path=str(p))


def _publish_notify(user_id: int, payload: dict):
    try:
        r = redis.from_url(getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))
        channel = f"user:{user_id}"
        r.publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Swallow notification errors to not fail task
        pass


@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def execute_task_segment(self, task_id: int, segment_id: int):
    # Make the task robust and idempotent-ish
    try:
        with transaction.atomic():
            task = Task.objects.select_for_update().filter(id=task_id).first()
            if not task:
                return
            # Validate ordering
            if segment_id != task.current_segment + 1:
                return
            seg = TaskSegment.objects.select_for_update().filter(task=task, segment_id=segment_id).first()
            if not seg:
                return
            # If already completed, no-op
            if seg.status == "completed":
                return
            # Mark running and started_at if not already
            seg.status = "running"
            seg.started_at = seg.started_at or timezone.now()
            seg.error_message = ""
            seg.save(update_fields=["status", "started_at", "error_message"])
            # Ensure task is running
            if task.status in ("pending", "failed"):
                task.status = "running"
                task.save(update_fields=["status"])

        # Execute outside of the open transaction (lazy import heavy deps here)
        from .services.workflow import WorkflowRunner
        runner = WorkflowRunner()
        story_dir = Path(task.story_dir or task.ensure_story_dir())

        created_resources: List[str] = []
        rtype = None
        # Segment execution
        if segment_id == 1:
            runner.run_story(story_dir, topic=task.topic, main_role=task.main_role, scene=task.scene)
            script_path = str(Path(story_dir) / "script_data.json")
            created_resources = [script_path]
            rtype = "json"
        elif segment_id == 2:
            images = runner.run_image(story_dir)
            created_resources = images
            rtype = "image"
        elif segment_id == 3:
            runner.run_split(story_dir)
            script_path = str(Path(story_dir) / "script_data.json")
            created_resources = [script_path]
            rtype = "json"
        elif segment_id == 4:
            wavs = runner.run_speech(story_dir)
            created_resources = wavs
            rtype = "audio"
        elif segment_id == 5:
            video = runner.run_video(story_dir)
            created_resources = [video]
            rtype = "video"
        else:
            raise ValueError("Unknown segment")

        with transaction.atomic():
            # Reload current objects under lock and persist results
            task = Task.objects.select_for_update().get(id=task_id)
            seg = TaskSegment.objects.select_for_update().get(task=task, segment_id=segment_id)
            if created_resources and rtype:
                _record_resources(task, segment_id, created_resources, rtype)
            seg.status = "completed"
            seg.ended_at = timezone.now()
            seg.save(update_fields=["status", "ended_at"])

            task.current_segment = segment_id
            task.status = "completed" if segment_id >= 5 else "running"
            # Ensure story_dir persisted
            if not task.story_dir:
                task.story_dir = str(story_dir)
            task.save(update_fields=["current_segment", "status", "story_dir"])

        # Notify success
        _publish_notify(
            user_id=task.user_id,
            payload={
                "type": "segment_finished",
                "task_id": task.id,
                "segment_id": segment_id,
                "status": "completed",
                "resources": created_resources,
            },
        )

    except Exception as e:
        # Persist failure state and notify
        with transaction.atomic():
            task = Task.objects.select_for_update().filter(id=task_id).first()
            if not task:
                return
            seg = TaskSegment.objects.select_for_update().filter(task=task, segment_id=segment_id).first()
            if seg:
                seg.status = "failed"
                seg.error_message = str(e)
                seg.ended_at = timezone.now()
                seg.save(update_fields=["status", "error_message", "ended_at"])
            task.status = "failed"
            task.save(update_fields=["status"])
        try:
            _publish_notify(
                user_id=task.user_id,
                payload={
                    "type": "segment_failed",
                    "task_id": task.id,
                    "segment_id": segment_id,
                    "status": "failed",
                    "error": str(e),
                },
            )
        except Exception:
            pass
