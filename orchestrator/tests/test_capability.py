from app.capability import CapabilityError, CapabilityScope, issue_capability, verify_capability


def payload(pipeline_id="7421"):
    return {
        "project": "payments-api",
        "environment": "prod",
        "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest": "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        "config_hash": "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        "pipeline_id": pipeline_id,
        "change_request_id": f"ISSUE-{pipeline_id}",
        "reason": "검증된 release 변경을 운영 환경에 배포하도록 Agent가 요청했습니다.",
        "actor_id": "release-agent-01",
        "action": "deploy",
    }


def create_agent_epoch(client, operator, pipeline_id="7421"):
    response = client.post("/api/agent/changes", json=payload(pipeline_id), headers=operator)
    assert response.status_code == 201, response.text
    return response.json()["epoch"]


def verify_pipeline(client, epoch):
    response = client.post(
        "/api/integrations/gitlab/webhook",
        json={
            "object_attributes": {
                "id": int(epoch["pipeline_id"]),
                "status": "success",
                "sha": epoch["commit_sha"],
            }
        },
        headers={
            "X-Gitlab-Token": "test-gitlab-token",
            "X-Gitlab-Event": "Pipeline Hook",
        },
    )
    assert response.status_code == 200, response.text


def observe(client, operator, epoch):
    identity = {
        key: epoch[key]
        for key in ("project", "environment", "commit_sha", "artifact_digest", "config_hash")
    }
    response = client.post("/api/targets/observe", json=identity, headers=operator)
    assert response.status_code == 200, response.text


def issue(client, approver, epoch):
    response = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        json={"ttl_seconds": 300},
        headers=approver,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_capability_requires_human_approval(client, operator, approver):
    epoch = create_agent_epoch(client, operator)
    verify_pipeline(client, epoch)
    response = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        json={"ttl_seconds": 300},
        headers=approver,
    )
    assert response.status_code == 409


def test_valid_capability_authorizes_agent_execution(client, operator, approver):
    epoch = create_agent_epoch(client, operator)
    verify_pipeline(client, epoch)
    observe(client, operator, epoch)
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200
    capability = issue(client, approver, epoch)

    response = client.post(
        f"/api/agent/epochs/{epoch['id']}/execute",
        json={
            "idempotency_key": "agent-capability-0001",
            "capability_token": capability["capability_token"],
        },
        headers=operator,
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "EXECUTED"

    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    assert passport["capabilities"][-1]["actor_type"] == "ai_agent"
    assert passport["capabilities"][-1]["actor_id"] == "release-agent-01"
    assert passport["capabilities"][-1]["action"] == "deploy"
    assert [e["event_type"] for e in passport["timeline"]][-2:] == [
        "CAPABILITY_ISSUED",
        "EXECUTED",
    ]
    assert capability["capability_token"] not in str(passport)


def test_capability_cannot_be_reused_for_another_epoch(client, operator, approver):
    first = create_agent_epoch(client, operator, "7421")
    second = create_agent_epoch(client, operator, "7422")
    for epoch in (first, second):
        verify_pipeline(client, epoch)
        assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200
    observe(client, operator, second)

    capability = issue(client, approver, first)
    response = client.post(
        f"/api/agent/epochs/{second['id']}/execute",
        json={
            "idempotency_key": "cross-epoch-0001",
            "capability_token": capability["capability_token"],
        },
        headers=operator,
    )
    assert response.status_code == 403
    assert "epoch_id" in response.json()["detail"]


def test_tampered_capability_is_rejected(client, operator, approver):
    epoch = create_agent_epoch(client, operator)
    verify_pipeline(client, epoch)
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200
    observe(client, operator, epoch)
    capability = issue(client, approver, epoch)["capability_token"]
    tampered = capability[:-1] + ("A" if capability[-1] != "A" else "B")

    response = client.post(
        f"/api/agent/epochs/{epoch['id']}/execute",
        json={"idempotency_key": "tampered-cap-0001", "capability_token": tampered},
        headers=operator,
    )
    assert response.status_code == 403


def test_expired_capability_fails_verification():
    scope = CapabilityScope(
        epoch_id="epoch-1",
        actor_type="ai_agent",
        actor_id="release-agent-01",
        project="payments-api",
        environment="prod",
        action="deploy",
        fingerprint="f" * 64,
    )
    token, _, _ = issue_capability(scope, ttl_seconds=-1)
    try:
        verify_capability(token, scope)
    except CapabilityError as exc:
        assert "만료" in str(exc)
    else:
        raise AssertionError("만료된 capability가 검증을 통과했습니다.")
