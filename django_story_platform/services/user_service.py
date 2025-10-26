"""
Django Story Platform - 用户业务服务
"""
import logging
from typing import Dict, Any, Optional
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from models import User, NotificationSettings


class UserService:
    """用户服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def create_user(self, user_data: Dict[str, Any]) -> User:
        """创建用户"""
        self.logger.info(f"Creating user: {user_data.get('username', 'Unknown')}")
        
        # 验证密码
        password = user_data.pop('password')
        validate_password(password)
        
        # 创建用户
        user = User.objects.create_user(
            password=password,
            **user_data
        )
        
        # 创建默认通知设置
        NotificationSettings.objects.create(
            user=user,
            email_notifications=True,
            push_notifications=True,
            story_completed_notify=True,
            story_failed_notify=True,
            progress_notify=False
        )
        
        self.logger.info(f"User created with ID: {user.id}")
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """用户认证"""
        try:
            user = authenticate(username=username, password=password)
            if user and user.is_active:
                self.logger.info(f"User authenticated: {user.username}")
                return user
            else:
                self.logger.warning(f"Authentication failed for user: {username}")
                return None
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return None
    
    def update_user_profile(self, user: User, profile_data: Dict[str, Any]) -> User:
        """更新用户资料"""
        self.logger.info(f"Updating profile for user {user.id}")
        
        # 更新字段
        for field, value in profile_data.items():
            if hasattr(user, field) and field not in ['id', 'password', 'date_joined']:
                setattr(user, field, value)
        
        user.save()
        
        self.logger.info(f"Profile updated for user {user.id}")
        return user
    
    def change_password(self, user: User, old_password: str, new_password: str) -> bool:
        """修改密码"""
        try:
            # 验证旧密码
            if not user.check_password(old_password):
                self.logger.warning(f"Invalid old password for user {user.id}")
                return False
            
            # 验证新密码
            validate_password(new_password)
            
            # 设置新密码
            user.set_password(new_password)
            user.save()
            
            self.logger.info(f"Password changed for user {user.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Password change failed for user {user.id}: {e}")
            return False
    
    def get_user_stats(self, user: User) -> Dict[str, Any]:
        """获取用户统计信息"""
        stats = {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'stories_count': user.stories.count(),
            'completed_stories_count': user.stories.filter(status='completed').count(),
            'date_joined': user.date_joined,
            'last_login': user.last_login,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
        }
        
        return stats
    
    def send_welcome_email(self, user: User) -> bool:
        """发送欢迎邮件"""
        try:
            subject = "欢迎加入故事平台！"
            message = f"""
亲爱的 {user.username}，

欢迎您加入故事平台！我们很高兴您成为我们的一员。

在这里，您可以：
- 创建和分享您的故事
- 使用AI技术生成多媒体内容
- 与其他用户交流创作心得

如果您有任何问题，请随时联系我们的客服团队。

祝您使用愉快！

故事平台团队
            """.strip()
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            
            self.logger.info(f"Welcome email sent to user {user.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send welcome email: {e}")
            return False
    
    def deactivate_user(self, user: User) -> bool:
        """停用用户"""
        try:
            user.is_active = False
            user.save()
            
            self.logger.info(f"User {user.id} deactivated")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to deactivate user {user.id}: {e}")
            return False
    
    def activate_user(self, user: User) -> bool:
        """激活用户"""
        try:
            user.is_active = True
            user.save()
            
            self.logger.info(f"User {user.id} activated")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to activate user {user.id}: {e}")
            return False
