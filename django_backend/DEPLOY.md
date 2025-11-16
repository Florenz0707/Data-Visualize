# 部署指南（Windows + WSL）

本指南面向在 Windows 主机上运行 Django/Celery、在 WSL（建议 Ubuntu，WSL2）中运行 Redis 的开发/准生产环境。涵盖环境准备、启动顺序、验证方法与常见问题排查。请在阅读前先通读 README.md 了解项目功能与组件。

一、总体架构
- Windows 主机：
  - Python 虚拟环境
  - Django（ASGI 模式）
  - Celery worker（Windows 推荐使用 solo 池）
- WSL（Ubuntu 例）：
  - Redis（作为 Celery broker + result backend，同时用于 Pub/Sub 通知）

二、前置条件
- Windows 10/11 + WSL2（推荐）
- 已安装 WSL 发行版（建议 Ubuntu）
- Git、Python 3.13+（在 Windows 侧）
- 可选：Node/npm（若使用 wscat 测试 WebSocket）

三、克隆与目录结构
- 在 Windows 上克隆仓库。
- 主要服务端项目路径即该目录。

四、WSL 中安装与启动 Redis
1) 打开 WSL 终端（Ubuntu）：
- sudo apt update
- sudo apt install -y redis-server

2) 启动 Redis（二选一）
- 前台启动（便于观察日志）：
  - redis-server
- 后台守护（未启用 systemd 的常见方式）：
  - sudo redis-server --daemonize yes

3) 基本验证（在 WSL 内）：
- redis-cli ping → PONG
- ss -lntp | grep 6379 → 确认 6379 端口监听

说明：WSL2 默认支持 localhost 端口直通，Windows 可用 127.0.0.1:6379 连接 WSL 的 Redis。

五、Windows 侧安装 Python 依赖
1) 打开 PowerShell，进入项目根目录。

2) 创建并激活虚拟环境：
- python -m venv .venv
- .\.venv\Scripts\activate

3) 安装依赖（任选其一）
- pip install -U pip
- pip install -e .
- 或使用 uv：
  - uv venv（首次）
  - .\.venv\Scripts\activate
  - uv sync

4) 可选安装 ASGI 服务器：
- pip install daphne
- 或：pip install uvicorn[standard]

六、Django 配置核对与迁移
- 打开 django_backend/settings.py 核对：
  - CELERY_BROKER_URL=redis://localhost:6379/0
  - CELERY_RESULT_BACKEND=redis://localhost:6379/1
  - REDIS_URL=redis://localhost:6379/0
  - INSTALLED_APPS 包含 channels、django_celery_results
  - CHANNEL_LAYERS.default 指向 REDIS_URL
- 迁移数据库：
  - python manage.py migrate

七、启动顺序（推荐）
1) 启动 Redis（WSL）
- 见第四部分。

2) 启动 Celery（Windows）
- Windows 上建议使用 solo 池：
  - celery -A django_backend worker -l info -P solo --concurrency 1
- 如需简化命令，可在 django_backend/celery.py 中检测 os.name=="nt" 时自动设置 app.conf.worker_pool="solo"。

3) 启动 ASGI 服务器（Windows，推荐 Uvicorn）
- 开发调试（热重载 + 详细日志）：
  - uvicorn django_backend.asgi:application --host 127.0.0.1 --port 8000 --reload --log-level debug
- 普通运行：
  - uvicorn django_backend.asgi:application --host 127.0.0.1 --port 8000

说明：
- 使用 ASGI 服务器后，不要再同时运行 runserver 占用相同端口以免冲突。
- HTTP API 前缀为 /api，WebSocket 路径为 /ws/notifications。

八、连通性与功能验证
1) Redis 连通（Windows 侧）
- PowerShell：Test-NetConnection 127.0.0.1 -Port 6379 → True
- Python（在 venv 中）：
  - python -c "import redis; print(redis.from_url('redis://localhost:6379/0').ping())" → True

