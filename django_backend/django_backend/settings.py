import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "django_celery_results",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "django_backend.wsgi.application"
ASGI_APPLICATION = "django_backend.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery / Redis configuration
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Celery stability and reliability settings
CELERY_BROKER_HEARTBEAT = int(os.environ.get("CELERY_BROKER_HEARTBEAT", 60))
CELERY_BROKER_CONNECTION_TIMEOUT = int(os.environ.get("CELERY_BROKER_CONNECTION_TIMEOUT", 30))
CELERY_BROKER_POOL_LIMIT = int(os.environ.get("CELERY_BROKER_POOL_LIMIT", 20))

# Ensure tasks are only acknowledged after successful execution
CELERY_TASK_ACKS_LATE = True
# Avoid over-prefetching on long CPU-bound tasks
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.environ.get("CELERY_WORKER_PREFETCH_MULTIPLIER", 1))
# If a worker is lost mid-task, requeue it (requires acks_late)
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Task time limits (seconds)
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", 1800))  # 30 min
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", 2100))  # 35 min

# Transport options for Redis
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_keepalive": True,
    "socket_timeout": 30,
    "retry_on_timeout": True,
    # Ensure messages become visible again if a worker dies holding them
    "visibility_timeout": 3600,
}

# Do not hijack Django's root logger
CELERYD_HIJACK_ROOT_LOGGER = False

# Cancel long running tasks on broker connection loss (Celery 5.1+, default True in 6.0)
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True

# django-celery-results
CELERY_RESULT_EXTENDED = True

# Channels (WebSocket gateway)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_URL", REDIS_URL)],
        },
    }
}

# Storage roots for generated assets (reuse project root generated_stories directory)
# Store generated assets within django_backend directory by default
GENERATED_ROOT = (BASE_DIR / "generated_stories").resolve()
GENERATED_ROOT.mkdir(parents=True, exist_ok=True)

# Token lifetimes (seconds)
ACCESS_TOKEN_LIFETIME = int(os.environ.get("ACCESS_TOKEN_LIFETIME", 15 * 60))  # 15 minutes
REFRESH_TOKEN_LIFETIME = int(os.environ.get("REFRESH_TOKEN_LIFETIME", 7 * 24 * 3600))  # 7 days
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_SECURE = False
REFRESH_COOKIE_HTTPONLY = True


# --- Load .env for model/API keys on server startup ---
# Prefer standard path "configs/.env"; also try "config/.env" for user convenience
# Avoid external dependencies to keep settings self-contained

def _load_env_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


_load_env_file(BASE_DIR / "config/.env")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "DEBUG"},
        "django.request": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "daphne": {"handlers": ["console"], "level": "DEBUG"},
        "channels": {"handlers": ["console"], "level": "DEBUG"},
        "asyncio": {"handlers": ["console"], "level": "WARNING"},
    }
}
