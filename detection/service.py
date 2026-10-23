from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from alerts.models import Alert, MITRE
from .rules import evaluate_brute_force, evaluate_port_scan
from agent.tasks import dispatch_investigation


def process_events_for_detection(events):
    if not events:
        return
    by_ip = {}
    for ev in events:
        by_ip.setdefault(ev.source_ip, []).append(ev)
    new_alert_ids = []
    for source_ip, ip_events in by_ip.items():
        window_end = max(e.timestamp for e in ip_events)
        window_start = window_end - timedelta(seconds=settings.WINDOW_SECONDS)
        # brute force
        res_bf = evaluate_brute_force(source_ip, window_start, window_end)
        if res_bf:
            evidence_bf, count_bf, first_m, last_m = res_bf
            alert = Alert.objects.filter(
                rule_name='brute_force', source_ip=source_ip, incident_status__in=['open', 'acknowledged']
            ).select_for_update().first()
            if alert:
                alert.last_seen_at = max(alert.last_seen_at, last_m)
                alert.last_window_count = count_bf
                if count_bf > alert.peak_window_count:
                    alert.peak_window_count = count_bf
                alert.evidence = evidence_bf
                alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
            else:
                try:
                    with transaction.atomic():
                        alert = Alert.objects.create(
                            rule_name='brute_force',
                            source_ip=source_ip,
                            incident_status='open',
                            investigation_status='queued',
                            severity='high',
                            mitre_id=MITRE['brute_force']['id'],
                            mitre_name=MITRE['brute_force']['name'],
                            first_seen_at=first_m,
                            last_seen_at=last_m,
                            last_window_count=count_bf,
                            peak_window_count=count_bf,
                            evidence=evidence_bf,
                        )
                    new_alert_ids.append(alert.id)
                except IntegrityError:
                    alert = Alert.objects.filter(
                        rule_name='brute_force', source_ip=source_ip, incident_status__in=['open', 'acknowledged']
                    ).first()
                    if alert:
                        alert.last_seen_at = max(alert.last_seen_at, last_m)
                        alert.last_window_count = count_bf
                        if count_bf > alert.peak_window_count:
                            alert.peak_window_count = count_bf
                        alert.evidence = evidence_bf
                        alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
        # port scan
        res_ps = evaluate_port_scan(source_ip, window_start, window_end)
        if res_ps:
            evidence_ps, count_ps, first_m, last_m = res_ps
            alert = Alert.objects.filter(
                rule_name='port_scan', source_ip=source_ip, incident_status__in=['open', 'acknowledged']
            ).select_for_update().first()
            if alert:
                alert.last_seen_at = max(alert.last_seen_at, last_m)
                alert.last_window_count = count_ps
                if count_ps > alert.peak_window_count:
                    alert.peak_window_count = count_ps
                alert.evidence = evidence_ps
                alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
            else:
                try:
                    with transaction.atomic():
                        alert = Alert.objects.create(
                            rule_name='port_scan',
                            source_ip=source_ip,
                            incident_status='open',
                            investigation_status='queued',
                            severity='medium',
                            mitre_id=MITRE['port_scan']['id'],
                            mitre_name=MITRE['port_scan']['name'],
                            first_seen_at=first_m,
                            last_seen_at=last_m,
                            last_window_count=count_ps,
                            peak_window_count=count_ps,
                            evidence=evidence_ps,
                        )
                    new_alert_ids.append(alert.id)
                except IntegrityError:
                    alert = Alert.objects.filter(
                        rule_name='port_scan', source_ip=source_ip, incident_status__in=['open', 'acknowledged']
                    ).first()
                    if alert:
                        alert.last_seen_at = max(alert.last_seen_at, last_m)
                        alert.last_window_count = count_ps
                        if count_ps > alert.peak_window_count:
                            alert.peak_window_count = count_ps
                        alert.evidence = evidence_ps
                        alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
    if new_alert_ids:
        for aid in new_alert_ids:
            transaction.on_commit(lambda a=aid: dispatch_investigation(a))
