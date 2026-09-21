package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
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
	body := []byte(`{"expected":{},"observed":{}}`)
	ts := "1700000000"
	sig := signForTest("secret", ts, body)
	if !validSignature("secret", ts, body, sig, now) {
		t.Fatal("valid signature rejected")
	}
	if validSignature("secret", ts, append(body, 'x'), sig, now) {
		t.Fatal("tampered body accepted")
	}
}

func TestSignatureRejectsStaleTimestamp(t *testing.T) {
	now := time.Unix(1_700_000_100, 0)
	body := []byte(`{}`)
	ts := "1700000000"
	if validSignature("secret", ts, body, signForTest("secret", ts, body), now) {
		t.Fatal("stale signature accepted")
	}
}

func TestTargetStoreSeparatesObservationFromExecuteInput(t *testing.T) {
	store := newTargetStore()
	expected := sampleIdentityForServer()
	observed := expected
	observed.ArtifactDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	store.put(observed)
	got, ok := store.get(expected)
	if !ok {
		t.Fatal("expected observed target")
	}
	if got.ArtifactDigest == expected.ArtifactDigest {
		t.Fatal("store returned caller expected identity instead of observed target")
	}
}

func TestGinRouterRejectsUnsignedExecution(t *testing.T) {
	router := newRouter("secret", newTargetStore())
	req := httptest.NewRequest(http.MethodPost, "/v1/execute", bytes.NewBufferString(`{"expected":{}}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("got %d want %d: %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
}

func TestGinRouterObserveThenExecute(t *testing.T) {
	const secret = "secret"
	router := newRouter(secret, newTargetStore())
	identity := sampleIdentityForServer()

	observeBody, _ := json.Marshal(observeRequest{Identity: identity})
	observe := signedRequest(t, secret, http.MethodPost, "/v1/targets/observe", observeBody)
	observeRec := httptest.NewRecorder()
	router.ServeHTTP(observeRec, observe)
	if observeRec.Code != http.StatusOK {
		t.Fatalf("observe got %d: %s", observeRec.Code, observeRec.Body.String())
	}

	executeBody, _ := json.Marshal(executeRequest{Expected: identity})
	execute := signedRequest(t, secret, http.MethodPost, "/v1/execute", executeBody)
	executeRec := httptest.NewRecorder()
	router.ServeHTTP(executeRec, execute)
	if executeRec.Code != http.StatusOK {
		t.Fatalf("execute got %d: %s", executeRec.Code, executeRec.Body.String())
	}
	var result core.Result
	if err := json.Unmarshal(executeRec.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Outcome != "EXECUTED" {
		t.Fatalf("got outcome %s", result.Outcome)
	}
}

func signedRequest(t *testing.T, secret, method, path string, body []byte) *http.Request {
	t.Helper()
	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-EpochDeploy-Timestamp", timestamp)
	req.Header.Set("X-EpochDeploy-Signature", signForTest(secret, timestamp, body))
	return req
}

func sampleIdentityForServer() core.Identity {
	return core.Identity{
		Project:        "payments-api",
		Environment:    "prod",
		CommitSHA:      "8f375e7b64f6d20a3c1a1b2a6f9a1d9e2f7c1234",
		ArtifactDigest: "sha256:3a7d5d6259081b92f69359685c9b0f3f3f2ad7b3ce84b3ae6a711a3fa2d0ef77",
		ConfigHash:     "cfg:2e9d35a12347bd18bb3c9dcb7a4c8701",
	}
}
