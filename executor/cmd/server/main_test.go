package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSignedHandlerRejectsUnsignedRequest(t *testing.T) {
	called := false
	handler := signedHandler("secret", func(w http.ResponseWriter, body []byte) {
		called = true
		w.WriteHeader(http.StatusNoContent)
	})
	req := httptest.NewRequest(http.MethodPost, "/v1/execute", strings.NewReader(`{"expected":{}}`))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("got status %d, want %d", rr.Code, http.StatusUnauthorized)
	}
	if called {
		t.Fatal("unsigned request reached protected handler")
	}
}
