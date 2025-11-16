import sys
from pathlib import Path

# Ensure project root is on sys.path to import mm_story_agent
CURRENT = Path(__file__).resolve()
DJANGO_DIR = CURRENT.parents[2]  # django_backend/
PROJECT_ROOT = DJANGO_DIR.parent  # repo root where mm_story_agent/ resides
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env files if present (local lightweight loader)
def _load_env_file(path: Path):
    try:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

import os
_load_env_file(PROJECT_ROOT / "configs/.env")
_load_env_file(PROJECT_ROOT / "config/.env")

