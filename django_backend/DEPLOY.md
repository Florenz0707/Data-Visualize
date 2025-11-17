# 部署指南（Windows + WSL 与 Linux）

本指南面向在 Windows+WSL 或原生 Linux 上运行 Django（ASGI）+ Celery + Redis 的环境。涵盖环境准备、启动顺序、验证方法与常见问题排查。请在阅读前先通读 README.md 了解项目功能与组件。

---

## 一、总体架构
- Django（ASGI）：提供 REST API 与 WebSocket 网关（Channels）
- Celery：执行异步任务（Redis 作为 broker 与 result backend）
- Redis：消息队列与 Pub/Sub（WebSocket 通知转发）
- 生成资源：默认写入项目内 django_backend/generated_stories

建议：Django、Celery、Redis 放在同一 Linux 栈（同机/容器/WSL 内）最稳定。

---

## 二、Linux 部署（推荐）

### 2.1 前置条件
- Linux 发行版（Ubuntu 20.04+/Debian/CentOS 等）
- Python 3.10+（项目当前 requires-python: ">=3.13"，请以实际环境为准）
- 可选：Nginx 作为反向代理（生产）

### 2.2 系统依赖
```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
  ffmpeg libsndfile1 redis-server
```

### 2.3 获取代码并创建虚拟环境
```bash
# 建议放在非 root 家目录
mkdir -p ~/apps && cd ~/apps
# 假设已将仓库放到此处
# git clone <repo> django_backend
cd django_backend
python3 -m venv .venv
source .venv/bin/activate
```

### 2.4 安装依赖
- 使用 uv（推荐）：
```bash
# 如未安装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```
- 或使用 pip：
```bash
pip install -U pip
pip install -e .
```

### 2.5 配置环境变量
- 可在 config/.env 写入（settings.py 会自动尝试加载）：
```
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
REDIS_URL=redis://localhost:6379/0
DJANGO_SECRET_KEY=<your-secret>
# 可选：ACCESS_TOKEN_LIFETIME、REFRESH_TOKEN_LIFETIME 等
```

- Redis（本机）默认安装后即监听 6379，无需额外配置。生产建议：/etc/redis/redis.conf 中设定
  - timeout 0
  - tcp-keepalive 300

### 2.6 初始化数据库
```bash
python manage.py migrate
```

### 2.7 启动顺序与运行命令
1) 启动 Redis（系统服务）：
```bash
sudo systemctl enable --now redis-server
# 验证
redis-cli ping
```

2) 启动 Celery worker：
```bash
source .venv/bin/activate
celery -A django_backend worker --loglevel=INFO --concurrency=2 -Ofair
```

3) 启动 ASGI（Uvicorn 或 Daphne）：
```bash
# Uvicorn（开发/生产均可，生产建议配合 Nginx）
uvicorn django_backend.asgi:application --host 0.0.0.0 --port 8000 --log-level info

# 或 Daphne
# daphne -b 0.0.0.0 -p 8000 django_backend.asgi:application
```

### 2.8 可选：systemd 服务示例
- /etc/systemd/system/celery.service
```
[Unit]
Description=Celery Worker
After=network.target redis-server.service

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/apps/django_backend
Environment="PATH=/home/YOUR_USER/apps/django_backend/.venv/bin"
ExecStart=/home/YOUR_USER/apps/django_backend/.venv/bin/celery -A django_backend worker --loglevel=INFO --concurrency=2 -Ofair
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- /etc/systemd/system/uvicorn.service
```
[Unit]
Description=Uvicorn ASGI Server
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/apps/django_backend
Environment="PATH=/home/YOUR_USER/apps/django_backend/.venv/bin"
ExecStart=/home/YOUR_USER/apps/django_backend/.venv/bin/uvicorn django_backend.asgi:application --host 0.0.0.0 --port 8000 --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并查看状态：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now celery.service uvicorn.service
sudo systemctl status celery.service uvicorn.service
```

### 2.9 Nginx 反向代理（可选）
```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## FFmpeg 配置要求与验证

