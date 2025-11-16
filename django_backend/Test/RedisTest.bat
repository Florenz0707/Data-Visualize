@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Verify connectivity from Windows (CMD/PowerShell) to Redis running in WSL,
REM and basic Celery <-> Redis connectivity in this project.
REM Usage: RedisTest.bat

set "REDIS_URL_DEFAULT=redis://localhost:6379/0"
set "BROKER_URL_DEFAULT=redis://localhost:6379/0"
set "RESULT_BACKEND_DEFAULT=redis://localhost:6379/1"

if not defined REDIS_URL set "REDIS_URL=%REDIS_URL_DEFAULT%"
if not defined CELERY_BROKER_URL set "CELERY_BROKER_URL=%BROKER_URL_DEFAULT%"
if not defined CELERY_RESULT_BACKEND set "CELERY_RESULT_BACKEND=%RESULT_BACKEND_DEFAULT%"

set "PROJECT=django_backend"
set "CHANNEL=test:chan:%RANDOM%_%TIME%"
set "TMP_OUT=.redis_sub_%RANDOM%.log"
set "TIMEOUT_SEC=10"

echo [INFO] Working dir: %CD%
echo [INFO] Redis URL: %REDIS_URL%
echo [INFO] Celery broker: %CELERY_BROKER_URL%
echo [INFO] Celery result backend: %CELERY_RESULT_BACKEND%

REM Step 1: ensure python exists
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found on PATH. Activate your venv first (e.g., .\.venv\Scripts\activate)
  exit /b 1
)

REM Step 2: Python redis ping (via temp script)
echo [INFO] Testing Redis PING via redis-py ...
set "PING_SCRIPT=%TEMP%\redis_ping_%RANDOM%.py"
>"%PING_SCRIPT%" echo import sys, os, redis
>>"%PING_SCRIPT%" echo url = os.environ.get('REDIS_URL', '%REDIS_URL_DEFAULT%')
>>"%PING_SCRIPT%" echo try:
>>"%PING_SCRIPT%" echo ^    r = redis.from_url(url)
>>"%PING_SCRIPT%" echo ^    ok = r.ping()
>>"%PING_SCRIPT%" echo ^    print('PING ->', ok)
>>"%PING_SCRIPT%" echo ^    sys.exit(0 if ok else 2)
>>"%PING_SCRIPT%" echo except Exception as e:
>>"%PING_SCRIPT%" echo ^    print('PING failed:', e)
>>"%PING_SCRIPT%" echo ^    sys.exit(2)

python "%PING_SCRIPT%"
set ERR=%ERRORLEVEL%
del /f /q "%PING_SCRIPT%" >nul 2>&1
if not "%ERR%"=="0" (
  echo [ERROR] Redis PING failed.
  exit /b %ERR%
)

REM Step 3: Pub/Sub test
echo [INFO] Testing Redis Pub/Sub on channel: %CHANNEL% ...
set "SUB_SCRIPT=%TEMP%\redis_sub_%RANDOM%.py"
>"%SUB_SCRIPT%" echo import os, sys, json
>>"%SUB_SCRIPT%" echo import redis
>>"%SUB_SCRIPT%" echo url = os.environ.get('REDIS_URL', '%REDIS_URL_DEFAULT%')
>>"%SUB_SCRIPT%" echo r = redis.from_url(url)
>>"%SUB_SCRIPT%" echo p = r.pubsub()
>>"%SUB_SCRIPT%" echo p.subscribe('%CHANNEL%')
>>"%SUB_SCRIPT%" echo print('listening')
>>"%SUB_SCRIPT%" echo for m in p.listen():
>>"%SUB_SCRIPT%" echo ^    if m.get('type') == 'message':
>>"%SUB_SCRIPT%" echo ^        try:
>>"%SUB_SCRIPT%" echo ^            data = m.get('data')
>>"%SUB_SCRIPT%" echo ^            s = data.decode() if isinstance(data, (bytes,bytearray)) else str(data)
>>"%SUB_SCRIPT%" echo ^            print('recv:', s)
>>"%SUB_SCRIPT%" echo ^        except Exception as e:
>>"%SUB_SCRIPT%" echo ^            print('recv error:', e)
>>"%SUB_SCRIPT%" echo ^        break

start "redis-subscriber" /B cmd /c "python "%SUB_SCRIPT%" 1^> "%TMP_OUT%" 2^>^&1"

REM Give subscriber time to start
timeout /t 1 >nul

set "PUB_SCRIPT=%TEMP%\redis_pub_%RANDOM%.py"
>"%PUB_SCRIPT%" echo import os, redis
>>"%PUB_SCRIPT%" echo url = os.environ.get('REDIS_URL', '%REDIS_URL_DEFAULT%')
>>"%PUB_SCRIPT%" echo r = redis.from_url(url)
>>"%PUB_SCRIPT%" echo r.publish('%CHANNEL%', 'hello-from-batch')
>>"%PUB_SCRIPT%" echo print('published')

python "%PUB_SCRIPT%" >nul 2>&1
del /f /q "%PUB_SCRIPT%" >nul 2>&1

set ok=0
for /l %%i in (1,1,%TIMEOUT_SEC%) do (
  findstr /c:"recv:" "%TMP_OUT%" >nul 2>&1 && (set ok=1 & goto :done_wait)
  timeout /t 1 >nul
)
:done_wait

if "%ok%"=="1" (
  for /f "usebackq tokens=*" %%l in ("%TMP_OUT%") do set last=%%l
  echo [INFO] Pub/Sub OK: !last!
) else (
  echo [WARN] Pub/Sub did not receive message within %TIMEOUT_SEC%s. See %TMP_OUT% for logs.
)

REM Step 4: Celery inspect ping (requires worker running)
echo [INFO] Checking Celery worker availability (requires: celery worker running) ...
where celery >nul 2>&1
if errorlevel 1 (
  echo [WARN] celery command not found on PATH. Skip Celery inspect test.
) else (
  celery -A %PROJECT% inspect ping | findstr /c:"\"ok\": \"pong\"" >nul 2>&1
  if errorlevel 1 (
    echo [WARN] Celery inspect ping did not return pong. Ensure worker is running: celery -A %PROJECT% worker -l info -P solo --concurrency 1
  ) else (
    echo [INFO] Celery inspect ping -> pong (worker reachable)
  )
)

echo [INFO] All checks done.

REM Cleanup temp files (subscriber exits on first message; script/logs can be removed)
del /f /q "%SUB_SCRIPT%" >nul 2>&1

endlocal
