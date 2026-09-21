import hashlib


def test_evidence_upload_hashes_and_sanitizes_name(client, operator):
    p={
        "project":"payments-api","environment":"prod","commit_sha":"abcdef1234567",
        "artifact_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","config_hash":"cfg:22222222222222222222222222222222",
        "pipeline_id":"99"
    }
    e=client.post('/api/epochs',json=p,headers=operator).json()
    data=b'build provenance\ncommit=abcdef1234567\n'
    r=client.post(f"/api/epochs/{e['id']}/evidence",headers=operator,data={'kind':'provenance'},files={'file':('../secret.txt',data,'text/plain')})
    assert r.status_code==201, r.text
    body=r.json(); assert body['filename']=='secret.txt'; assert body['sha256']==hashlib.sha256(data).hexdigest()


def test_evidence_kind_length_is_bounded(client, operator):
    p={
        "project":"payments-api","environment":"prod","commit_sha":"abcdef1234567",
        "artifact_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","config_hash":"cfg:22222222222222222222222222222222",
        "pipeline_id":"99"
    }
    e=client.post('/api/epochs',json=p,headers=operator).json()
    r=client.post(
        f"/api/epochs/{e['id']}/evidence",
        headers=operator,
        data={'kind':'x'*41},
        files={'file':('evidence.txt',b'x','text/plain')},
    )
    assert r.status_code == 422
