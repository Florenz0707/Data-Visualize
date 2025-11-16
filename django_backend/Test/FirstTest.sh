#!/usr/bin/env bash
# Windows Git Bash friendly smoke test for the minimal Django + Ninja prototype
# This version DOES NOT start or manage the server. Ensure your server is already running.
# Default server: http://127.0.0.1:8000 (change HOST/PORT below if needed)

set -euo pipefail

# -------- Config --------
HOST=127.0.0.1
PORT=8000
BASE="http://$HOST:$PORT"
USER_NAME="proto_user"
USER_PASS="proto_pass"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COOKIE_FILE="$SCRIPT_DIR/cookie.txt"

# -------- Helpers --------
extract_access_token() {
  # Extract value of access_token from a simple JSON: {"access_token":"...","token_type":"Bearer"}
  # Works without jq; not a general JSON parser but sufficient for prototype responses.
  printf "%s" "$1" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

extract_task_id() {
  # Extract value of task_id from {"task_id":123}
  printf "%s" "$1" | sed -n 's/.*"task_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'
}

cleanup() {
  rm -f "$COOKIE_FILE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# -------- Sanity check: server availability --------
printf "Checking server %s ...\n" "$BASE"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/docs" || true)
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "404" ]; then
  echo "Server not reachable at $BASE (HTTP $HTTP_CODE). Start your Django server and retry." >&2
  exit 1
fi

echo "== 1) Register (expect 200 or 400 if already exists) =="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PASS\"}") || true
echo "Register HTTP $HTTP_CODE"

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

echo "== 3) Get workflow =="
curl -s "$BASE/api/task/workflow" | cat

echo "== 4) Create task =="
NEW_TASK_JSON=$(curl -s -X POST "$BASE/api/task/new" \
  -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  -d '{"topic":"Prototype Smoke Test","main_role":"Tester","scene":"(optional)"}')
echo "$NEW_TASK_JSON" | cat
TASK_ID=$(extract_task_id "$NEW_TASK_JSON")
if [ -z "$TASK_ID" ]; then
  echo "Failed to parse task_id from response" >&2
  exit 1
fi

echo "== 5) Check progress (should be 0/pending) =="
curl -s "$BASE/api/task/$TASK_ID/progress" -H "$AUTH_HEADER" | cat

echo "== 6) List my tasks =="
curl -s "$BASE/api/task/mytasks" -H "$AUTH_HEADER" | cat

echo "== 7) Refresh access token via cookie (optional) =="
curl -s -b "$COOKIE_FILE" -X POST "$BASE/api/refresh" | cat

echo "\nAll prototype request checks completed."}
