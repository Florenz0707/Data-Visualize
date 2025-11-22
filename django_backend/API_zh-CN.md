# 接口文档 - MM-StoryAgent 后端

Base URL: http://127.0.0.1:8000

所有接口统一挂载在 /api/ 之下。

鉴权：在请求头 Authorization 中传 Bearer 访问令牌；刷新令牌通过 HttpOnly Cookie 维护。

---

## 约定
- Content-Type: application/json（除非另有说明）。
- 鉴权：Authorization: Bearer <access_token>
- 状态码：200(OK)、202(已排队/异步执行)、4xx(客户端错误)、5xx(服务端错误)。
- 资源路径 urls 一律为相对项目根目录（BASE_DIR）的相对路径。

错误返回（示例）：
```json
{ "detail": "错误信息" }
```

---

## 1. 认证

### 1.1 注册
POST /api/register

请求体
```json
{ "username": "string", "password": "string" }
```
响应 200
```json
{ "id": 1, "username": "string" }
```

### 1.2 登录
POST /api/login

请求体
```json
{ "username": "string", "password": "string" }
```
响应 200
```json
{ "access_token": "string", "token_type": "Bearer" }
```
副作用：设置 HttpOnly refresh_token Cookie。

### 1.3 刷新访问令牌
POST /api/refresh

响应 200
```json
{ "access_token": "string", "token_type": "Bearer" }
```

---

## 2. 工作流

### 2.1 获取工作流定义
GET /api/task/workflow

响应 200
```json
[
  {"id": 1, "name": "Story"},
  {"id": 2, "name": "Image"},
  {"id": 3, "name": "Split"},
  {"id": 4, "name": "Speech"},
  {"id": 5, "name": "Video"}
]
```

---

## 3. 任务

### 3.1 新建任务
POST /api/task/new（鉴权）

请求体
```json
{ "topic": "string", "main_role": "string(可选)", "scene": "string(可选)" }
```
响应 200
```json
{ "task_id": 123 }
```

### 3.2 我的任务
GET /api/task/mytasks（鉴权）

响应 200
```json
{ "task_ids": [1,2,3] }
```

### 3.3 任务进度
GET /api/task/{task_id}/progress（鉴权）

响应 200
```json
{ "current_segment": 0, "status": "pending|running|completed|failed|deleted" }
```

### 3.4 执行某环节
POST /api/task/{task_id}/execute/{segmentId}?redo=true|false（鉴权）

说明
- 必须按顺序执行：segmentId == current_segment + 1。
- redo=true 且该环节已完成时，会回滚 >= segmentId 的产物与状态，并从该环节重新开始。
- 执行为异步（Celery），本接口返回 202。

响应 202
```json
{ "accepted": true, "celery_task_id": "string|null", "message": "Execution queued" }
```

### 3.5 列出某环节资源（相对路径）
GET /api/task/{task_id}/resource?segmentId=N（鉴权）

响应 200（统一结构）
```json
{ "segmentId": 4, "urls": ["generated_stories/123/speech/s1_1.wav", "..."] }
```
说明
- urls 始终为相对路径；如需下载，请使用下方单文件下载接口。

### 3.6 单文件下载
GET /api/resource?url=<相对路径>（鉴权）

说明
- url 必须是 /api/task/{task_id}/resource 返回过的相对路径。
- 后端将校验资源归属当前用户且文件位于该任务 story_dir 下。
- 成功返回流式附件（Content-Disposition: attachment）。

### 3.7 删除任务
DELETE /api/task/{task_id}（鉴权）

响应 200
```json
{ "deleted": true }
```

---

## 4. 文本转视频（独立工作流 videogen）

说明
- 该工作流与默认 5 段流程独立，直接从长文本或图片生成视频（单段）。
- 可选两种入口：
  1) 便捷入口：/api/videogen/new 与 /api/videogen/{task_id}/execute
  2) 通用入口：/api/task/new 时传 workflow_version="videogen"，随后 /api/task/{task_id}/execute/1 执行

### 4.1 创建 videogen 任务
POST /api/videogen/new（鉴权）

请求体
```json
{ "topic": "作为 prompt 的长文本描述", "main_role": "可选", "scene": "可选" }
```
响应 200
```json
{ "task_id": 123 }
```

说明：topic 字段将作为视频生成的文本提示（prompt）。

### 4.2 执行 videogen
POST /api/videogen/{task_id}/execute（鉴权）

请求体（全部可选，用于覆盖默认参数）
```json
{
  "prompt": "覆盖 topic 的文本提示",
  "model": "gen4_turbo",
  "ratio": "1280:720",
  "prompt_image_path": "./example.png",
  "prompt_image_data_uri": "data:image/png;base64,...",
  "width": 1280,
  "height": 720,
  "fps": 24,
  "duration": 5,
  "use_mock": false
}
```
说明
- 传入 prompt_image_path 或 prompt_image_data_uri 时走“图生视频（image_to_video）”；否则“文本生视频（text_to_video）”。
- use_mock=true 时本地生成占位视频，便于离线调试；生产建议 false。
- 执行为异步，返回 202：
```json
{ "accepted": true, "celery_task_id": "string|null", "message": "Execution queued" }
```

### 4.3 资源获取
- 列表：GET /api/task/{task_id}/resource?segmentId=1（鉴权）
- 下载：GET /api/resource?url=<相对路径>（鉴权）

### 4.4 通过通用入口创建 videogen（可选）
POST /api/task/new（鉴权）
```json
{ "topic": "string", "workflow_version": "videogen" }
```
随后执行：POST /api/task/{task_id}/execute/1

---

## 5. 提示 & 安全
- 资源路径为相对路径；不要传入绝对路径。服务端会校验归属与路径安全。
- redo=true 时，会删除相应环节之后的产物并重置状态，再从该环节重新执行。
- 可结合 WebSocket/Redis 订阅完成/失败通知，或通过 /progress 与 /resource 輪询。

---

## 5. 示例

```bash
ACCESS=<token>
TASK=<id>

# 执行第 1 段（Story）
curl -X POST "http://127.0.0.1:8000/api/task/$TASK/execute/1" -H "Authorization: Bearer $ACCESS"

# 重新执行第 2 段（Image）
curl -X POST "http://127.0.0.1:8000/api/task/$TASK/execute/2?redo=true" -H "Authorization: Bearer $ACCESS"

# 列出第 5 段（Video）的资源
curl -s "http://127.0.0.1:8000/api/task/$TASK/resource?segmentId=5" -H "Authorization: Bearer $ACCESS"
# => {"segmentId":5,"urls":["generated_stories/$TASK/output.mp4"]}

# 下载视频
curl -L -o output.mp4 "http://127.0.0.1:8000/api/resource?url=generated_stories/$TASK/output.mp4" -H "Authorization: Bearer $ACCESS"
```