2) Celery 自检（Windows 侧）
- celery -A django_backend inspect ping → 输出含 \"ok\": \"pong\"

3) 脚本辅助（Test目录下）
- Windows Powershell: RedisTest.bat
- Git Bash：bash ThirdTest.sh（只发送 HTTP 请求，登录→建任务→触发执行段）

4) WebSocket 测试（实时通知）
- 获取 access_token：POST /api/login
- 连接：ws://127.0.0.1:8000/ws/notifications?token=<access_token>
  - wscat -c "ws://127.0.0.1:8000/ws/notifications?token=..."
- 触发执行：POST /api/task/{task_id}/execute/1
- 观察 WS 收到的 JSON 通知（segment_finished/segment_failed）

九、常见部署变体
A) 在 WSL 中运行 Celery worker（避免 Windows 多进程问题）
- 在 WSL 中为项目单独创建虚拟环境并安装依赖：
  - python3 -m venv .venv && source .venv/bin/activate
  - pip install -U pip && pip install -e .
- 切换到挂载路径（/mnt/d/...）项目根目录：
  - cd /mnt/d/_Files/_Lessons/Data-Visualize/django_backend
- 启动 worker：
  - celery -A django_backend worker -l info
- 注意：Django 可以继续在 Windows 上运行，任务通过 Redis 在 WSL worker 消费。磁盘路径建议统一（都从 /mnt/d/... 启动），以避免路径差异。

B) 全部在 WSL 中运行（更接近 Linux 生产环境）
- 在 WSL 中安装依赖、迁移和运行 daphne/uvicorn + Celery + Redis。
- Windows 仅用于编辑代码与浏览器访问。

十、环境变量与配置建议
- 生产/准生产建议使用 .env 注入敏感配置（API Key、模型配置）。
- 常用变量：
  - CELERY_BROKER_URL
  - CELERY_RESULT_BACKEND
  - REDIS_URL
  - ACCESS_TOKEN_LIFETIME、REFRESH_TOKEN_LIFETIME
- 根据需求调整 Django SECRET_KEY、ALLOWED_HOSTS、DEBUG 等。

十一、故障排查
- Windows Celery 报错 WinError 5：
  - 使用 -P solo --concurrency 1；或把 worker 放在 WSL。
- WebSocket 连接失败：
  - 确保使用 daphne/uvicorn；token 未过期；端口/防火墙放通。
- 收不到通知：
  - 确定 Celery 正在消费；在 WSL 里执行 redis-cli SUBSCRIBE "user:{user_id}" 观察是否发布；核对 REDIS_URL。
- 接口返回 401：
  - 确认 Authorization: Bearer <access_token> 头；或通过 /api/refresh 获取新 token。
- 视频/音频生成失败：
  - 查看 Celery worker 日志；核对 mm_story_agent.yaml、models.yaml 配置与对应模型、外部服务 API Key。

十二、日常运维建议
- 日志：
  - Celery worker 加 -l info/debug 观察队列与错误
  - ASGI 服务器日志关注 101/异常堆栈
- 备份：
  - 生成内容位于 generated_stories/<task_id>，如需持久化请定期备份
- 安全：
  - 仅在可信网络暴露 Redis；如需跨主机访问，务必加固访问策略
- 监控（可选）：
  - Flower 监控 Celery（pip install flower；flower -A django_backend）

十三、常用命令速查
- 启动 Celery（Windows，solo）：
  - celery -A django_backend worker -l info -P solo --concurrency 1
- 启动 ASGI（Daphne）：
  - daphne -p 8000 django_backend.asgi:application
- 启动 ASGI（Uvicorn）：
  - uvicorn django_backend.asgi:application --host 127.0.0.1 --port 8000
- Redis 订阅（WSL）：
  - redis-cli SUBSCRIBE "user:{user_id}"

附：快速自检脚本
- Windows：RedisTest.bat → 批处理版检测
- Git Bash：bash ThirdTest.sh → 仅 HTTP 调用验证异步入队与 202 返回
