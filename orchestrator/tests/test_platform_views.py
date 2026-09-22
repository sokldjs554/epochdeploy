def epoch_payload():
    return {
        "project": "payments-api",
        "environment": "prod",
        "commit_sha": "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
        "artifact_digest": "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
        "config_hash": "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
        "pipeline_id": "7421",
    }


def create_verified_epoch(client, operator):
    created = client.post("/api/epochs", json=epoch_payload(), headers=operator)
    assert created.status_code == 201, created.text
    epoch = created.json()
    hook = {
        "object_attributes": {
            "id": int(epoch["pipeline_id"]),
            "status": "success",
            "sha": epoch["commit_sha"],
        }
    }
    verified = client.post(
        "/api/integrations/gitlab/webhook",
        json=hook,
        headers={"X-Gitlab-Token": "test-gitlab-token", "X-Gitlab-Event": "Pipeline Hook"},
    )
    assert verified.status_code == 200, verified.text
    return client.get(f"/api/epochs/{epoch['id']}", headers=operator).json()


def test_evidence_ledger_lists_uploaded_metadata(client, operator):
    epoch = create_verified_epoch(client, operator)
    payload = b"provenance=v1\ncommit=8f375e7\n"
    uploaded = client.post(
        f"/api/epochs/{epoch['id']}/evidence",
        headers=operator,
        data={"kind": "provenance"},
        files={"file": ("build.txt", payload, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text

    response = client.get(f"/api/epochs/{epoch['id']}/evidence", headers=operator)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["kind"] == "provenance"
    assert rows[0]["filename"] == "build.txt"
    assert rows[0]["size_bytes"] == len(payload)
    assert len(rows[0]["sha256"]) == 64
    assert rows[0]["content_type"] == "text/plain"


def test_integration_status_is_explicit_without_exposing_secrets(client, operator):
    response = client.get("/api/system/integrations", headers=operator)
    assert response.status_code == 200
    body = response.json()
    assert body["gitlab"]["status"] == "configured"
    assert body["gitlab"]["binding"] == "pipeline id + immutable commit SHA"
    assert body["executor"]["implementation"] == "local"
    assert body["executor"]["transport"] == "HMAC-SHA256 signed HTTP/JSON"
    assert body["executor"]["target_observation"] == "executor-owned"
    assert body["database"]["backend"] == "sqlite"
    assert body["grpc"]["status"] == "contract-only"
    serialized = response.text.lower()
    assert "test-gitlab-token" not in serialized
    assert "test-secret" not in serialized
