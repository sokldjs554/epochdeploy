package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"epochdeploy/executor/internal/core"
)

type executeRequest struct {
	Expected core.Identity `json:"expected"`
}

type observeRequest struct {
	Identity core.Identity `json:"identity"`
}

type targetStore struct {
	mu      sync.RWMutex
	targets map[string]core.Identity
}

func newTargetStore() *targetStore {
	return &targetStore{targets: make(map[string]core.Identity)}
}

func targetKey(identity core.Identity) string {
	return strings.TrimSpace(identity.Project) + "\x00" + strings.TrimSpace(identity.Environment)
}

func (s *targetStore) put(identity core.Identity) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.targets[targetKey(identity)] = identity
}

func (s *targetStore) get(expected core.Identity) (core.Identity, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	identity, ok := s.targets[targetKey(expected)]
	return identity, ok
}

const maxClockSkew = 30 * time.Second

func main() {
	secret := os.Getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET")
	if secret == "" {
		log.Fatal("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET is required")
	}
	store := newTargetStore()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "epochdeploy-executor"})
	})
	mux.HandleFunc("POST /v1/targets/observe", signedHandler(secret, func(w http.ResponseWriter, body []byte) {
		var req observeRequest
		if !decodeOne(body, &req) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		store.put(req.Identity)
		writeJSON(w, http.StatusOK, map[string]string{"observed_fingerprint": core.Fingerprint(req.Identity)})
	}))
	mux.HandleFunc("POST /v1/execute", signedHandler(secret, func(w http.ResponseWriter, body []byte) {
		var req executeRequest
		if !decodeOne(body, &req) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		observed, ok := store.get(req.Expected)
		if !ok {
			writeJSON(w, http.StatusConflict, map[string]string{"error": "live target has not been observed by executor"})
			return
		}
		writeJSON(w, http.StatusOK, core.Compare(req.Expected, observed))
	}))

	port := os.Getenv("EPOCHDEPLOY_EXECUTOR_PORT")
	if port == "" {
		port = "9080"
	}
	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 2 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			log.Printf("executor graceful shutdown failed: %v", err)
		}
	}()

	log.Printf("epochdeploy executor listening on :%s", port)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func signedHandler(secret string, next func(http.ResponseWriter, []byte)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 64<<10))
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		if !validSignature(secret, r.Header.Get("X-EpochDeploy-Timestamp"), body, r.Header.Get("X-EpochDeploy-Signature"), time.Now()) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid executor signature"})
			return
		}
		next(w, body)
	}
}

func decodeOne(body []byte, dst any) bool {
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return false
	}
	return dec.Decode(&struct{}{}) == io.EOF
}

func validSignature(secret, timestamp string, body []byte, signature string, now time.Time) bool {
	unixSeconds, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	requestTime := time.Unix(unixSeconds, 0)
	if now.Sub(requestTime) > maxClockSkew || requestTime.Sub(now) > maxClockSkew {
		return false
	}
	const prefix = "sha256="
	if !strings.HasPrefix(signature, prefix) {
		return false
	}
	provided, err := hex.DecodeString(strings.TrimPrefix(signature, prefix))
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(timestamp))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write(body)
	return hmac.Equal(provided, mac.Sum(nil))
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
