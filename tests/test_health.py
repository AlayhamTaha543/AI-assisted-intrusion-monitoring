import pytest


@pytest.mark.django_db
def test_health(client):
    resp = client.get('/api/health/')
    assert resp.status_code == 200
