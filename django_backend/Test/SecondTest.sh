#!/usr/bin/env bash
# Windows Git Bash friendly API test script (no server startup)
# Ensure your Django server is already running (default http://127.0.0.1:8000)

set -euo pipefail

# -------- Config --------
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8000}
BASE="http://$HOST:$PORT"
USER_NAME=${USER_NAME:-"proto_user"}
USER_PASS=${USER_PASS:-"proto_pass"}
RESUME=${RESUME:-"false"}  # true: continue from latest segment of task 1 (or created task); false: start from segment 1
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COOKIE_FILE="$SCRIPT_DIR/cookie.txt"

# -------- Helpers --------
extract_access_token() {
  printf "%s" "$1" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}
extract_task_id() {
  printf "%s" "$1" | sed -n 's/.*"task_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'
}
get_current_segment() {
  # input: JSON {"current_segment":N,...} -> prints N or empty
  printf "%s" "$1" | sed -n 's/.*"current_segment"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'
}
cleanup() { rm -f "$COOKIE_FILE" >/dev/null 2>&1 || true; }
trap cleanup EXIT

say() { printf "%s\n" "$*"; }

# -------- Sanity check --------
say "Checking server $BASE ..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/docs" || true)
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "404" ]; then
  echo "Server not reachable at $BASE (HTTP $HTTP_CODE). Start your Django server and retry." >&2
  exit 1
fi

# -------- 1) Register --------
say "== 1) Register (expect 200 or 400 if exists) =="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PASS\"}") || true
say "Register HTTP $HTTP_CODE"

# -------- 2) Login --------
say "== 2) Login (store refresh cookie) =="
LOGIN_JSON=$(curl -s -c "$COOKIE_FILE" -X POST "$BASE/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PASS\"}")
say "$LOGIN_JSON"
ACCESS_TOKEN=$(extract_access_token "$LOGIN_JSON")
if [ -z "$ACCESS_TOKEN" ]; then
  echo "Failed to obtain access_token from login response" >&2
  exit 1
fi
AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"

# -------- 3) Workflow (optional) --------
say "== 3) Get workflow =="
curl -s "$BASE/api/task/workflow" | cat

# -------- 4) Ensure Task 1 exists (or create one) --------
say "== 4) Ensure Task 1 exists (or create one) =="
TASK_ID=""
# Try task 1 progress
HTTP_CODE_TASK1=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/task/1/progress" -H "$AUTH_HEADER" || true)
if [ "$HTTP_CODE_TASK1" = "200" ]; then
  TASK_ID=1
  say "Task 1 exists."
else
  say "Task 1 not found. Creating a new task..."
  NEW_TASK_JSON=$(curl -s -X POST "$BASE/api/task/new" \
    -H "$AUTH_HEADER" -H "Content-Type: application/json" \
    -d '{"topic":"Prototype API Test","main_role":"Tester","scene":"(optional)"}')
  say "$NEW_TASK_JSON"
  TASK_ID=$(extract_task_id "$NEW_TASK_JSON")
  if [ -z "$TASK_ID" ]; then
    echo "Failed to parse task_id from response" >&2
    exit 1
  fi
fi
say "Using TASK_ID=$TASK_ID"

# -------- 5) Determine start segment based on RESUME --------
PROGRESS_JSON=$(curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER")
say "Current progress: $PROGRESS_JSON"
CURRENT_SEG=$(get_current_segment "$PROGRESS_JSON")
[ -z "$CURRENT_SEG" ] && CURRENT_SEG=0
if [ "$RESUME" = "true" ]; then
  START_SEG=$((CURRENT_SEG + 1))
  [ "$START_SEG" -lt 1 ] && START_SEG=1
  [ "$START_SEG" -gt 5 ] && START_SEG=5
  say "RESUME=true → starting from segment $START_SEG"
else
  START_SEG=1
  say "RESUME=false → starting from segment 1"
fi

# -------- 6) Execute segments from START_SEG to 5 --------
for i in $(seq "$START_SEG" 5); do
  say "Executing segment $i ..."
  curl -s -X POST "$BASE/api/task/$TASK_ID/execute/$i" -H "$AUTH_HEADER" | cat
  echo
  # fetch progress after each step
  curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER" | cat
  echo
 done

# -------- 7) Final progress and (optional) video resource --------
say "== Final progress =="
curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER" | cat

echo
say "== Segment 5 resource (if completed) =="
curl -s "$BASE/api/task/$TASK_ID/resource?segmentId=5" -H "$AUTH_HEADER" | cat

echo -e "\nAll API request checks completed."
