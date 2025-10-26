"""
Django Story Platform - 用户API URL路由
"""
from django.urls import path
from . import user_api

urlpatterns = [
    path('register/', user_api.UserRegistrationView.as_view(), name='user-register'),
    path('login/', user_api.UserLoginView.as_view(), name='user-login'),
    path('logout/', user_api.UserLogoutView.as_view(), name='user-logout'),
    path('profile/', user_api.UserProfileView.as_view(), name='user-profile'),
    path('change-password/', user_api.PasswordChangeView.as_view(), name='user-change-password'),
    path('stats/', user_api.user_stats, name='user-stats'),
]
