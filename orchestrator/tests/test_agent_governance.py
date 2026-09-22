def agent_payload():
    return {
        "project": "payments-api",
        "environment": "prod",
        "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest": "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        "config_hash": "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        "pipeline_id": "7421",
        "change_request_id": "ISSUE-184",
        "reason": "Payment retry policy caused intermittent production timeouts",
        "actor_id": "release-agent-01",
        "action": "deploy",
    }


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


def test_agent_change_preserves_why_and_who(client, operator):
    response = client.post("/api/agent/changes", json=agent_payload(), headers=operator)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["change"]["external_ref"] == "ISSUE-184"
    assert body["change"]["reason"] == agent_payload()["reason"]
    assert body["change"]["actor_type"] == "ai_agent"
    assert body["change"]["actor_id"] == "release-agent-01"
    assert body["change"]["requested_by"] == "operator"

    passport = client.get(
        f"/api/epochs/{body['epoch']['id']}/passport",
        headers=operator,
    )
    assert passport.status_code == 200
    data = passport.json()
    assert data["change"]["actor_type"] == "ai_agent"
    assert data["release"]["fingerprint"] == body["epoch"]["fingerprint"]
    assert [event["event_type"] for event in data["timeline"]] == [
        "EPOCH_CREATED",
        "CHANGE_REQUESTED",
    ]


def test_passport_tracks_verified_approval_evidence_and_execution(client, operator, approver):
    created = client.post("/api/agent/changes", json=agent_payload(), headers=operator)
    epoch = created.json()["epoch"]
    verify_pipeline(client, epoch)

    approval = client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver)
    assert approval.status_code == 200, approval.text

    identity = {
        key: epoch[key]
        for key in ("project", "environment", "commit_sha", "artifact_digest", "config_hash")
    }
    observed = client.post("/api/targets/observe", json=identity, headers=operator)
    assert observed.status_code == 200

    evidence = client.post(
        f"/api/epochs/{epoch['id']}/evidence",
        headers=operator,
        data={"kind": "provenance"},
        files={"file": ("build.txt", b"builder=gitlab\nattested=true\n", "text/plain")},
    )
    assert evidence.status_code == 201, evidence.text

    executed = client.post(
        f"/api/epochs/{epoch['id']}/execute",
        headers=operator,
        json={"idempotency_key": "passport-execute-0001"},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["outcome"] == "EXECUTED"

    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    event_types = [event["event_type"] for event in passport["timeline"]]
    assert event_types == [
        "EPOCH_CREATED",
        "CHANGE_REQUESTED",
        "PIPELINE_VERIFIED",
        "APPROVED",
        "EVIDENCE_ATTACHED",
        "EXECUTED",
    ]
    assert passport["approval"]["approver"] == "approver"
    assert passport["evidence"][0]["filename"] == "build.txt"
    assert passport["executions"][0]["outcome"] == "EXECUTED"


def test_idempotent_approval_does_not_duplicate_passport_event(client, operator, approver):
    created = client.post("/api/agent/changes", json=agent_payload(), headers=operator)
    epoch = created.json()["epoch"]
    verify_pipeline(client, epoch)
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200
    assert client.post(f"/api/epochs/{epoch['id']}/approve", headers=approver).status_code == 200

    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    approvals = [event for event in passport["timeline"] if event["event_type"] == "APPROVED"]
    assert len(approvals) == 1


def test_pipeline_sha_mismatch_is_visible_in_passport(client, operator):
    created = client.post("/api/agent/changes", json=agent_payload(), headers=operator)
    epoch = created.json()["epoch"]
    response = client.post(
        "/api/integrations/gitlab/webhook",
        json={
            "object_attributes": {
                "id": int(epoch["pipeline_id"]),
                "status": "success",
                "sha": "ffffffffffffffffffffffffffffffffffffffff",
            }
        },
        headers={
            "X-Gitlab-Token": "test-gitlab-token",
            "X-Gitlab-Event": "Pipeline Hook",
        },
    )
    assert response.status_code == 200
    passport = client.get(f"/api/epochs/{epoch['id']}/passport", headers=operator).json()
    assert passport["release"]["pipeline_status"] == "sha_mismatch"
    assert passport["timeline"][-1]["event_type"] == "PIPELINE_REJECTED"