本项目的视频合成（第5环节）依赖 ffmpeg。请确保服务器上已正确安装并且可被运行用户访问。

- 安装（Ubuntu/Debian）：
  - sudo apt update && sudo apt install -y ffmpeg
- 安装（CentOS/RHEL）：
  - sudo dnf install -y epel-release && sudo dnf install -y ffmpeg
- 安装（Windows 开发）：
  - 从 https://www.gyan.dev/ffmpeg/builds/ 下载 “release full” 压缩包；解压后将 bin 目录加入系统 PATH（如 C:\ffmpeg\bin）。
  - 重新打开终端，确保 `ffmpeg -version` 可用。

- 验证：
  - 运行 `ffmpeg -version`，应能输出版本信息。
  - MoviePy 写文件时会调用 ffmpeg；若 PATH 未包含 ffmpeg，可为 MoviePy 设置环境变量 IMAGEIO_FFMPEG_EXE 指向 ffmpeg 可执行文件：
    - Linux/WSL：export IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
    - Windows PowerShell：$env:IMAGEIO_FFMPEG_EXE = "C:\\ffmpeg\\bin\\ffmpeg.exe"

- 编解码器建议：
  - 视频：libx264（默认）；音频：aac。打包时 MoviePy 会使用这些编码器。
  - 若系统 ffmpeg 构建缺少 aac，请安装具备 aac 的发行版或改用 libmp3lame（同时修改代码/配置）。

- 性能与稳定性：
  - 建议在服务器上使用较新版本 ffmpeg（>=4.2）。
  - 可在配置中调节写出线程数（threads）与 fps、分辨率（size）以平衡质量与性能。

- 常见问题：
  - FileNotFoundError: ffmpeg：未安装或 PATH 未配置，参照上方安装与环境变量。
  - BrokenPipeError/编码失败：检查磁盘空间、权限、以及 ffmpeg 是否支持所需编码器。
  - Windows 路径含空格：确保 IMAGEIO_FFMPEG_EXE 用引号包裹完整路径。

---

## 三、Windows + WSL 开发/准生产（原文）

本节为原有指南（保留）。若在 Windows 运行 Django/Celery、在 WSL 中运行 Redis，请参考：

1) WSL 中安装与启动 Redis
- sudo apt install -y redis-server
- redis-server 或 sudo redis-server --daemonize yes

2) Windows 侧安装依赖并启动服务
- Python venv + pip/uv 安装
- Celery（Windows 上建议 threads/solo）
  - celery -A django_backend worker --loglevel=INFO --pool=threads --concurrency=2 -Ofair
- ASGI（Uvicorn）
  - uvicorn django_backend.asgi:application --host 127.0.0.1 --port 8000 --reload

3) 注意事项
- 跨栈（Windows↔WSL）长连接可能更易断开，建议最终迁移到单一 Linux 栈。
- 保持路径一致性，确保 GENERATED_ROOT 双侧可读写。

---

## 四、连通性与功能验证
- Redis 连通：`redis-cli ping` → PONG
- Celery 自检：`celery -A django_backend inspect ping`
- 登录→建任务→逐段执行（1..5），观察 202 返回与 WS 通知
- 资源下载接口验证：单文件/ZIP 下载

---

## 五、常见问题排查
- 断线重连与任务中断：本项目已在 settings.py 中启用心跳、健康检查与任务丢失防护；建议在同一 Linux 栈内运行。
- 依赖缺失：音视频/语音任务需要 ffmpeg、libsndfile 等库
- 权限问题：生成目录需可写；systemd 服务需指向正确的 venv PATH
- WebSocket 失败：确认使用 ASGI 服务器（Uvicorn/Daphne）与正确的 token

---

## 六、命令速查
- 迁移数据库：`python manage.py migrate`
- 启动 Celery：`celery -A django_backend worker --loglevel=INFO --concurrency=2 -Ofair`
- 启动 ASGI（Uvicorn）：`uvicorn django_backend.asgi:application --host 0.0.0.0 --port 8000`
- 订阅 Redis 通知：`redis-cli SUBSCRIBE "user:{user_id}"`
