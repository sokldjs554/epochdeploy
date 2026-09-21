def epoch_payload():
    return {
        "project":"payments-api", "environment":"prod",
        "commit_sha":"8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest":"sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        "config_hash":"cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        "pipeline_id":"7421"
    }


def create_epoch(client, operator):
    r = client.post('/api/epochs', json=epoch_payload(), headers=operator)
    assert r.status_code == 201, r.text
    epoch = r.json()
    assert epoch["pipeline_status"] == "pending"
    hook = {"object_attributes": {"id": int(epoch["pipeline_id"]), "status": "success", "sha": epoch["commit_sha"]}}
    headers = {"X-Gitlab-Token": "test-gitlab-token", "X-Gitlab-Event": "Pipeline Hook"}
    verified = client.post('/api/integrations/gitlab/webhook', json=hook, headers=headers)
    assert verified.status_code == 200, verified.text
    return client.get(f"/api/epochs/{epoch['id']}", headers=operator).json()


def test_happy_path_executes(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    assert client.post('/api/targets/observe',json=ident,headers=operator).status_code==200
    assert client.post(f"/api/epochs/{e['id']}/approve",headers=approver).status_code==200
    r=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'run-happy-0001'},headers=operator)
    assert r.status_code==200, r.text
    assert r.json()['outcome']=='EXECUTED'
    assert r.json()['differences']==[]


def test_stale_artifact_is_denied(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    ident['artifact_digest']='sha256:9999999999999999999999999999999999999999999999999999999999999999'
    client.post('/api/targets/observe',json=ident,headers=operator)
    r=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'run-drift-0001'},headers=operator)
    assert r.status_code==200
    body=r.json(); assert body['outcome']=='DENIED_STALE'; assert body['differences'][0]['field']=='artifact_digest'


def test_execute_requires_approval(client, operator):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    r=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'run-noapproval'},headers=operator)
    assert r.status_code==409


def test_mutable_refs_rejected(client, operator):
    p=epoch_payload(); p['artifact_digest']='latest-image-tag'
    r=client.post('/api/epochs',json=p,headers=operator)
    assert r.status_code==422


def test_pipeline_must_be_successful_before_approval(client, operator, approver):
    p=epoch_payload()
    r=client.post('/api/epochs',json=p,headers=operator); e=r.json()
    r=client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    assert r.status_code==409


def test_role_boundary_operator_cannot_approve(client, operator):
    e=create_epoch(client, operator)
    r=client.post(f"/api/epochs/{e['id']}/approve",headers=operator)
    assert r.status_code==403


def test_idempotency_reuses_receipt(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    payload={'idempotency_key':'same-key-0001'}
    a=client.post(f"/api/epochs/{e['id']}/execute",json=payload,headers=operator)
    b=client.post(f"/api/epochs/{e['id']}/execute",json=payload,headers=operator)
    assert a.status_code==b.status_code==200
    receipts=client.get(f"/api/epochs/{e['id']}/receipts",headers=operator).json()
    assert len(receipts)==1


def test_commit_drift_is_denied(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    ident['commit_sha']='ffffffffffffffffffffffffffffffffffffffff'
    client.post('/api/targets/observe',json=ident,headers=operator)
    body=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'run-commit-drift'},headers=operator).json()
    assert body['outcome']=='DENIED_STALE'
    assert body['differences'][0]['field']=='commit_sha'


def test_config_drift_is_denied(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    ident['config_hash']='cfg:ffffffffffffffffffffffffffffffff'
    client.post('/api/targets/observe',json=ident,headers=operator)
    body=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'run-config-drift'},headers=operator).json()
    assert body['outcome']=='DENIED_STALE'
    assert body['differences'][0]['field']=='config_hash'


def test_terminal_epoch_rejects_new_execution_key(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    first=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'terminal-first'},headers=operator)
    assert first.status_code==200 and first.json()['outcome']=='EXECUTED'
    second=client.post(f"/api/epochs/{e['id']}/execute",json={'idempotency_key':'terminal-second'},headers=operator)
    assert second.status_code==409


