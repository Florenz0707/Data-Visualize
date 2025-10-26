"""
Django Story Platform - 项目初始化
"""
import os
import django
from django.core.wsgi import get_wsgi_application

# 设置Django设置模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# 初始化Django
django.setup()

# 导入Celery应用
from core.celery import app as celery_app

__all__ = ['celery_app']
