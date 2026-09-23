def dry_run(client, operator, *, env, action):
    response = client.post(
        "/api/policy/dry-run",
        headers=operator,
        json={
            "actor_type": "ai_agent",
            "action": action,
            "project": "payments-api",
            "environment": env,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def agent_payload(*, env, action, pipeline_id):
    return {
        "project": "payments-api",
        "environment": env,
        "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest": "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        "config_hash": "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        "pipeline_id": pipeline_id,
        "change_request_id": f"ISSUE-{pipeline_id}",
        "reason": "Agent가 시작한 release 요청의 정책 시뮬레이션",
        "actor_id": "release-agent-01",
        "action": action,
    }


def create_change(client, operator, *, env, action, pipeline_id):
    response = client.post(
        "/api/agent/changes",
        headers=operator,
        json=agent_payload(env=env, action=action, pipeline_id=pipeline_id),
    )
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
    response = client.post(
        "/api/targets/observe",
        headers=operator,
        json={
            key: epoch[key]
            for key in ("project", "environment", "commit_sha", "artifact_digest", "config_hash")
        },
    )
    assert response.status_code == 200, response.text


def test_policy_dry_run_returns_allow_ask_deny(client, operator):
    allow = dry_run(client, operator, env="staging", action="deploy")
    ask = dry_run(client, operator, env="prod", action="deploy")
    deny = dry_run(client, operator, env="prod", action="delete")
    assert allow["decision"] == "ALLOW"
    assert allow["rule_id"] == "allow-agent-nonprod-write"
    assert ask["decision"] == "ASK"
    assert "human-approval" in ask["required_controls"]
    assert deny["decision"] == "DENY"
    assert deny["rule_id"] == "deny-destructive-action"


def test_allow_policy_can_issue_and_execute_without_human_approval(client, operator):
    epoch = create_change(client, operator, env="staging", action="deploy", pipeline_id="8101")
    verify_pipeline(client, epoch)
    observe(client, operator, epoch)

    issued = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        headers=operator,
        json={"ttl_seconds": 300},
    )
    assert issued.status_code == 201, issued.text

    executed = client.post(
        f"/api/agent/epochs/{epoch['id']}/execute",
        headers=operator,
        json={
            "idempotency_key": "policy-allow-0001",
            "capability_token": issued.json()["capability_token"],
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["outcome"] == "EXECUTED"

    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    events = [event["event_type"] for event in passport["timeline"]]
    assert "POLICY_EVALUATED" in events
    assert "APPROVED" not in events
    policy_event = [event for event in passport["timeline"] if event["event_type"] == "POLICY_EVALUATED"][-1]
    assert policy_event["details"]["decision"] == "ALLOW"


def test_ask_policy_requires_human_approval(client, operator, approver):
    epoch = create_change(client, operator, env="prod", action="deploy", pipeline_id="8102")
    verify_pipeline(client, epoch)

    blocked = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        headers=operator,
        json={"ttl_seconds": 300},
    )
    assert blocked.status_code == 409
    assert "명시적인 사람 승인" in blocked.json()["detail"]

    approved = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    assert approved.status_code == 200
    issued = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        headers=approver,
        json={"ttl_seconds": 300},
    )
    assert issued.status_code == 201


def test_deny_policy_never_issues_capability(client, operator, approver):
    epoch = create_change(client, operator, env="prod", action="delete", pipeline_id="8103")
    verify_pipeline(client, epoch)
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200

    response = client.post(
        f"/api/epochs/{epoch['id']}/capabilities",
        headers=approver,
        json={"ttl_seconds": 300},
    )
    assert response.status_code == 403
    assert "위임할 수 없습니다" in response.json()["detail"]

    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    policy_events = [event for event in passport["timeline"] if event["event_type"] == "POLICY_EVALUATED"]
    assert policy_events[-1]["details"]["decision"] == "DENY"
    assert passport["capabilities"] == []
