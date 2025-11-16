# 接口文档 - MM-StoryAgent 最小后端原型

基础地址（Base URL）：http://127.0.0.1:8000

所有接口均挂载在 `/api/` 前缀下。

认证方案：在请求头 `Authorization` 中携带 Bearer 访问令牌（access token）；刷新令牌（refresh token）通过 HttpOnly Cookie 维护。

注意：这是最小可用原型。目前“执行（execute）”接口仅做模拟完成并写入占位文件；接入真实多代理（multi-agent）工作流后，可在不改变对外接口的情况下替换为真实产物。

---

## 约定
- 请求/响应的内容类型默认为 `application/json`，除非另有说明。
- 鉴权：受保护接口需在请求头中加入 `Authorization: Bearer <access_token>`。
- 刷新：`/api/login` 会通过响应头设置 HttpOnly 的 `refresh_token` Cookie（最小原型下可能依客户端而定）。
- 状态码：成功返回 200；4xx 为客户端错误；5xx 为服务端错误。

错误格式（Ninja/HttpError 默认）：
```json
{
  "detail": "错误信息"
}
```

---

## 1. 认证相关

### 1.1 注册
- 方法：POST
- 路径：`/api/register`
- 鉴权：否
- 请求体：
```json
{
  "username": "string",
  "password": "string"
}
```
- 响应 200：
```json
{
  "id": 1,
  "username": "string"
}
```
- 可能错误：
  - 400 用户名已存在

### 1.2 登录
- 方法：POST
- 路径：`/api/login`
- 鉴权：否
- 请求体：
```json
{
  "username": "string",
  "password": "string"
}
```
- 响应 200：
```json
{
  "access_token": "string",
  "token_type": "Bearer"
}
```
- 副作用：
  - 通过 `Set-Cookie: refresh_token=<token>; Path=/; HttpOnly; SameSite=Lax` 设置刷新令牌 Cookie（在最小原型中，不同客户端可能展示与保存方式不同）。
- 可能错误：
  - 401 用户名或密码错误

### 1.3 刷新访问令牌
- 方法：POST
- 路径：`/api/refresh`
- 鉴权：通过 HttpOnly Cookie 携带 `refresh_token`
- 请求体：无
- 响应 200：
```json
{
  "access_token": "string",
  "token_type": "Bearer"
}
```
- 可能错误：
  - 401 刷新令牌无效或过期

---

## 2. 工作流相关

### 2.1 获取工作流定义
- 方法：GET
- 路径：`/api/task/workflow`
- 鉴权：否
- 响应 200：
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

## 3. 任务相关

### 3.1 创建新任务
- 方法：POST
- 路径：`/api/task/new`
- 鉴权：需要 Bearer 访问令牌
- 请求体：
```json
{
  "topic": "string",
  "main_role": "string (可选)",
  "scene": "string (可选)"
}
```
- 响应 200：
```json
{
  "task_id": 123
}
```
- 副作用：
  - 创建任务并初始化存储目录：`generated_stories/<task_id>/`，创建 `image/` 与 `speech/` 子目录。

### 3.2 查询任务进度
- 方法：GET
- 路径：`/api/task/{task_id}/progress`
- 鉴权：需要 Bearer 访问令牌
- 响应 200：
```json
{
  "current_segment": 0,
  "status": "pending | running | completed | failed | deleted"
}
```
- 可能错误：
  - 404 任务不存在

### 3.3 获取我的任务列表
- 方法：GET
- 路径：`/api/task/mytasks`
- 鉴权：需要 Bearer 访问令牌
- 响应 200：
```json
{
  "task_ids": [1, 2, 3]
}
```

### 3.4 获取某环节资源
- 方法：GET
- 路径：`/api/task/{task_id}/resource`
- 查询参数：`segmentId`（整数）
- 鉴权：需要 Bearer 访问令牌
- 响应 200：
```json
{
  "resources": [
    "generated_stories/123/segment_3.txt"
  ]
}
```
- 可能错误：
  - 404 任务不存在
  - 400 该环节尚未完成

### 3.5 执行某个工作流环节
- 方法：POST
- 路径：`/api/task/{task_id}/execute/{segmentId}`
- 鉴权：需要 Bearer 访问令牌
- 行为说明：
  - 必须严格按顺序执行：`segmentId == current_segment + 1`。
  - 最小原型会模拟完成，并写入占位文件：`generated_stories/<task_id>/segment_<segmentId>.txt`。
  - 同时更新任务的 `current_segment` 和 `status`。
- 响应 200：
```json
{
  "accepted": true,
  "message": "Simulated execution completed"
}
```
- 可能错误：
  - 404 任务不存在
  - 400 非顺序执行 / 未知环节

### 3.6 删除任务
- 方法：DELETE
- 路径：`/api/task/{task_id}`
- 鉴权：需要 Bearer 访问令牌
- 响应 200：
```json
{
  "deleted": true
}
```
- 副作用：
  - 删除数据库记录，并移除 `generated_stories/<task_id>/` 目录。
- 可能错误：
  - 404 任务不存在

---

## 4. 认证细节
- 受保护接口需在请求头提供：`Authorization: Bearer <token>`。
- 刷新令牌通过 HttpOnly Cookie 储存，Cookie 名为 `refresh_token`。
- 令牌有效期（可在 `settings.py` 中配置）：
  - 访问令牌（access token）：默认 15 分钟
  - 刷新令牌（refresh token）：默认 7 天

---

## 5. Curl 示例

### 注册
```bash
curl -X POST http://127.0.0.1:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'
```

### 登录（使用 -i 查看响应头 Set-Cookie）
```bash
curl -i -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'
```

### 创建任务
```bash
ACCESS=<your_access_token>
curl -X POST http://127.0.0.1:8000/api/task/new \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"topic":"Magnet Mania","main_role":"Penny"}'
```

### 执行第 1 段
```bash
TASK_ID=<your_task_id>
curl -X POST http://127.0.0.1:8000/api/task/$TASK_ID/execute/1 \
  -H "Authorization: Bearer $ACCESS"
```

### 查询进度
```bash
curl -X GET http://127.0.0.1:8000/api/task/$TASK_ID/progress \
  -H "Authorization: Bearer $ACCESS"
```

### 获取第 3 段资源
```bash
curl -X GET "http://127.0.0.1:8000/api/task/$TASK_ID/resource?segmentId=3" \
  -H "Authorization: Bearer $ACCESS"
```

### 删除任务
```bash
curl -X DELETE http://127.0.0.1:8000/api/task/$TASK_ID \
  -H "Authorization: Bearer $ACCESS"
```

---

## 6. 说明
- 最小原型的执行接口会写入占位文件（segment_K.txt）；在接入真实多模态工作流后，将把真实产物（pages、图片、语音、视频等）记录到 Resource 表并返回相应路径。
- 工作流定义可通过 `WorkflowDefinition` 表进行扩展或切换；若数据库无记录，默认返回 5 步工作流。

