package boundary

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"testing"
	"time"

	"epochdeploy/executor/internal/core"
)

func signForTest(secret, timestamp string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(timestamp))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write(body)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}

func TestValidSignature(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	body := []byte(`{"expected":{}}`)
	ts := "1700000000"
	sig := signForTest("secret", ts, body)
	if !ValidSignature("secret", ts, body, sig, now) {
		t.Fatal("valid signature rejected")
	}
	if ValidSignature("secret", ts, append(body, 'x'), sig, now) {
		t.Fatal("tampered body accepted")
	}
}

func TestSignatureRejectsStaleTimestamp(t *testing.T) {
	now := time.Unix(1_700_000_100, 0)
	body := []byte(`{}`)
	ts := "1700000000"
	if ValidSignature("secret", ts, body, signForTest("secret", ts, body), now) {
		t.Fatal("stale signature accepted")
	}
}

func TestTargetStoreSeparatesObservationFromExpectedIdentity(t *testing.T) {
	store := NewTargetStore()
	expected := core.Identity{
		Project: "payments-api", Environment: "prod", CommitSHA: "abc1234",
		ArtifactDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		ConfigHash:     "cfg:22222222222222222222222222222222",
	}
	observed := expected
	observed.ArtifactDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	store.Put(observed)
	got, ok := store.Get(expected)
	if !ok {
		t.Fatal("expected observed target")
	}
	if got.ArtifactDigest == expected.ArtifactDigest {
		t.Fatal("store returned caller expected identity instead of observed target")
	}
}