def test_idempotent_retry_preserves_stale_diff(client, operator, approver):
    e=create_epoch(client, operator)
    ident={k:e[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    client.post('/api/targets/observe',json=ident,headers=operator)
    client.post(f"/api/epochs/{e['id']}/approve",headers=approver)
    ident['artifact_digest']='sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    client.post('/api/targets/observe',json=ident,headers=operator)
    payload={'idempotency_key':'stale-retry-0001'}
    a=client.post(f"/api/epochs/{e['id']}/execute",json=payload,headers=operator).json()
    b=client.post(f"/api/epochs/{e['id']}/execute",json=payload,headers=operator).json()
    assert a==b
    assert b['differences'][0]['field']=='artifact_digest'


def test_pipeline_status_cannot_be_forged_on_create(client, operator):
    payload = epoch_payload()
    payload["pipeline_status"] = "success"
    response = client.post('/api/epochs', json=payload, headers=operator)
    assert response.status_code == 422


def test_approval_is_idempotent(client, operator, approver):
    epoch = create_epoch(client, operator)
    first = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    second = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_execute_requires_observed_target(client, operator, approver):
    epoch = create_epoch(client, operator)
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200
    response = client.post(
        f"/api/epochs/{epoch['id']}/execute",
        json={"idempotency_key": "missing-target-0001"},
        headers=operator,
    )
    assert response.status_code == 409


def test_executor_observation_failure_maps_to_502(client, operator, monkeypatch):
    class BrokenExecutor:
        def observe(self, identity):
            from app.executor_client import ExecutorBoundaryError
            raise ExecutorBoundaryError("down")

    monkeypatch.setattr("app.services.executor_client", lambda: BrokenExecutor())
    ident = {k: epoch_payload()[k] for k in ('project','environment','commit_sha','artifact_digest','config_hash')}
    response = client.post('/api/targets/observe', json=ident, headers=operator)
    assert response.status_code == 502
    assert response.json()['detail'] == 'executor observation unavailable'


def test_demo_bootstrap_keeps_pipeline_pending_until_demo_gitlab_hook(client, admin, approver):
    epoch = client.post('/api/demo/bootstrap', headers=admin).json()
    assert epoch['pipeline_status'] == 'pending'
    blocked = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    assert blocked.status_code == 409
    verified = client.post(f"/api/demo/gitlab-success/{epoch['id']}", headers=admin)
    assert verified.status_code == 200
    assert verified.json()['pipeline_status'] == 'success'
    approved = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    assert approved.status_code == 200


def test_integrations_status_reports_last_pipeline_event(client, admin, operator):
    epoch = client.post('/api/demo/bootstrap', headers=admin).json()
    client.post(f"/api/demo/gitlab-success/{epoch['id']}", headers=admin)
    response = client.get('/api/integrations/status', headers=operator)
    assert response.status_code == 200
    body = response.json()
    assert body['gitlab']['webhook_configured'] is True
    assert body['gitlab']['sha_binding'] is True
    assert body['gitlab']['last_event_type'] == 'Pipeline Hook'
    assert body['gitlab']['last_external_id'] == epoch['pipeline_id']
    assert body['executor']['request_auth'] in {'local', 'timestamped HMAC-SHA256'}


def test_evidence_can_be_listed_for_epoch(client, operator):
    epoch = create_epoch(client, operator)
    uploaded = client.post(
        f"/api/epochs/{epoch['id']}/evidence",
        headers=operator,
        data={'kind': 'provenance'},
        files={'file': ('provenance.txt', b'commit=abcdef1234567\n', 'text/plain')},
    )
    assert uploaded.status_code == 201
    listed = client.get(f"/api/epochs/{epoch['id']}/evidence", headers=operator)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]['filename'] == 'provenance.txt'
    assert rows[0]['kind'] == 'provenance'
