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

	"epochdeploy/executor/internal/boundary"
	"epochdeploy/executor/internal/core"
)

const testSecret = "gin-test-secret"

func identity() core.Identity {
	return core.Identity{
		Project: "payments-api", Environment: "prod", CommitSHA: "abc1234",
		ArtifactDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		ConfigHash:     "cfg:22222222222222222222222222222222",
	}
}

func signedRequest(t *testing.T, method, path string, payload any) *http.Request {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	mac := hmac.New(sha256.New, []byte(testSecret))
	_, _ = mac.Write([]byte(timestamp))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write(body)
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-EpochDeploy-Timestamp", timestamp)
	req.Header.Set("X-EpochDeploy-Signature", "sha256="+hex.EncodeToString(mac.Sum(nil)))
	return req
}

func TestHealthzAdvertisesGin(t *testing.T) {
	router := buildRouter(testSecret, boundary.NewTargetStore())
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	if !bytes.Contains(rr.Body.Bytes(), []byte(`"implementation":"gin"`)) {
		t.Fatalf("unexpected body: %s", rr.Body.String())
	}
}

func TestUnsignedExecutionIsRejected(t *testing.T) {
	router := buildRouter(testSecret, boundary.NewTargetStore())
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/v1/execute", bytes.NewBufferString(`{"expected":{}}`)))
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rr.Code)
	}
}

func TestObserveThenExecuteExactIdentity(t *testing.T) {
	store := boundary.NewTargetStore()
	router := buildRouter(testSecret, store)
	want := identity()

	observe := httptest.NewRecorder()
	router.ServeHTTP(observe, signedRequest(t, http.MethodPost, "/v1/targets/observe", map[string]any{"identity": want}))
	if observe.Code != http.StatusOK {
		t.Fatalf("observe status = %d: %s", observe.Code, observe.Body.String())
	}

	execute := httptest.NewRecorder()
	router.ServeHTTP(execute, signedRequest(t, http.MethodPost, "/v1/execute", map[string]any{"expected": want}))
	if execute.Code != http.StatusOK {
		t.Fatalf("execute status = %d: %s", execute.Code, execute.Body.String())
	}
	var result core.Result
	if err := json.Unmarshal(execute.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Outcome != "EXECUTED" || len(result.Differences) != 0 {
		t.Fatalf("unexpected result: %+v", result)
	}
}

func TestObservedDriftFailsClosed(t *testing.T) {
	store := boundary.NewTargetStore()
	router := buildRouter(testSecret, store)
	expected := identity()
	observed := expected
	observed.ArtifactDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

	observe := httptest.NewRecorder()
	router.ServeHTTP(observe, signedRequest(t, http.MethodPost, "/v1/targets/observe", map[string]any{"identity": observed}))
	if observe.Code != http.StatusOK {
		t.Fatalf("observe status = %d: %s", observe.Code, observe.Body.String())
	}

	execute := httptest.NewRecorder()
	router.ServeHTTP(execute, signedRequest(t, http.MethodPost, "/v1/execute", map[string]any{"expected": expected}))
	if execute.Code != http.StatusOK {
		t.Fatalf("execute status = %d: %s", execute.Code, execute.Body.String())
	}
	var result core.Result
	if err := json.Unmarshal(execute.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Outcome != "DENIED_STALE" || len(result.Differences) != 1 || result.Differences[0].Field != "artifact_digest" {
		t.Fatalf("unexpected result: %+v", result)
	}
}

func TestUnknownJSONFieldIsRejected(t *testing.T) {
	router := buildRouter(testSecret, boundary.NewTargetStore())
	req := signedRequest(t, http.MethodPost, "/v1/execute", map[string]any{
		"expected": identity(), "observed": identity(),
	})
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400: %s", rr.Code, rr.Body.String())
	}
}
