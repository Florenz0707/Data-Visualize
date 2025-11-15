# First Test - Minimal Backend Prototype Validation

This guide helps you verify the minimal Django + Ninja backend prototype under `django_backend/`.

## 1) Environment

- Python: >= 3.11
- Minimal dependencies for this prototype:
  - django
  - django-ninja

Notes:
- The root project has many multimedia dependencies (see project-level `requirements.txt`), but the minimal backend prototype only requires Django and django-ninja to run and validate the API flow. You can add the heavy dependencies later when integrating real agents.

## 2) Setup

```bash
# Create and activate venv (recommended)
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

# Install minimal deps
pip install django django-ninja

# Migrate DB
cd django_backend
python manage.py migrate

# Run server
python manage.py runserver
```

Open API docs in browser: http://127.0.0.1:8000/api/docs

## 3) Test Flow (Step-by-step)

### 3.1 Register
- Endpoint: `POST /api/register`
- JSON Body:
```json
{
  "username": "u1",
  "password": "p1"
}
```
- Expect: 200 with user id and username.

### 3.2 Login
- Endpoint: `POST /api/login`
- JSON Body:
```json
{
  "username": "u1",
  "password": "p1"
}
```
- Expect:
  - JSON with `access_token`.
  - Response should also set `Set-Cookie: refresh_token=...` (depending on your client, the cookie may or may not be persisted automatically in this minimal prototype).

### 3.3 Get Workflow Definition
- Endpoint: `GET /api/task/workflow`
- Expect: ordered list of segments `[Story, Image, Split, Speech, Video]`.

### 3.4 Create Task (Requires Bearer Token)
- Endpoint: `POST /api/task/new`
- Headers: `Authorization: Bearer <access_token>`
- JSON Body (example):
```json
{
  "topic": "Magnet Mania",
  "main_role": "Penny",
  "scene": "(optional)"
}
```
- Expect: `task_id` and the folder `generated_stories/<task_id>/` created.

### 3.5 Execute Segments (Simulated)
- Execute strictly in order; otherwise you will get an error: `Segment cannot be executed out of order`.
- Endpoints:
  - `POST /api/task/{task_id}/execute/1`
  - `POST /api/task/{task_id}/execute/2`
  - `POST /api/task/{task_id}/execute/3`
  - `POST /api/task/{task_id}/execute/4`
  - `POST /api/task/{task_id}/execute/5`
- Expect:
  - Each call returns `accepted=true` and writes a stub file: `generated_stories/<task_id>/segment_<k>.txt`.
  - `current_segment` increases step by step; after 5, task status becomes `completed`.

### 3.6 Check Progress
- Endpoint: `GET /api/task/{task_id}/progress`
- Expect: `current_segment` and `status` (running/completed).

### 3.7 Get Resources for a Segment
- Endpoint: `GET /api/task/{task_id}/resource?segmentId=3`
- Expect: list of resource paths for segment 3 (stub file paths in this prototype).

### 3.8 List My Tasks
- Endpoint: `GET /api/task/mytasks`
- Expect: list of task ids for the authenticated user.

### 3.9 Delete Task
- Endpoint: `DELETE /api/task/{task_id}`
- Expect: `{ "deleted": true }` and the folder `generated_stories/<task_id>/` removed.

## 4) Curl Examples

```bash
# Register
curl -X POST http://127.0.0.1:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'

# Login (use -i to see Set-Cookie)
curl -i -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"u1","password":"p1"}'
# Copy access_token from JSON response

# Create Task (replace ACCESS with your token)
ACCESS=<your_access_token_here>
curl -X POST http://127.0.0.1:8000/api/task/new \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"topic":"Magnet Mania","main_role":"Penny"}'

# Execute first segment (replace TASK_ID)
curl -X POST http://127.0.0.1:8000/api/task/<TASK_ID>/execute/1 \
  -H "Authorization: Bearer $ACCESS"
```

## 5) Notes & Troubleshooting
- If `/api/docs` is not available, ensure the server is running and `django_backend/urls.py` includes `path("api/", api.urls)`.
- If the refresh cookie is not visible, it may be due to client handling in this minimal prototype. You can proceed with the `access_token` for testing the core flow.
- SQLite DB is created at `django_backend/db.sqlite3`.
- Stub resources are written into `generated_stories/<task_id>/`.

