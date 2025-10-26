"""
Django Story Platform - 用户API接口
"""
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
import logging

from models import User
from api.serializers.user_serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    UserProfileSerializer, PasswordChangeSerializer
)

logger = logging.getLogger(__name__)


class UserRegistrationView(generics.CreateAPIView):
    """用户注册视图"""
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info(f"New user registered: {user.username}")
            
            return Response({
                'message': 'User created successfully',
                'user_id': user.id,
                'username': user.username
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """用户登录视图"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({
                'error': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        if user:
            if user.is_active:
                login(request, user)
                serializer = UserSerializer(user)
                logger.info(f"User logged in: {user.username}")
                
                return Response({
                    'message': 'Login successful',
                    'user': serializer.data
                })
            else:
                return Response({
                    'error': 'Account is disabled'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)


class UserLogoutView(APIView):
    """用户登出视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        logger.info(f"User logged out: {request.user.username}")
        logout(request)
        return Response({'message': 'Logout successful'})


class UserProfileView(generics.RetrieveUpdateAPIView):
    """用户资料视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserProfileSerializer


class PasswordChangeView(APIView):
    """密码修改视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            logger.info(f"Password changed for user: {user.username}")
            
            return Response({'message': 'Password changed successfully'})
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_stats(request):
    """获取用户统计信息"""
    user = request.user
    
    stats = {
        'user_id': user.id,
        'username': user.username,
        'stories_count': user.stories_count,
        'completed_stories_count': user.completed_stories_count,
        'date_joined': user.date_joined,
        'last_login': user.last_login,
    }
    
    return Response(stats)
