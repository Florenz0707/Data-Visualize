# Django Story Platform

基于Django的多模态故事生成平台，采用分层架构设计。

## 🏗️ 项目架构

### 技术层次划分

```
django_story_platform/
├── models/                    # 📊 数据模型层
│   ├── user_models.py        # 用户相关模型
│   ├── story_models.py       # 故事相关模型
│   ├── media_models.py       # 媒体相关模型
│   └── notification_models.py # 通知相关模型
├── api/                      # 🌐 API接口层
│   ├── user_api.py          # 用户API
│   ├── story_api.py         # 故事API
│   ├── media_api.py         # 媒体API
│   ├── notification_api.py  # 通知API
│   └── serializers/          # 序列化器
├── services/                 # 🔧 业务服务层
│   ├── user_service.py      # 用户业务逻辑
│   ├── story_service.py     # 故事业务逻辑
│   ├── media_service.py     # 媒体业务逻辑
│   └── notification_service.py # 通知业务逻辑
├── agents/                   # 🤖 AI代理层
│   ├── base_agent.py        # 代理基类
│   ├── story_agent.py       # 故事生成代理
│   ├── image_agent.py       # 图像生成代理
│   ├── speech_agent.py      # 语音生成代理
│   └── video_agent.py       # 视频合成代理
├── core/                     # ⚙️ 核心配置
│   ├── settings.py          # Django设置
│   ├── urls.py              # URL路由
│   ├── wsgi.py              # WSGI配置
│   ├── asgi.py              # ASGI配置
│   └── celery.py            # Celery配置
├── tasks/                    # 📋 异步任务
│   ├── story_tasks.py       # 故事相关任务
│   ├── media_tasks.py       # 媒体相关任务
│   └── notification_tasks.py # 通知相关任务
├── static/                   # 📁 静态文件
├── media/                    # 📁 媒体文件
├── templates/                # 📁 模板文件
├── manage.py                 # Django管理脚本
├── requirements.txt          # 项目依赖
└── README.md                 # 项目文档
```

## 🎯 架构优势

### 1. **技术层次清晰**
- **数据模型层**：统一管理所有数据模型
- **API接口层**：提供RESTful API接口
- **业务服务层**：封装核心业务逻辑
- **AI代理层**：处理AI生成任务
- **核心配置层**：Django项目配置

### 2. **业务模块通过文件名区分**
- `user_*`：用户相关功能
- `story_*`：故事相关功能
- `media_*`：媒体相关功能
- `notification_*`：通知相关功能

### 3. **职责分离明确**
- **模型层**：数据定义和关系
- **API层**：HTTP请求处理
- **服务层**：业务逻辑实现
- **代理层**：AI功能封装
- **任务层**：异步任务处理

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
export SECRET_KEY="your-secret-key"
export DEBUG=True
export DB_NAME="story_platform"
export DB_USER="postgres"
export DB_PASSWORD="password"
export DB_HOST="localhost"
export DB_PORT="5432"
```

### 3. 数据库迁移
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. 创建超级用户
```bash
python manage.py createsuperuser
```

### 5. 启动服务
```bash
# 启动Django开发服务器
python manage.py runserver

# 启动Celery worker
celery -A core worker --loglevel=info

# 启动Celery beat（定时任务）
celery -A core beat --loglevel=info
```

## 📚 核心功能

### 1. **用户管理**
- 用户注册/登录
- 用户资料管理
- 权限控制

### 2. **故事生成**
- 多模态故事生成
- 实时进度跟踪
- 异步任务处理

### 3. **媒体管理**
- 图像生成
- 语音合成
- 视频合成
- 文件管理

### 4. **通知系统**
- 实时通知
- WebSocket支持
- 邮件通知

## 🔧 技术栈

- **后端框架**：Django 4.2 + Django REST Framework
- **数据库**：PostgreSQL
- **异步任务**：Celery + Redis
- **WebSocket**：Django Channels
- **AI框架**：PyTorch + Transformers
- **图像处理**：Pillow + OpenCV
- **音频处理**：Librosa + SoundFile
- **视频处理**：MoviePy

## 📖 API文档

### 用户API
- `POST /api/v1/users/register/` - 用户注册
- `POST /api/v1/users/login/` - 用户登录
- `POST /api/v1/users/logout/` - 用户登出
- `GET /api/v1/users/profile/` - 获取用户资料
- `PUT /api/v1/users/profile/` - 更新用户资料

### 故事API
- `GET /api/v1/stories/` - 获取故事列表
- `POST /api/v1/stories/` - 创建故事
- `GET /api/v1/stories/{id}/` - 获取故事详情
- `PUT /api/v1/stories/{id}/` - 更新故事
- `DELETE /api/v1/stories/{id}/` - 删除故事
- `GET /api/v1/stories/{id}/status/` - 获取故事状态
- `GET /api/v1/stories/{id}/download/` - 下载故事视频

## 🎨 前端集成

### WebSocket连接
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/story-progress/');
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Progress update:', data);
};
```

### API调用示例
```javascript
// 创建故事
const response = await fetch('/api/v1/stories/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Token your-token'
    },
    body: JSON.stringify({
        topic: '一个关于友谊的故事',
        main_role: '小明',
        scene: '学校'
    })
});
```

## 🔒 安全考虑

- 用户认证和授权
- CSRF保护
- CORS配置
- 输入验证
- 文件上传安全

## 📈 性能优化

- 数据库查询优化
- 缓存策略
- 异步任务处理
- 静态文件CDN
- 图片压缩

## 🐛 调试和日志

- Django调试模式
- 详细日志记录
- 错误追踪
- 性能监控

## 📝 开发规范

- 代码格式化：Black
- 代码检查：Flake8
- 测试框架：Pytest
- 文档生成：自动生成API文档

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 📄 许可证

MIT License
