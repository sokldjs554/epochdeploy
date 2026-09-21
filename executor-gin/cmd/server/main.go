package main

import (
	"context"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"epochdeploy/executor/internal/boundary"
	"epochdeploy/executor/internal/core"
	"github.com/gin-gonic/gin"
)

const signedBodyKey = "epochdeploy.signed_body"

type executeRequest struct {
	Expected core.Identity `json:"expected"`
}

type observeRequest struct {
	Identity core.Identity `json:"identity"`
}

func buildRouter(secret string, store *boundary.TargetStore) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(gin.Recovery())

	router.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status": "ok", "service": "epochdeploy-executor", "implementation": "gin",
		})
	})

	v1 := router.Group("/v1")
	v1.Use(signedMiddleware(secret))
	v1.POST("/targets/observe", func(c *gin.Context) {
		var req observeRequest
		if !decodeSignedBody(c, &req) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
			return
		}
		store.Put(req.Identity)
		c.JSON(http.StatusOK, gin.H{"observed_fingerprint": core.Fingerprint(req.Identity)})
	})
	v1.POST("/execute", func(c *gin.Context) {
		var req executeRequest
		if !decodeSignedBody(c, &req) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
			return
		}
		observed, ok := store.Get(req.Expected)
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
		if !boundary.ValidSignature(
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
		c.Next()
	}
}

func decodeSignedBody(c *gin.Context, dst any) bool {
	value, ok := c.Get(signedBodyKey)
	if !ok {
		return false
	}
	body, ok := value.([]byte)
	return ok && boundary.DecodeOne(body, dst)
}

func main() {
	secret := os.Getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET")
	if secret == "" {
		log.Fatal("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET is required")
	}
	port := os.Getenv("EPOCHDEPLOY_EXECUTOR_PORT")
	if port == "" {
		port = "9080"
	}

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           buildRouter(secret, boundary.NewTargetStore()),
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
			log.Printf("Gin executor graceful shutdown failed: %v", err)
		}
	}()

	log.Printf("epochdeploy Gin executor listening on :%s", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
