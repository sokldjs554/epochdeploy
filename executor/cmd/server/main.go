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
	"github.com/gin-gonic/gin"
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
const signedBodyKey = "epochdeploy.signed-body"

func main() {
	secret := os.Getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET")
	if secret == "" {
		log.Fatal("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET is required")
	}
	store := newTargetStore()

	gin.SetMode(gin.ReleaseMode)
	router := newRouter(secret, store)

	port := os.Getenv("EPOCHDEPLOY_EXECUTOR_PORT")
	if port == "" {
		port = "9080"
	}
	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           router,
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

	log.Printf("epochdeploy Gin executor listening on :%s", port)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func newRouter(secret string, store *targetStore) *gin.Engine {
	router := gin.New()
	router.Use(gin.Recovery())
	if err := router.SetTrustedProxies(nil); err != nil {
		panic(err)
	}

	router.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "epochdeploy-executor", "framework": "gin"})
	})

	signed := router.Group("/")
	signed.Use(signedMiddleware(secret))
	signed.POST("/v1/targets/observe", func(c *gin.Context) {
		var req observeRequest
		if !decodeSignedBody(c, &req) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
			return
		}
		store.put(req.Identity)
		c.JSON(http.StatusOK, gin.H{"observed_fingerprint": core.Fingerprint(req.Identity)})
	})
	signed.POST("/v1/execute", func(c *gin.Context) {
		var req executeRequest
		if !decodeSignedBody(c, &req) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
			return
		}
		observed, ok := store.get(req.Expected)
		if !ok {
			c.JSON(http.StatusConflict, gin.H{"error": "live target has not been observed by executor"})
			return
		}
		c.JSON(http.StatusOK, core.Compare(req.Expected, observed))
	})
	return router
}

func signedMiddleware(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		body, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, 64<<10))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
			return
		}
		if !validSignature(
			secret,
			c.GetHeader("X-EpochDeploy-Timestamp"),
			body,
			c.GetHeader("X-EpochDeploy-Signature"),
			time.Now(),
		) {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid executor signature"})
			return
		}
		c.Set(signedBodyKey, body)
		c.Request.Body = io.NopCloser(bytes.NewReader(body))
		c.Next()
	}
}

func decodeSignedBody(c *gin.Context, dst any) bool {
	value, ok := c.Get(signedBodyKey)
	if !ok {
		return false
	}
	body, ok := value.([]byte)
	if !ok {
		return false
	}
	return decodeOne(body, dst)
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
