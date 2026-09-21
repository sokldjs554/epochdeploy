from app.fingerprint import diff_identity, fingerprint


def identity():
    return {"project":"p", "environment":"prod", "commit_sha":"abc1234", "artifact_digest":"sha256:1111111111111111111111111111111111111111111111111111111111111111", "config_hash":"cfg:22222222222222222222222222222222"}


def test_fingerprint_deterministic():
    a = identity(); b = dict(reversed(list(a.items())))
    assert fingerprint(a) == fingerprint(b)


def test_diff_identity_reports_precise_field():
    a = identity(); b = identity(); b["config_hash"] = "cfg:33333333333333333333333333333333"
    assert diff_identity(a,b) == [{"field":"config_hash", "expected":a["config_hash"], "observed":b["config_hash"]}]


def test_cross_runtime_fingerprint_vector():
    expected = "074034cdaccbb753732b0212fb10ce1418aeda971956c570f586ed6f04bbdc13"
    v = {
        "project": "payments-api",
        "environment": "prod",
        "commit_sha": "abc1234",
        "artifact_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        "config_hash": "cfg:22222222222222222222222222222222",
    }
    assert fingerprint(v) == expected
    assert fingerprint({key: f"  {value}  " for key, value in v.items()}) == expected
