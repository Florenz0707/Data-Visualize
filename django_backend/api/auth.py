from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.utils import timezone

ACCESS_SALT = "access"
REFRESH_SALT = "refresh"


def create_access_token(user: User) -> str:
    data = {"uid": user.id, "ts": int(timezone.now().timestamp())}
    return signing.dumps(data, salt=ACCESS_SALT)


def create_refresh_token(user: User) -> str:
    data = {"uid": user.id, "ts": int(timezone.now().timestamp())}
    return signing.dumps(data, salt=REFRESH_SALT)


def verify_access_token(token: str) -> Optional[User]:
    try:
        data = signing.loads(token, salt=ACCESS_SALT, max_age=getattr(settings, "ACCESS_TOKEN_LIFETIME", 900))
        uid = data.get("uid")
        return User.objects.filter(id=uid).first()
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None


def verify_refresh_token(token: str) -> Optional[User]:
    try:
        data = signing.loads(token, salt=REFRESH_SALT,
                             max_age=getattr(settings, "REFRESH_TOKEN_LIFETIME", 7 * 24 * 3600))
        uid = data.get("uid")
        return User.objects.filter(id=uid).first()
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None


def auth_from_header(auth_header: Optional[str]) -> Optional[User]:
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return verify_access_token(parts[1])
    return None
