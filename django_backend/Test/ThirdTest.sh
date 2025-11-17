#!/usr/bin/env bash
# ThirdTest.sh - Git Bash script to exercise the message-queue flow by sending HTTP requests only.
# - Logs in (or uses ACCESS_TOKEN if provided)
# - Creates a task (or uses TASK_ID if provided)
# - Triggers execution for a given segment and prints the 202 response with celery_task_id
# No Python execution is involved.
#
# Usage examples:
#   bash ThirdTest.sh                       # uses defaults; needs USERNAME/PASSWORD envs
#   USERNAME=user PASSWORD=pass bash ThirdTest.sh
#   ACCESS_TOKEN=... bash ThirdTest.sh --segment 1
#   ACCESS_TOKEN=... TASK_ID=123 bash ThirdTest.sh --segment 2
#   bash ThirdTest.sh --base http://127.0.0.1:8000/api --segment 1 --topic "A day at the zoo"

set -euo pipefail

# --- Defaults & args ---
BASE_URL="${BASE_URL:-http://127.0.0.1:8000/api}"
USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"
ACCESS_TOKEN="${ACCESS_TOKEN:-}"
TASK_ID="${TASK_ID:-}"
SEGMENT_ID=1
TOPIC="${TOPIC:-A simple demo story}"
MAIN_ROLE="${MAIN_ROLE:-}"
SCENE="${SCENE:-}"

print_help() {
  cat <<EOF
ThirdTest.sh options:
  --base URL         API base (default: $BASE_URL)
  --user NAME        Username (env USERNAME)
  --pass PASS        Password (env PASSWORD)
  --segment N        Segment id to execute (default: $SEGMENT_ID)
  --topic TEXT       Topic for new task (default from TOPIC env)
  --main ROLE        Main role (optional)
  --scene TEXT       Scene (optional)
  --task-id ID       Use existing task id (skip create)
  -h, --help         Show help
Notes:
  - If ACCESS_TOKEN env provided, login is skipped.
  - If TASK_ID env/arg provided, task creation is skipped.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE_URL="$2"; shift 2;;
    --user) USERNAME="$2"; shift 2;;
    --pass) PASSWORD="$2"; shift 2;;
    --segment) SEGMENT_ID="$2"; shift 2;;
    --topic) TOPIC="$2"; shift 2;;
    --main) MAIN_ROLE="$2"; shift 2;;
    --scene) SCENE="$2"; shift 2;;
    --task-id) TASK_ID="$2"; shift 2;;
    -h|--help) print_help; exit 0;;
    *) echo "[WARN] Unknown arg: $1"; shift;;
  esac
done

info(){ echo "[INFO] $*"; }
warn(){ echo "[WARN] $*"; }
err(){ echo "[ERROR] $*"; }

echo "[INFO] BASE_URL=$BASE_URL"
echo "[INFO] SEGMENT_ID=$SEGMENT_ID"

# --- Step 1: Acquire access token (if not provided) ---
if [[ -z "$ACCESS_TOKEN" ]]; then
  if [[ -z "${USERNAME}" || -z "${PASSWORD}" ]]; then
    err "ACCESS_TOKEN not provided and USERNAME/PASSWORD not set. Set ACCESS_TOKEN env or provide credentials."
    exit 2
  fi
  info "Logging in to obtain access token ..."
  LOGIN_RESP=$(curl -sS -X POST "$BASE_URL/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")
  # parse access_token via sed (avoid external deps like jq)
  ACCESS_TOKEN=$(echo "$LOGIN_RESP" | sed -n 's/.*"access_token"\s*:\s*"\([^"]*\)".*/\1/p')
  if [[ -z "$ACCESS_TOKEN" ]]; then
    err "Failed to parse access_token from /login response: $LOGIN_RESP"
    exit 3
  fi
  info "Got access token (len=$(echo -n "$ACCESS_TOKEN" | wc -c))"
else
  info "Using ACCESS_TOKEN from environment"
fi
AUTH_HEADER=( -H "Authorization: Bearer $ACCESS_TOKEN" )

# --- Step 2: Create task (if TASK_ID not provided) ---
if [[ -z "$TASK_ID" ]]; then
  info "Creating new task ..."
  CREATE_RESP=$(curl -sS -X POST "$BASE_URL/task/new" \
    "${AUTH_HEADER[@]}" \
    -H 'Content-Type: application/json' \
    -d "{\"topic\":\"$TOPIC\",\"main_role\":\"$MAIN_ROLE\",\"scene\":\"$SCENE\"}")
  TASK_ID=$(echo "$CREATE_RESP" | sed -n 's/.*"task_id"\s*:\s*\([0-9][0-9]*\).*/\1/p')
  if [[ -z "$TASK_ID" ]]; then
    err "Failed to parse task_id from /task/new response: $CREATE_RESP"
    exit 4
  fi
  info "Created task_id=$TASK_ID"
else
  info "Using existing TASK_ID=$TASK_ID"
fi

# --- Step 3: Trigger async execution for a segment ---
info "Triggering execute for task_id=$TASK_ID segment=$SEGMENT_ID ..."
EXEC_URL="$BASE_URL/task/$TASK_ID/execute/$SEGMENT_ID"
# capture status and body
HTTP_CODE=0
RESP_FILE=$(mktemp)
HTTP_CODE=$(curl -sS -o "$RESP_FILE" -w "%{http_code}" -X POST "$EXEC_URL" "${AUTH_HEADER[@]}")
RESP_BODY=$(cat "$RESP_FILE")
rm -f "$RESP_FILE"

echo "[INFO] HTTP $HTTP_CODE"
echo "[INFO] Response: $RESP_BODY"

# extract celery_task_id and message if present
TASKID=$(echo "$RESP_BODY" | sed -n 's/.*"celery_task_id"\s*:\s*"\([^"]*\)".*/\1/p')
MSG=$(echo "$RESP_BODY" | sed -n 's/.*"message"\s*:\s*"\([^"]*\)".*/\1/p')
if [[ -n "$TASKID" ]]; then
  info "celery_task_id=$TASKID"
fi
if [[ -n "$MSG" ]]; then
  info "message=$MSG"
fi

if [[ "$HTTP_CODE" != "202" ]]; then
  warn "Expected HTTP 202 Accepted for queued execution."
  exit 5
fi

info "Done. You can now subscribe to your Redis channel (e.g., user:{user_id}) to observe completion notifications."
