import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone

from alerts.models import Alert
from .investigator import investigate


@shared_task(bind=True)
def run_investigation(self, alert_id):
    try:
        with transaction.atomic():
            alert = Alert.objects.select_for_update().get(id=alert_id)
            if alert.investigation_status != 'queued':
                return
            alert.investigation_status = 'running'
            alert.ai_used_tool = False
            alert.investigation_error = ''
            alert.investigation_attempts += 1
            alert.investigation_started_at = timezone.now()
            alert.save(update_fields=['investigation_status', 'ai_used_tool', 'investigation_error', 'investigation_attempts', 'investigation_started_at', 'updated_at'])
    except Exception:
        return

    try:
        alert = Alert.objects.get(id=alert_id)
        attempts = 0
        last_err = None
        while attempts < 2:
            try:
                result = investigate(alert)
                alert.ai_summary = result['summary']
                alert.ai_recommended_actions = result['recommended_actions']
                alert.ai_model = getattr(__import__('django.conf', fromlist=['settings']).settings, 'OLLAMA_MODEL', '')
                alert.ai_used_tool = bool(result.get('used_tool'))
                alert.investigation_status = 'completed'
                alert.investigated_at = timezone.now()
                alert.investigation_latency_ms = result.get('latency_ms')
                alert.investigation_error = ''
                alert.save(update_fields=['ai_summary', 'ai_recommended_actions', 'ai_model', 'ai_used_tool', 'investigation_status', 'investigated_at', 'investigation_latency_ms', 'investigation_error', 'updated_at'])
                return
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                last_err = e
                attempts += 1
                if attempts < 2:
                    time.sleep(5)
                else:
                    break
        alert = Alert.objects.get(id=alert_id)
        alert.investigation_status = 'failed'
        alert.investigation_error = 'investigation_failed'
        alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
    except SoftTimeLimitExceeded:
        try:
            alert = Alert.objects.get(id=alert_id)
            alert.investigation_status = 'failed'
            alert.investigation_error = 'timeout'
            alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
        except Exception:
            pass
    except Exception:
        try:
            alert = Alert.objects.get(id=alert_id)
            alert.investigation_status = 'failed'
            alert.investigation_error = 'investigation_failed'
            alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
        except Exception:
            pass
