package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"epochdeploy/executor/internal/boundary"
	"epochdeploy/executor/internal/core"
)

type executeRequest struct {
	Expected core.Identity `json:"expected"`
}

type observeRequest struct {
	Identity core.Identity `json:"identity"`
}

func main() {
	secret := os.Getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET")
	if secret == "" {
		log.Fatal("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET is required")
	}
	store := boundary.NewTargetStore()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{
			"status": "ok", "service": "epochdeploy-executor", "implementation": "stdlib",
		})
	})
	mux.HandleFunc("POST /v1/targets/observe", signedHandler(secret, func(w http.ResponseWriter, body []byte) {
		var req observeRequest
		if !boundary.DecodeOne(body, &req) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		store.Put(req.Identity)
		writeJSON(w, http.StatusOK, map[string]string{"observed_fingerprint": core.Fingerprint(req.Identity)})
	}))
	mux.HandleFunc("POST /v1/execute", signedHandler(secret, func(w http.ResponseWriter, body []byte) {
		var req executeRequest
		if !boundary.DecodeOne(body, &req) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request"})
			return
		}
		observed, ok := store.Get(req.Expected)
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

	log.Printf("epochdeploy stdlib executor listening on :%s", port)
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
		if !boundary.ValidSignature(secret, r.Header.Get("X-EpochDeploy-Timestamp"), body, r.Header.Get("X-EpochDeploy-Signature"), time.Now()) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid executor signature"})
			return
		}
		next(w, body)
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
