import json


def test_gitlab_pipeline_hook_updates_pipeline_status(client, operator):
    p={
        "project":"payments-api","environment":"prod","commit_sha":"abcdef1234567",
        "artifact_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","config_hash":"cfg:22222222222222222222222222222222",
        "pipeline_id":"99"
    }
    e=client.post('/api/epochs',json=p,headers=operator).json()
    payload={"object_attributes":{"id":99,"status":"success","sha":"abcdef1234567"}}
    headers={"X-Gitlab-Token":"test-gitlab-token","X-Gitlab-Event":"Pipeline Hook","Content-Type":"application/json"}
    r=client.post('/api/integrations/gitlab/webhook',content=json.dumps(payload),headers=headers)
    assert r.status_code==200
    got=client.get(f"/api/epochs/{e['id']}",headers=operator).json()
    assert got['pipeline_status']=='success'


def test_gitlab_duplicate_webhook_is_idempotent(client):
    payload={"object_attributes":{"id":99,"status":"success","sha":"abcdef1234567"}}
    headers={"X-Gitlab-Token":"test-gitlab-token","X-Gitlab-Event":"Pipeline Hook","Content-Type":"application/json"}
    a=client.post('/api/integrations/gitlab/webhook',content=json.dumps(payload),headers=headers).json()
    b=client.post('/api/integrations/gitlab/webhook',content=json.dumps(payload),headers=headers).json()
    assert a['duplicate'] is False and b['duplicate'] is True


def test_gitlab_bad_token_rejected(client):
    r=client.post('/api/integrations/gitlab/webhook',json={},headers={"X-Gitlab-Token":"bad"})
    assert r.status_code==401


def test_gitlab_pipeline_sha_mismatch_blocks_approval(client, operator, approver):
    p={
        "project":"payments-api","environment":"prod","commit_sha":"abcdef1234567",
        "artifact_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","config_hash":"cfg:22222222222222222222222222222222",
        "pipeline_id":"101"
    }
    e=client.post('/api/epochs',json=p,headers=operator).json()
    payload={"object_attributes":{"id":101,"status":"success","sha":"fffffff9999999"}}
    headers={"X-Gitlab-Token":"test-gitlab-token","X-Gitlab-Event":"Pipeline Hook","Content-Type":"application/json"}
    assert client.post('/api/integrations/gitlab/webhook',json=payload,headers=headers).status_code==200
    got=client.get(f"/api/epochs/{e['id']}",headers=operator).json()
    assert got['pipeline_status']=='sha_mismatch'
    assert client.post(f"/api/epochs/{e['id']}/approve",headers=approver).status_code==409


def test_gitlab_webhook_size_is_bounded(client):
    headers={"X-Gitlab-Token":"test-gitlab-token","X-Gitlab-Event":"Pipeline Hook","Content-Type":"application/json"}
    oversized = b'{' + (b' ' * (1024 * 1024))
    response = client.post('/api/integrations/gitlab/webhook', content=oversized, headers=headers)
    assert response.status_code == 413
