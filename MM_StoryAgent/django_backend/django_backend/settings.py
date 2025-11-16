import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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
try:
    from mm_story_agent.config import load_env
    # Prefer standard path "configs/.env"; also try "config/.env" for user convenience
    repo_root = BASE_DIR.parent
    load_env(repo_root / "configs/.env")
    load_env(repo_root / "config/.env")
except Exception:
    # Silently ignore if mm_story_agent is not available yet
    pass
