# 多模态故事生成后端（用户指南）

本项目提供“一键式多模态故事生成”服务。用户输入主题（可选主角、场景），系统按流程自动完成：
1) 生成故事文本（Story）
2) 生成图片（Image）
3) 文本分段（Split）
4) 语音合成（Speech）
5) 视频合成（Video）

任务执行为异步：提交执行请求后立即返回，完成后通过通知（WebSocket/消息队列）提示，并可按段获取资源。

---

## 使用流程
1) 注册/登录，获得 access_token
2) 创建任务，得到 task_id（可填写：主题、主角、场景）
3) 按顺序逐段执行（1 → 5），每次执行返回 202（已排队）
4) 订阅通知（WebSocket）接收完成/失败消息
5) 每段完成后，使用资源下载接口直接获取该段文件（单文件或自动打包）

注意：
- 段必须按顺序执行（segmentId 必须是 current_segment + 1）
- 所有需要鉴权的接口，需在请求头携带 Authorization: Bearer <access_token>

---

## 通知（实时）
- WebSocket 地址：
  - ws://<host>/ws/notifications?token=<access_token>
- 收到的消息为 JSON：
  - 成功：
    {
      "type": "segment_finished",
      "task_id": 123,
      "segment_id": 2,
      "status": "completed",
      "resources": ["generated_stories/123/image/p1.png", "..."]
    }
  - 失败：
    {
      "type": "segment_failed",
      "task_id": 123,
      "segment_id": 2,
      "status": "failed",
      "error": "错误信息"
    }

---

## API 说明（功能、请求与响应）

所有接口前缀为 /api。

### 身份认证
- POST /api/register
  - 请求：{ "username": string, "password": string }
  - 响应：{ "id": number, "username": string }

- POST /api/login
  - 请求：{ "username": string, "password": string }
  - 响应：{ "access_token": string, "token_type": "Bearer" }
  - 备注：同时在 Cookie 写入 refresh_token（HttpOnly）

- POST /api/refresh
  - 请求：无（使用 Cookie 中的 refresh_token）
  - 响应：{ "access_token": string, "token_type": "Bearer" }

### 工作流定义
- GET /api/task/workflow
  - 响应：[{ "id": number, "name": string }]

### 任务管理
- POST /api/task/new（需鉴权）
  - 请求：{ "topic": string, "main_role"?: string, "scene"?: string }
  - 响应：{ "task_id": number }

- GET /api/task/mytasks（需鉴权）
  - 响应：{ "task_ids": number[] }

- GET /api/task/{task_id}/progress（需鉴权）
  - 响应：{ "current_segment": number, "status": "pending"|"running"|"completed"|"failed" }

- POST /api/task/{task_id}/execute/{segmentId}（需鉴权）
  - 作用：按顺序执行指定段（1..5）。提交后后台异步处理。
  - 响应（状态码 202）：
    {
      "accepted": true,
      "celery_task_id": string | null,
      "message": "Execution queued"
    }

- GET /api/task/{task_id}/resource?segmentId=N[&name=文件名]（需鉴权）
  - 作用：下载指定段资源。若指定 name 且文件存在则直接下载该文件；未指定 name 且该段只有一个文件则直接下载；若有多个文件则自动打包为 zip 返回。
  - 响应：文件下载（单文件：原始类型；多文件：application/zip，均带 Content-Disposition: attachment）

- DELETE /api/task/{task_id}（需鉴权）
  - 作用：删除任务并清理生成文件
  - 响应：{ "deleted": true }

### 独立：文本转视频（videogen）
- 该工作流与默认 5 段流程独立，直接从长文本或图片生成视频（单段）。
- 两种入口：
  1) 便捷入口：
     - POST /api/videogen/new（鉴权）
       - 请求：{ "topic": "作为 prompt 的长文本描述", "main_role"?: "string", "scene"?: "string" }
       - 响应：{ "task_id": number }
     - POST /api/videogen/{task_id}/execute（鉴权）
       - 请求（可选覆盖参数）：
         {
           "prompt": "覆盖 topic 的文本提示",
           "model": "gen4_turbo",
           "ratio": "1280:720",
           "prompt_image_path": "./example.png",
           "prompt_image_data_uri": "data:image/png;base64,...",
           "width": 1280, "height": 720, "fps": 24, "duration": 5,
           "use_mock": false
         }
       - 说明：传入 prompt_image_* 时走图生视频（image_to_video），否则文本生视频（text_to_video）。返回 202。
  2) 通用入口：
     - POST /api/task/new，传 { "topic": "...", "workflow_version": "videogen" }
     - 然后 POST /api/task/{task_id}/execute/1
- 资源获取：
  - GET /api/task/{task_id}/resource?segmentId=1（鉴权）
  - GET /api/resource?url=<相对路径>（鉴权）

---

## 段含义与返回资源
1) Story：生成故事文本，落盘 script_data.json；资源类型：json
2) Image：基于故事生成图片，保存在 image/；资源类型：image（png）
3) Split：将文本按语音合成友好方式分段，写回 script_data.json；资源类型：json
4) Speech：为每页/分段生成配音，保存在 speech/；资源类型：audio（wav）
5) Video：合成最终视频 output.mp4；资源类型：video（mp4）

---

## 使用要点
- 执行为异步：接口返回 202 表示已排队，完成后以通知消息告知
- 建议在执行前先订阅 WebSocket，以免错过即时消息
- 每段完成后再使用资源查询接口获取对应的文件路径

如需更详细的示例或前端集成建议，请联系维护者。
