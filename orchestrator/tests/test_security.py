def test_unauthenticated_request_rejected(client):
    assert client.get('/api/epochs').status_code==401


def test_bad_login_rejected(client):
    assert client.post('/api/auth/token',json={'username':'operator','password':'wrong'}).status_code==401


def test_security_headers_present(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
