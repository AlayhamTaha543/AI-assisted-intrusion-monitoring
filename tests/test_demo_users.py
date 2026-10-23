from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.authtoken.models import Token


def _run():
    out = StringIO()
    call_command('create_demo_users', stdout=out)
    return out.getvalue()


def _value(output, label):
    for line in output.splitlines():
        if line.startswith(label + '='):
            return line.split('=', 1)[1]
    return None


def test_create_demo_users_prints_tokens(db):
    output = _run()
    ingest = _value(output, 'INGEST_TOKEN')
    analyst = _value(output, 'ANALYST_TOKEN')
    assert ingest
    assert analyst
    assert Token.objects.get(user__username='ingestor1').key == ingest
    assert Token.objects.get(user__username='analyst1').key == analyst


def test_second_run_keeps_password(db, client):
    first = _run()
    password = _value(first, 'ANALYST_PASSWORD')
    assert password
    second = _run()
    assert _value(second, 'ANALYST_PASSWORD') == '(unchanged)'
    assert client.login(username='analyst1', password=password)


def test_env_password_applied(db, client, monkeypatch):
    monkeypatch.setenv('DEMO_USER_PASSWORD', 'abc12345XYZ')
    output = _run()
    assert _value(output, 'ANALYST_PASSWORD') == 'abc12345XYZ'
    assert client.login(username='analyst1', password='abc12345XYZ')
    assert User.objects.get(username='analyst1').check_password('abc12345XYZ')


def test_analyst_group_has_view_alert(db):
    _run()
    user = User.objects.get(username='analyst1')
    assert user.groups.get(name='analyst').permissions.filter(codename='view_alert').exists()
