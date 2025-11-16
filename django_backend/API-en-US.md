# API Documentation - MM-StoryAgent Minimal Backend Prototype

Base URL: http://127.0.0.1:8000

All API endpoints are mounted under the `/api/` prefix.

Auth scheme: Bearer access token in `Authorization` header; refresh token in HttpOnly cookie.

Note: This is a minimal prototype. The execute endpoints currently simulate completion and write stub files. Integration with real multi-agent workflow can replace the simulated logic transparently.

---

## Conventions
- Content-Type: application/json for request/response bodies unless specified.
- Authentication: provide `Authorization: Bearer <access_token>` for protected endpoints.
- Refresh: refresh token is set as an HttpOnly cookie by the login endpoint.
- Status codes: 200 on success; 4xx for client errors; 5xx for server errors.

Error format (typical Ninja/HttpError):
```json
{
  "detail": "Error message"
}
```

---

## 1. Auth Endpoints

### 1.1 Register
- Method: POST
- Path: `/api/register`
- Auth: None
- Request body:
```json
{
  "username": "string",
  "password": "string"
}
```
- Response 200:
```json
{
  "id": 1,
  "username": "string"
}
```
- Errors:
  - 400 Username already exists

### 1.2 Login
- Method: POST
- Path: `/api/login`
- Auth: None
- Request body:
```json
{
  "username": "string",
  "password": "string"
}
```
- Response 200:
```json
{
  "access_token": "string",
  "token_type": "Bearer"
}
```
- Side effects:
  - Sets `Set-Cookie: refresh_token=<token>; Path=/; HttpOnly; SameSite=Lax` (client may or may not display it in minimal prototype)
- Errors:
  - 401 Invalid credentials

### 1.3 Refresh Access Token
- Method: POST
- Path: `/api/refresh`
- Auth: Refresh token cookie
- Request: no body
- Response 200:
```json
{
  "access_token": "string",
  "token_type": "Bearer"
}
```
- Errors:
  - 401 Invalid refresh token

---

## 2. Workflow Endpoints

### 2.1 Get Workflow Definition
- Method: GET
- Path: `/api/task/workflow`
- Auth: None
- Response 200:
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

## 3. Task Endpoints

### 3.1 Create New Task
- Method: POST
- Path: `/api/task/new`
- Auth: Bearer access token
- Request body:
```json
{
  "topic": "string",
  "main_role": "string (optional)",
  "scene": "string (optional)"
}
```
- Response 200:
```json
{
  "task_id": 123
}
```
- Side effects:
  - Creates a task and initializes the storage directory: `generated_stories/<task_id>/` with subfolders `image/` and `speech/`.

### 3.2 Get Task Progress
- Method: GET
- Path: `/api/task/{task_id}/progress`
- Auth: Bearer access token
- Response 200:
```json
{
  "current_segment": 0,
  "status": "pending | running | completed | failed | deleted"
}
```
- Errors:
  - 404 Task not found

### 3.3 List My Tasks
- Method: GET
- Path: `/api/task/mytasks`
- Auth: Bearer access token
- Response 200:
```json
{
  "task_ids": [1, 2, 3]
}
```

### 3.4 Get Resources for a Segment
- Method: GET
- Path: `/api/task/{task_id}/resource`
- Query: `segmentId` (integer)
- Auth: Bearer access token
- Response 200:
```json
{
  "resources": [
    "generated_stories/123/segment_3.txt"
  ]
}
```
- Errors:
  - 404 Task not found
  - 400 Segment not completed yet

### 3.5 Execute a Workflow Segment
- Method: POST
- Path: `/api/task/{task_id}/execute/{segmentId}`
- Auth: Bearer access token
- Behavior:
  - Must be executed strictly in order: `segmentId == current_segment + 1`.
  - Minimal prototype simulates completion and writes `generated_stories/<task_id>/segment_<segmentId>.txt`.
  - Updates `current_segment` and task status.
- Response 200:
```json
{
  "accepted": true,
  "message": "Simulated execution completed"
}
```
- Errors:
  - 404 Task not found
  - 400 Segment cannot be executed out of order / Unknown segment

### 3.6 Delete Task
- Method: DELETE
- Path: `/api/task/{task_id}`
- Auth: Bearer access token
- Response 200:
```json
{
  "deleted": true
}
```
- Side effects:
  - Deletes DB records and removes `generated_stories/<task_id>/` folder.
- Errors:
  - 404 Task not found

---

## 4. Authentication Details
- Provide access token via header: `Authorization: Bearer <token>`
- Refresh token is stored as an HttpOnly cookie named `refresh_token`
- Token lifetime (defaults, configurable in settings.py):
  - Access token: 15 minutes
  - Refresh token: 7 days

---

## 5. Curl Examples

### Register
```bash
curl -X POST http://127.0.0.1:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'
```

### Login (shows headers to inspect Set-Cookie)
```bash
curl -i -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'
```

### Create Task
```bash
ACCESS=<your_access_token>
curl -X POST http://127.0.0.1:8000/api/task/new \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"topic":"Magnet Mania","main_role":"Penny"}'
```

### Execute Segment 1
```bash
TASK_ID=<your_task_id>
curl -X POST http://127.0.0.1:8000/api/task/$TASK_ID/execute/1 \
  -H "Authorization: Bearer $ACCESS"
```

### Get Progress
```bash
curl -X GET http://127.0.0.1:8000/api/task/$TASK_ID/progress \
  -H "Authorization: Bearer $ACCESS"
```

### Get Segment Resources
```bash
curl -X GET "http://127.0.0.1:8000/api/task/$TASK_ID/resource?segmentId=3" \
  -H "Authorization: Bearer $ACCESS"
```

### Delete Task
```bash
curl -X DELETE http://127.0.0.1:8000/api/task/$TASK_ID \
  -H "Authorization: Bearer $ACCESS"
```

---

## 6. Notes
- The minimal prototype writes stub files (segment_K.txt) on execute; production integration should attach real outputs (pages, images, audio, video) to the Resource table.
- Workflow definition can be extended/edited via WorkflowDefinition records. If none is present, a default 5-step workflow is returned.

