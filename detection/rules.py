from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q

from events.models import LogEvent
from alerts.models import Alert, MITRE


def evaluate_brute_force(source_ip, window_start, window_end):
    events = LogEvent.objects.filter(
        source_ip=source_ip,
        event_type='login_failed',
        timestamp__gte=window_start,
        timestamp__lte=window_end,
    )
    failed_count = events.count()
    if failed_count < settings.BRUTE_FORCE_THRESHOLD:
        return None
    distinct_usernames = events.exclude(Q(username__isnull=True) | Q(username='')).values('username').distinct().count()
    evidence = {
        'failed_logins': failed_count,
        'distinct_usernames': distinct_usernames,
        'threshold': settings.BRUTE_FORCE_THRESHOLD,
        'window_seconds': settings.WINDOW_SECONDS,
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat(),
    }
    return evidence, failed_count


def evaluate_port_scan(source_ip, window_start, window_end):
    events = LogEvent.objects.filter(
        source_ip=source_ip,
        event_type='connection',
        timestamp__gte=window_start,
        timestamp__lte=window_end,
        dest_port__isnull=False,
    )
    connection_events = events.count()
    distinct_ports = events.values('dest_port').distinct().count()
    if distinct_ports < settings.PORT_SCAN_THRESHOLD:
        return None
    evidence = {
        'distinct_ports': distinct_ports,
        'connection_events': connection_events,
        'threshold': settings.PORT_SCAN_THRESHOLD,
        'window_seconds': settings.WINDOW_SECONDS,
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat(),
    }
    return evidence, distinct_ports
