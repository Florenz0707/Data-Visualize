"""
Django Story Platform - WebSocket消费者
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class StoryProgressConsumer(AsyncWebsocketConsumer):
    """故事进度WebSocket消费者"""
    
    async def connect(self):
        """连接WebSocket"""
        self.user = self.scope["user"]
        
        if self.user == AnonymousUser():
            await self.close()
            return
        
        self.user_group_name = f"user_{self.user.id}"
        
        # 加入用户组
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected for user {self.user.id}")
    
    async def disconnect(self, close_code):
        """断开WebSocket连接"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        logger.info(f"WebSocket disconnected for user {self.user.id}")
    
    async def receive(self, text_data):
        """接收WebSocket消息"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'message': 'pong'
                }))
            elif message_type == 'subscribe_story':
                story_id = text_data_json.get('story_id')
                if story_id:
                    await self.subscribe_story(story_id)
            elif message_type == 'unsubscribe_story':
                story_id = text_data_json.get('story_id')
                if story_id:
                    await self.unsubscribe_story(story_id)
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))
    
    async def subscribe_story(self, story_id):
        """订阅故事进度"""
        try:
            # 验证用户是否有权限访问该故事
            has_permission = await self.check_story_permission(story_id)
            if not has_permission:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'No permission to access this story'
                }))
                return
            
            # 加入故事组
            story_group_name = f"story_{story_id}"
            await self.channel_layer.group_add(
                story_group_name,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'subscribed',
                'story_id': story_id,
                'message': f'Subscribed to story {story_id}'
            }))
            
            logger.info(f"User {self.user.id} subscribed to story {story_id}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to story {story_id}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to subscribe to story'
            }))
    
    async def unsubscribe_story(self, story_id):
        """取消订阅故事进度"""
        try:
            story_group_name = f"story_{story_id}"
            await self.channel_layer.group_discard(
                story_group_name,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'unsubscribed',
                'story_id': story_id,
                'message': f'Unsubscribed from story {story_id}'
            }))
            
            logger.info(f"User {self.user.id} unsubscribed from story {story_id}")
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from story {story_id}: {e}")
    
    async def notification_message(self, event):
        """处理通知消息"""
        message = event['message']
        
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': message
        }))
    
    async def story_progress_update(self, event):
        """处理故事进度更新"""
        progress_data = event['progress']
        
        await self.send(text_data=json.dumps({
            'type': 'progress_update',
            'progress': progress_data
        }))
    
    async def story_completion(self, event):
        """处理故事完成通知"""
        completion_data = event['completion']
        
        await self.send(text_data=json.dumps({
            'type': 'story_completion',
            'completion': completion_data
        }))
    
    @database_sync_to_async
    def check_story_permission(self, story_id):
        """检查用户是否有权限访问故事"""
        try:
            from models import Story
            story = Story.objects.get(id=story_id, user=self.user)
            return True
        except Story.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Failed to check story permission: {e}")
            return False


class NotificationConsumer(AsyncWebsocketConsumer):
    """通知WebSocket消费者"""
    
    async def connect(self):
        """连接WebSocket"""
        self.user = self.scope["user"]
        
        if self.user == AnonymousUser():
            await self.close()
            return
        
        self.user_group_name = f"user_{self.user.id}"
        
        # 加入用户组
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Notification WebSocket connected for user {self.user.id}")
    
    async def disconnect(self, close_code):
        """断开WebSocket连接"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        logger.info(f"Notification WebSocket disconnected for user {self.user.id}")
    
    async def receive(self, text_data):
        """接收WebSocket消息"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'message': 'pong'
                }))
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Notification WebSocket receive error: {e}")
    
    async def notification_message(self, event):
        """处理通知消息"""
        message = event['message']
        
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': message
        }))
    
    async def notification_update(self, event):
        """处理通知更新"""
        notification_data = event['notification']
        
        await self.send(text_data=json.dumps({
            'type': 'notification_update',
            'notification': notification_data
        }))
