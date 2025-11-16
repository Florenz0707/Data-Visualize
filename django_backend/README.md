# MM-StoryAgent Backend

面向“多模态故事生成”的后端服务。提供从“创作脚本 → 生成图片 → 文本分段 → 语音合成 → 视频合成”的一键流水线，并支持登录鉴权、任务管理、异步执行与实时通知（Redis + WebSocket）。本项目适合需要快速搭建 AI 内容生产后台、并以 API 或 WebSocket 方式集成到前端应用的用户。

## 面向用户的核心价值

- 一键化生成：输入主题（可选主角/场景），自动完成完整的多模态内容生成流程。
- 任务可追踪：每个任务分为 5 个环节（Story/Image/Split/Speech/Video），可以按段执行与获取产物。
- 异步不阻塞：执行任务立即返回；后台完成后通过消息队列通知，大任务也能平滑体验。
- 实时通知：支持 Redis Pub/Sub 与 WebSocket 网关，前端可便捷订阅用户专属频道获取环节完成/失败提醒。

## 功能概览

- 用户与鉴权
  - 注册/登录（返回短期 Access Token，Cookie 中自动写入 Refresh Token）
  - 刷新 Access Token
- 任务管理
  - 创建任务（指定主题、主角、场景）
  - 查询任务列表与进度
  - 分段拉取资源（图片、音频、脚本 JSON、最终视频）
  - 删除任务（清理生成文件）
- 工作流执行（5 段）
  1. Story：生成故事文本，保存 script_data.json
  2. Image：生成每页故事对应图片
  3. Split：将文本按语音合成友好方式分段
  4. Speech：为每页/分段生成配音（wav）
  5. Video：合成最终视频（mp4）
- 异步与通知
  - Celery 异步任务：接口返回 202 Accepted，并给出 celery_task_id
  - Redis Pub/Sub：完成或失败后发布到频道 `user:{user_id}`
  - WebSocket 网关：`ws://<host>/ws/notifications?token=<access_token>` 实时转发消息到前端

## 典型使用流程（面向前端/客户端）

1. 注册/登录，获得 `access_token`
2. 创建任务，得到 `task_id`
3. 依次触发执行 1→5 段（每次调用返回 202，后台执行）
4. 订阅通知：
   - 方式 A：Redis 频道 `user:{user_id}`（调试/内网）
   - 方式 B：WebSocket `ws://<host>/ws/notifications?token=<access_token>`（推荐前端）
5. 某段完成后，收到消息（JSON）与资源路径，再调用接口拉取该段资源

示例通知（成功）

```
{
  "type": "segment_finished",
  "task_id": 101,
  "segment_id": 2,
  "status": "completed",
  "resources": ["generated_stories/101/image/p1.png", "..."]
}
```

失败时 `type` 为 `segment_failed` 并包含 `error` 字段。

## 快速开始（开发环境）

- 依赖：Python 3.13+、Redis（建议在 WSL2 中运行）、Celery、ASGI 服务器（daphne/uvicorn）
- 安装依赖
  - 使用 uv 或 pip 安装 pyproject.toml 中的依赖
- 数据库初始化
  - `python manage.py migrate`
- 启动服务
  1) 启动 Redis（WSL）
     - `redis-server`（或 `sudo redis-server --daemonize yes`）
  2) 启动 Celery（Windows 上推荐 solo 池）
     - `celery -A django_backend worker -l info -P solo --concurrency 1`
  3) 启动 ASGI 服务器（选择其一）
     - Daphne：`daphne -p 8000 django_backend.asgi:application`
     - Uvicorn：`uvicorn django_backend.asgi:application --host 127.0.0.1 --port 8000`

默认关键配置（可在 `django_backend/settings.py` 或环境变量中修改）

- `CELERY_BROKER_URL=redis://localhost:6379/0`
- `CELERY_RESULT_BACKEND=redis://localhost:6379/1`
- `REDIS_URL=redis://localhost:6379/0`

## API 速览（路径前缀 `/api`）

- `POST /register` 注册
- `POST /login` 登录（返回 `access_token`，并设置 `refresh_token` Cookie）
- `POST /refresh` 刷新 `access_token`
- `GET /task/workflow` 查看工作流段定义
- `POST /task/new` 创建任务（需要 `Authorization: Bearer <access_token>`）
- `GET /task/{task_id}/progress` 查询进度
- `GET /task/mytasks` 我的任务列表
- `GET /task/{task_id}/resource?segmentId=N` 获取该段的资源路径
- `POST /task/{task_id}/execute/{segmentId}` 触发执行某段（返回 202 + `celery_task_id`）
- `DELETE /task/{task_id}` 删除任务并清理资源

## WebSocket 网关（实时通知）

- 地址：`ws://127.0.0.1:8000/ws/notifications?token=<access_token>`
- 鉴权：查询参数 `token` 或 Header `Authorization: Bearer <token>`
- 消息：服务端监听 Redis 频道 `user:{user_id}` 并将消息 JSON 原样转发

## 命令行测试脚本

- `RedisTest.sh`（Git Bash）：本地 Redis 连接与 Celery 连通性测试（含 PING 与 Pub/Sub）
- `RedisTest.bat`（CMD/PowerShell）：Windows 批处理版 Redis 测试
- `ThirdTest.sh`（Git Bash）：纯 HTTP 请求压测链路
  - 登录 → 创建任务 → 触发执行段 → 返回 202 + `celery_task_id`

## 常见问题（FAQ）

- Windows 上 Celery 多进程报错（WinError 5）
  - 使用 `-P solo --concurrency 1` 启动 Celery，或在 `celery.py` 中检测 Windows 自动设置 solo 池。
- WebSocket 无法连接
  - 请使用 daphne/uvicorn 启动 ASGI，不要用 `runserver`。
  - 检查 `access_token` 是否过期，端口/防火墙是否放通。
- 收不到通知
  - 确认 Celery worker 正在运行、Redis 可连通。
  - 用 `redis-cli SUBSCRIBE "user:{user_id}"` 验证是否发布消息。

---
如需进一步接入前端示例、通知持久化（轮询）、或自定义工作流段配置，欢迎在 Issue 中提出需求。
