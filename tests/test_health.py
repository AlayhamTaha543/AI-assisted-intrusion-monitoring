from unittest.mock import patch


def _redis_ok():
    return patch('config.urls.redis.from_url')


def test_health_ok(client, db):
    with _redis_ok() as from_url:
        from_url.return_value.ping.return_value = True
        resp = client.get('/api/health/')
    assert resp.status_code == 200
    body = resp.json()
    assert body == {'status': 'ok', 'db': True, 'redis': True}


def test_health_redis_down_503(client, db):
    with _redis_ok() as from_url:
        from_url.return_value.ping.side_effect = ConnectionError('down')
        resp = client.get('/api/health/')
    assert resp.status_code == 503
    body = resp.json()
    assert body['status'] == 'degraded'
    assert body['redis'] is False


def test_health_db_down_503(client, db):
    with _redis_ok() as from_url, patch('config.urls.connection') as conn:
        from_url.return_value.ping.return_value = True
        conn.cursor.side_effect = Exception('db down')
        resp = client.get('/api/health/')
    assert resp.status_code == 503
    assert resp.json()['db'] is False


def test_health_uses_redis_timeouts(client, db):
    with _redis_ok() as from_url:
        from_url.return_value.ping.return_value = True
        client.get('/api/health/')
    from_url.assert_called_once()
    _, kwargs = from_url.call_args
    assert kwargs['socket_connect_timeout'] == 1
    assert kwargs['socket_timeout'] == 1
