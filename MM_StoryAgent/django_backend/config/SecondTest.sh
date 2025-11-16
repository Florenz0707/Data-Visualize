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
DO_EXECUTE=${DO_EXECUTE:-"true"}  # set to "true" to run segments 1..5 (requires dependencies & API keys)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COOKIE_FILE="$SCRIPT_DIR/cookie.txt"

# -------- Helpers --------
extract_access_token() {
  # Extract "access_token" from simple JSON: {"access_token":"...","token_type":"Bearer"}
  printf "%s" "$1" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}
extract_task_id() {
  # Extract "task_id" from {"task_id":123}
  printf "%s" "$1" | sed -n 's/.*"task_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'
}
cleanup() { rm -f "$COOKIE_FILE" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# -------- Sanity check --------
printf "Checking server %s ...\n" "$BASE"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/docs" || true)
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "404" ]; then
  echo "Server not reachable at $BASE (HTTP $HTTP_CODE). Start your Django server and retry." >&2
  exit 1
fi

# -------- 1) Register --------
echo "== 1) Register (expect 200 or 400 if exists) =="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PASS\"}") || true
echo "Register HTTP $HTTP_CODE"

# -------- 2) Login --------
echo "== 2) Login (store refresh cookie) =="
LOGIN_JSON=$(curl -s -c "$COOKIE_FILE" -X POST "$BASE/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PASS\"}")
echo "$LOGIN_JSON" | cat
ACCESS_TOKEN=$(extract_access_token "$LOGIN_JSON")
if [ -z "$ACCESS_TOKEN" ]; then
  echo "Failed to obtain access_token from login response" >&2
  exit 1
fi
AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"

# -------- 3) Workflow --------
echo "== 3) Get workflow =="
curl -s "$BASE/api/task/workflow" | cat

# -------- 4) Create task --------
echo "== 4) Create task =="
NEW_TASK_JSON=$(curl -s -X POST "$BASE/api/task/new" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"topic":"Prototype API Test","main_role":"Tester","scene":"(optional)"}')
echo "$NEW_TASK_JSON" | cat
TASK_ID=$(extract_task_id "$NEW_TASK_JSON")
if [ -z "$TASK_ID" ]; then
  echo "Failed to parse task_id from response" >&2
  exit 1
fi

# -------- 5) Progress (initial) --------
echo "== 5) Check progress (should be 0/pending) =="
curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER" | cat

# -------- Optional: Execute segments 1..5 --------
if [ "$DO_EXECUTE" = "true" ]; then
  echo "== Execute segments 1..5 =="
  for i in 1 2 3 4 5; do
    echo "Executing segment $i ..."
    curl -s -X POST "$BASE/api/task/$TASK_ID/execute/$i" -H "$AUTH_HEADER" | cat
  done

  echo "== Progress after execution =="
  curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER" | cat

  echo "== Video resource (segment 5) =="
  curl -s "$BASE/api/task/$TASK_ID/resource?segmentId=5" -H "$AUTH_HEADER" | cat
fi

# -------- 6) My tasks --------
echo "== 6) List my tasks =="
curl -s "$BASE/api/task/mytasks" -H "$AUTH_HEADER" | cat

# -------- 7) Refresh token --------
echo "== 7) Refresh access token via cookie =="
curl -s -b "$COOKIE_FILE" -X POST "$BASE/api/refresh" | cat

echo -e "\nAll API request checks completed."
