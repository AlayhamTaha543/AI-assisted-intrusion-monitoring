from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from alerts.models import Alert, MITRE
from .rules import evaluate_brute_force, evaluate_port_scan


def process_events_for_detection(events):
    if not events:
        return
    # group by source_ip
    by_ip = {}
    for ev in events:
        by_ip.setdefault(ev.source_ip, []).append(ev)
    for source_ip, ip_events in by_ip.items():
        window_end = max(e.timestamp for e in ip_events)
        window_start = window_end - timedelta(seconds=settings.WINDOW_SECONDS)
        # brute force
        res_bf = evaluate_brute_force(source_ip, window_start, window_end)
        if res_bf:
            evidence_bf, count_bf = res_bf
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
                        first_seen_at=window_start,
                        last_seen_at=window_end,
                        last_window_count=count_bf,
                        peak_window_count=count_bf,
                        evidence=evidence_bf,
                    )
                transaction.on_commit(lambda a_id=alert.id: _enqueue_investigation(a_id))
            except IntegrityError:
                # update existing active
                try:
                    alert = Alert.objects.get(rule_name='brute_force', source_ip=source_ip, incident_status__in=['open', 'acknowledged'])
                    alert.last_seen_at = window_end
                    alert.last_window_count = count_bf
                    if count_bf > alert.peak_window_count:
                        alert.peak_window_count = count_bf
                    alert.evidence = evidence_bf
                    alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
                except Alert.DoesNotExist:
                    pass
        # port scan
        res_ps = evaluate_port_scan(source_ip, window_start, window_end)
        if res_ps:
            evidence_ps, count_ps = res_ps
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
                        first_seen_at=window_start,
                        last_seen_at=window_end,
                        last_window_count=count_ps,
                        peak_window_count=count_ps,
                        evidence=evidence_ps,
                    )
                transaction.on_commit(lambda a_id=alert.id: _enqueue_investigation(a_id))
            except IntegrityError:
                try:
                    alert = Alert.objects.get(rule_name='port_scan', source_ip=source_ip, incident_status__in=['open', 'acknowledged'])
                    alert.last_seen_at = window_end
                    alert.last_window_count = count_ps
                    if count_ps > alert.peak_window_count:
                        alert.peak_window_count = count_ps
                    alert.evidence = evidence_ps
                    alert.save(update_fields=['last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'updated_at'])
                except Alert.DoesNotExist:
                    pass


def _enqueue_investigation(alert_id):
    try:
        from agent.tasks import run_investigation
        run_investigation.delay(alert_id)
    except Exception:
        try:
            alert = Alert.objects.get(id=alert_id)
            if alert.investigation_status == 'queued':
                alert.investigation_status = 'failed'
                alert.investigation_error = 'queue_unavailable'
                alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
        except Exception:
            pass
