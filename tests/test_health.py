import pytest


@pytest.mark.django_db
def test_health(client):
    resp = client.get('/api/health/')
    assert resp.status_code in [200, 503]
