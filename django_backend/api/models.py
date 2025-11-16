from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from pathlib import Path
import shutil

class WorkflowDefinition(models.Model):
    version = models.CharField(max_length=32, unique=True)
    segments_json = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def get_active_segments():
        wf = WorkflowDefinition.objects.filter(is_active=True).order_by('-id').first()
        if wf and wf.segments_json:
            return wf.segments_json
        # default 5-segment workflow
        return [
            {"id": 1, "name": "Story"},
            {"id": 2, "name": "Image"},
            {"id": 3, "name": "Split"},
            {"id": 4, "name": "Speech"},
            {"id": 5, "name": "Video"},
        ]

class Task(models.Model):
    STATUS_CHOICES = (
        ("pending", "pending"),
        ("running", "running"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("deleted", "deleted"),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tasks")
    topic = models.CharField(max_length=512)
    main_role = models.CharField(max_length=256, blank=True, default="")
    scene = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    current_segment = models.IntegerField(default=0)
    workflow_version = models.CharField(max_length=32, blank=True, default="default")
    story_dir = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def ensure_story_dir(self):
        if not self.story_dir:
            root = Path(getattr(settings, 'GENERATED_ROOT', Path(settings.BASE_DIR).parent / 'generated_stories'))
            task_dir = (root / str(self.id))
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / 'image').mkdir(exist_ok=True)
            (task_dir / 'speech').mkdir(exist_ok=True)
            self.story_dir = str(task_dir)
            self.save(update_fields=["story_dir"])    
        return Path(self.story_dir)

    def purge_files(self):
        if self.story_dir:
            p = Path(self.story_dir)
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

class TaskSegment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="segments")
    segment_id = models.IntegerField()
    name = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="pending")
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

class Resource(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="resources")
    segment_id = models.IntegerField()
    type = models.CharField(max_length=32)
    path = models.CharField(max_length=512)
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

