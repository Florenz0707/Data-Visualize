
# Data-Visualize / Story Agent

这是一个多模块项目，包含一个基于 Django 的后端（智能故事生成与服务）和一个使用 Vite + React/TypeScript 的前端（`story-agent-frontend`）。仓库包含用于模型代理、任务工作流、以及用于演示/调试的示例脚本。

主要目标：构建和演示一个可扩展的「故事代理（Story Agent）」平台，支持多模态能力（文本、图像、语音、音频等），并提供前端界面以交互和展示生成结果。

**主要特性**
- 后端：基于 Django，包含 API、任务队列、模型适配器和多模态代理实现。
- 前端：`story-agent-frontend` 使用 Vite + React + TypeScript，提供登录、Dashboard 与任务工作区视图。
- 示例与工具：`Test/` 中包含若干脚本用于调试（如 ffmpeg 测试脚本）。

**仓库结构（简要）**
- `django_backend/`：Django 项目源码、服务、模型适配器与配置（包含 `pyproject.toml`）。
- `story-agent-frontend/`：前端代码（Vite + React + TypeScript）。
- `docs/` 与 `README.md`：项目文档与说明。

开始之前（先决条件）
- Linux
- Python 3.8+（后端）
- Node.js 16+ / npm 或 pnpm / yarn（前端）
- 可选：Poetry（若使用 `pyproject.toml` 管理依赖）

快速开始 — 后端（本地开发）

1. 进入后端目录并创建虚拟环境（示例）：

```bash
cd django_backend
python -m venv .venv
source .venv/bin/activate
```

2. 安装依赖：

- 如果你使用 Poetry（仓库包含 `pyproject.toml`）：

```bash
poetry install
```

- 或使用 pip（如果存在 `requirements.txt`）：

```bash
pip install -r requirements.txt
```

3. 运行数据库迁移并启动开发服务器：

```bash
# 迁移（若使用 Django ORM）
python manage.py migrate

# 启动开发服务器（默认 8000 端口）
python manage.py runserver
```

4. API 文档与参考：后端目录下包含 `API_en-US.md` 与 `API_zh-CN.md`，查看接口与授权要求。

快速开始 — 前端（本地开发）

1. 安装依赖并启动开发服务器：

```bash
cd story-agent-frontend
npm install
# 或使用 pnpm / yarn: pnpm install 或 yarn
npm run dev
```

2. 打开浏览器访问 `http://localhost:5173`（Vite 默认端口，若被更改请参照终端输出）。

注意：前端默认会与后端 API 交互（通过配置的环境或 `lib/api.ts`），启动前请确保后端服务已按需运行，并根据 `src/context/AuthContext.tsx` 或 `src/lib/api.ts` 调整 API 路径与鉴权信息。

部署提示
- 后端部署：详见 `django_backend/DEPLOY.md`（包含系统依赖、服务启动顺序、systemd 示例与调试建议）。
- 前端部署（简要）：使用 `npm run build` 进行构建，然后把 `dist/` 部署到静态主机（如 Vercel、Netlify、或 Nginx）。仓库中 `story-agent-frontend/nginx.conf` 可作为参考。

开发与贡献
- 希望贡献请先 fork 仓库并创建 feature 分支。
- 提交说明请保持清晰（参见项目贡献指南，如无则在 PR 中说明变更）。

常见问题
- 如果启动前端时无法连接后端，请确认后端地址与端口在前端配置中正确设置，并且跨域（CORS）已在后端配置允许。

联系方式与许可
- 仓库根目录包含 `LICENSE`，请查看许可条款以确定使用与分发限制。
