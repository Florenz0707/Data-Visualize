# API Documentation - MM-StoryAgent Backend

Base URL: http://127.0.0.1:8000

All endpoints are mounted under /api/.

Auth scheme: Bearer access token in Authorization header; refresh token in HttpOnly cookie.

---

## Conventions
- Content-Type: application/json unless noted.
- Auth header: Authorization: Bearer <access_token>
- Status codes: 200 (OK), 202 (Accepted for async execution), 4xx (client errors), 5xx (server errors).
- All resource paths ("urls") returned by the API are relative to the project BASE_DIR.

Error response (typical):
```json
{ "detail": "Error message" }
```

---

## 1. Auth

### 1.1 Register
POST /api/register

Request
```json
{ "username": "string", "password": "string" }
```
Response 200
```json
{ "id": 1, "username": "string" }
```

### 1.2 Login
POST /api/login

Request
```json
{ "username": "string", "password": "string" }
```
Response 200
```json
{ "access_token": "string", "token_type": "Bearer" }
```
Side effects: sets HttpOnly refresh_token cookie.

### 1.3 Refresh Access Token
POST /api/refresh

Response 200
```json
{ "access_token": "string", "token_type": "Bearer" }
```

---

## 2. Workflow

### 2.1 Get Workflow Definition
GET /api/task/workflow

Response 200
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

## 3. Tasks

### 3.1 Create Task
POST /api/task/new (auth)

Request
```json
{ "topic": "string", "main_role": "string(optional)", "scene": "string(optional)" }
```
Response 200
```json
{ "task_id": 123 }
```

### 3.2 My Tasks
GET /api/task/mytasks (auth)

Response 200
```json
{ "task_ids": [1, 2, 3] }
```

### 3.3 Task Progress
GET /api/task/{task_id}/progress (auth)

Response 200
```json
{ "current_segment": 0, "status": "pending|running|completed|failed|deleted" }
```

### 3.4 Execute a Segment
POST /api/task/{task_id}/execute/{segmentId}?redo=true|false (auth)

Rules
- Forward-only execution: segmentId must equal current_segment + 1.
- If redo=true and the segmentId was already completed, the system resets segments >= segmentId and restarts from segmentId.
- Execution is asynchronous (Celery); endpoint returns 202.

Response 202
```json
{ "accepted": true, "celery_task_id": "string|null", "message": "Execution queued" }
```

### 3.5 List Resources of a Segment (relative URLs)
GET /api/task/{task_id}/resource?segmentId=N (auth)

Response 200 (unified)
```json
{ "segmentId": 4, "urls": ["generated_stories/123/speech/s1_1.wav", "..."] }
```
Notes
- urls are always relative to the project root (BASE_DIR).
- This endpoint only lists resources; use the single-file download endpoint below to download.

### 3.6 Download a Single Resource
GET /api/resource?url=<relative_path> (auth)

Behavior
- url must be a project-root relative path previously returned by /task/{task_id}/resource.
- The resource must belong to the current user; the file must be under that task's story_dir.
- Returns a streamed attachment (Content-Disposition: attachment).

### 3.7 Delete Task
DELETE /api/task/{task_id} (auth)

Response 200
```json
{ "deleted": true }
```

---

## 4. Notifications (optional)
- The system may broadcast per-segment completion/failure via WebSocket/Redis PubSub (implementation detail). Clients can poll /progress and /task/{id}/resource alternatively.

---

## 5. Examples

```bash
ACCESS=<token>
TASK=<id>

# Execute Story (1)
curl -X POST "http://127.0.0.1:8000/api/task/$TASK/execute/1" -H "Authorization: Bearer $ACCESS"

# Redo Image (2)
curl -X POST "http://127.0.0.1:8000/api/task/$TASK/execute/2?redo=true" -H "Authorization: Bearer $ACCESS"

# List Video (5) resources
curl -s "http://127.0.0.1:8000/api/task/$TASK/resource?segmentId=5" -H "Authorization: Bearer $ACCESS"
# => {"segmentId":5,"urls":["generated_stories/$TASK/output.mp4"]}

# Download the video
curl -L -o output.mp4 "http://127.0.0.1:8000/api/resource?url=generated_stories/$TASK/output.mp4" -H "Authorization: Bearer $ACCESS"
```

---

## 6. Notes & Security
- Resource URLs are relative paths; do not attempt to pass absolute paths. The server validates ownership and that files live under the task's story folder.
- When redo=true, segments >= segmentId are reset and their files may be removed depending on the segment; then execution restarts at segmentId.
