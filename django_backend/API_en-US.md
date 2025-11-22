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
{
  "current_segment": 0,
  "status": "pending|running|completed|failed|deleted",
  "workflow_version": "default|videogen",
  "total_segments": 5,
  "segment_names": ["Story", "Image", "Split", "Speech", "Video"]
}
```

Task Info (one-shot metadata)
GET /api/task/{task_id}/info (auth)

Notes
- Returns the workflow type (workflow_version), current step, total steps, and segment names in a single call.
- Useful on first load to determine whether the task follows the default 5-step flow or the single-step videogen flow.

Response 200 (examples)
- Default workflow
```json
{
  "id": 123,
  "workflow_version": "default",
  "status": "running",
  "current_segment": 2,
  "total_segments": 5,
  "segment_names": ["Story", "Image", "Split", "Speech", "Video"]
}
```
- Videogen workflow
```json
{
  "id": 456,
  "workflow_version": "videogen",
  "status": "running",
  "current_segment": 1,
  "total_segments": 1,
  "segment_names": ["VideoGen"]
}
```

Example
```bash
curl -s "http://127.0.0.1:8000/api/task/$TASK/info" -H "Authorization: Bearer $ACCESS"
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


### 3.8 User-provided resource upload (redo seg1/seg3)
PUT /api/task/{task_id}/myresource/{segmentId} (auth)

Notes
- Only the default 5-step workflow; videogen is not supported
- Only segmentId ∈ {1, 3}
- Acts like a redo: writes user-provided content, resets and marks the segment completed, sets current_segment to the segment, and clears downstream artifacts

Request formats
- application/json
  - seg1 (Story):
    {
      "pages": [ {"story":"page1"}, {"story":"page2"} ]
    }
    - strings are allowed and will be normalized to {"story": "..."}
  - seg3 (Split):
    {
      "segmented_pages": [ ["s1","s2"], ["A","B","C"] ]
    }
    - segmented_pages length must match pages length in script_data.json

- multipart/form-data (upload JSON file)
  - file=@script_data.json
  - mode=merge|replace (optional; default replace)
    - seg1: replace overwrites pages; merge only replaces pages while preserving other fields (and clears old segmented_pages)
    - seg3: always merges into script_data.json and updates segmented_pages

Response (200)
```json
{ "segmentId": 1, "urls": ["generated_stories/<id>/script_data.json"], "message": "Resource updated and segment marked completed" }
```

Errors
- 400: invalid segmentId (not 1/3), bad schema, length mismatch, unsupported Content-Type
- 401: unauthorized; 403: forbidden; 404: task not found / missing prerequisites (seg3); 409: task running

---

## 4. Text-to-Video (Standalone Workflow: videogen)

Overview
- Independent from the default 5-step workflow. Single-step video generation from long text or an input image.
- Two entry styles:
  1) Convenience: /api/videogen/new and /api/videogen/{task_id}/execute
  2) Generic: /api/task/new with workflow_version="videogen"; then /api/task/{task_id}/execute/1

### 4.1 Create videogen task
POST /api/videogen/new (auth)

Request
```json
{ "topic": "Prompt text for direct video generation", "main_role": "optional", "scene": "optional" }
```
Response 200
```json
{ "task_id": 123 }
```

Note: topic is used as the prompt.

### 4.2 Execute videogen
POST /api/videogen/{task_id}/execute (auth)

Behavior
- No request body: the execution uses parameters defined at task creation (topic as prompt; other params from t2v_generation.params).
- Redo: POST /api/videogen/{task_id}/execute?redo=true
- Asynchronous execution, returns 202:
```json
{ "accepted": true, "celery_task_id": "string|null", "message": "Execution queued" }
```

### 4.3 Fetch resources
- List: GET /api/task/{task_id}/resource?segmentId=1 (auth)
- Download: GET /api/resource?url=<relative_path> (auth)

### 4.4 Generic entry to videogen (optional)
POST /api/task/new (auth)
```json
{ "topic": "string", "workflow_version": "videogen" }
```
Then execute: POST /api/task/{task_id}/execute/1

---

## 5. Notifications (optional)
- The system may broadcast per-segment completion/failure via WebSocket/Redis PubSub (implementation detail). Clients can poll /progress and /task/{id}/resource alternatively.

---

## 6. Examples

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
