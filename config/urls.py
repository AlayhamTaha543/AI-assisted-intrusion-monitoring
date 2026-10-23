from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection
from django.conf import settings
import redis


def health(request):
    db_ok = False
    redis_ok = False
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
        db_ok = True
    except Exception:
        db_ok = False
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    if db_ok and redis_ok:
        return JsonResponse({'status': 'ok', 'db': True, 'redis': True}, status=200)
    return JsonResponse({'status': 'degraded', 'db': db_ok, 'redis': redis_ok}, status=503)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/', include('events.urls')),
    path('api/', include('alerts.urls')),
]
