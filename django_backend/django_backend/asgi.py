import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path, re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_backend.settings')

django_asgi_app = get_asgi_application()

# Import websocket urls
from api.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})
