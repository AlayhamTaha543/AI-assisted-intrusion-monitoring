import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parent.parent


def _run_settings_import(env_overrides):
    env = os.environ.copy()
    env.update(env_overrides)
    env['PYTHONPATH'] = str(ROOT)
    env.pop('DJANGO_SETTINGS_MODULE', None)
    return subprocess.run(
        [sys.executable, '-c', 'import config.settings'],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_secret_key_required_when_not_debug():
    result = _run_settings_import({'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': 'replace-me'})
    assert result.returncode != 0
    assert 'ImproperlyConfigured' in result.stderr

    result = _run_settings_import({'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': 'a-real-secret'})
    assert result.returncode == 0


def test_make_env_generates_key():
    makefile = (ROOT / 'Makefile').read_text()
    env_block = makefile.split('env:')[1].split('\n\n')[0]
    assert 'DJANGO_SECRET_KEY' in env_block
    assert 'secrets.token_urlsafe' in env_block


def test_celery_settings():
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT == 270
    assert settings.CELERY_TASK_TIME_LIMIT == 300
    assert settings.CELERY_TASK_ACKS_LATE is False
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1
    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert settings.CELERY_TASK_PUBLISH_RETRY is False
