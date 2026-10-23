from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connections
from django.core.cache import caches
import redis
from django.conf import settings


def health(request):
    db_ok = False
    redis_ok = False
    try:
        connections['default'].cursor()
        db_ok = True
    except Exception:
        db_ok = False
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return JsonResponse({'status': 'ok' if db_ok and redis_ok else 'degraded', 'db': db_ok, 'redis': redis_ok})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/', include('events.urls')),
    path('api/', include('alerts.urls')),
]
