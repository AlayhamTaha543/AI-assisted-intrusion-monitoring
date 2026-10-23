import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from alerts.models import Alert
from .investigator import (
    InvalidOutputError,
    LLMResponseError,
    TransientLLMError,
    investigate,
)

logger = logging.getLogger(__name__)


def dispatch_investigation(alert_id, retry=True):
    try:
        run_investigation.apply_async(args=[alert_id], retry=retry)
        return True
    except Exception:
        logger.warning('queue dispatch failed for alert %s', alert_id)
        Alert.objects.filter(id=alert_id, investigation_status='queued').update(
            investigation_status='failed',
            investigation_error='queue_unavailable',
        )
        return False


@shared_task(bind=True)
def run_investigation(self, alert_id):
    try:
        updated = Alert.objects.filter(id=alert_id, investigation_status='queued').update(
            investigation_status='running',
            ai_used_tool=False,
            investigation_error='',
            investigation_started_at=timezone.now(),
            investigation_attempts=0,
        )
    except Exception:
        logger.exception('failed to claim alert %s', alert_id)
        return

    if not updated:
        return

    attempts = 0
    final_code = 'unexpected_error'

    try:
        while attempts < 2:
            attempts += 1
            Alert.objects.filter(id=alert_id).update(investigation_attempts=attempts)
            alert = Alert.objects.get(id=alert_id)
            try:
                result = investigate(alert)
                updated = Alert.objects.filter(id=alert_id, investigation_status='running').update(
                    ai_summary=result['summary'],
                    ai_recommended_actions=result['recommended_actions'],
                    ai_model=getattr(__import__('django.conf', fromlist=['settings']).settings, 'OLLAMA_MODEL', ''),
                    ai_used_tool=bool(result.get('used_tool')),
                    investigation_status='completed',
                    investigated_at=timezone.now(),
                    investigation_latency_ms=result.get('latency_ms'),
                    investigation_error='',
                )
                if not updated:
                    logger.info('result discarded: status changed during run alert=%s', alert_id)
                logger.info('investigation alert=%s attempt=%s outcome=completed', alert_id, attempts)
                return
            except TransientLLMError:
                final_code = 'llm_unavailable'
                logger.info('investigation alert=%s attempt=%s outcome=transient', alert_id, attempts)
                if attempts < 2:
                    time.sleep(5)
                    continue
                break
            except InvalidOutputError:
                final_code = 'invalid_output'
                logger.info('investigation alert=%s attempt=%s outcome=invalid_output', alert_id, attempts)
                break
            except LLMResponseError:
                final_code = 'llm_error'
                logger.info('investigation alert=%s attempt=%s outcome=llm_error', alert_id, attempts)
                break
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                final_code = 'unexpected_error'
                logger.exception('investigation alert=%s attempt=%s outcome=unexpected_error', alert_id, attempts)
                break

        Alert.objects.filter(id=alert_id, investigation_status='running').update(
            investigation_status='failed',
            investigation_error=final_code,
        )
    except SoftTimeLimitExceeded:
        Alert.objects.filter(id=alert_id, investigation_status='running').update(
            investigation_status='failed',
            investigation_error='time_limit',
        )
        logger.warning('investigation alert=%s outcome=time_limit', alert_id)
