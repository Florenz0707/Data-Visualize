"""
Django Story Platform - 故事API URL路由
"""
from django.urls import path
from . import story_api

urlpatterns = [
    path('', story_api.StoryListCreateView.as_view(), name='story-list-create'),
    path('<uuid:pk>/', story_api.StoryDetailView.as_view(), name='story-detail'),
    path('generate/', story_api.StoryGenerationView.as_view(), name='story-generate'),
    path('<uuid:story_id>/status/', story_api.story_status, name='story-status'),
    path('<uuid:story_id>/download/', story_api.download_video, name='story-download'),
    path('<uuid:story_id>/regenerate/', story_api.regenerate_story, name='story-regenerate'),
]
