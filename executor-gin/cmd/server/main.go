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

type executionContext struct {
	EpochID             string `json:"epoch_id"`
	ActorType           string `json:"actor_type"`
	ActorID             string `json:"actor_id"`
	Action              string `json:"action"`
	ApprovedFingerprint string `json:"approved_fingerprint"`
	CapabilityToken     string `json:"capability_token"`
	PolicyDecision      string `json:"policy_decision,omitempty"`
	PolicyRule          string `json:"policy_rule,omitempty"`
}

type executeRequest struct {
	Expected core.Identity   `json:"expected"`
	Context  *executionContext `json:"context,omitempty"`
}

type observeRequest struct {
	Identity core.Identity `json:"identity"`
}

func buildRouter(secret, capabilitySecret string, store *boundary.TargetStore) *gin.Engine {
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
			c.JSON(http.StatusBadRequest, gin.H{"error": "요청 형식이 올바르지 않습니다."})
			return
		}
		store.Put(req.Identity)
		c.JSON(http.StatusOK, gin.H{"observed_fingerprint": core.Fingerprint(req.Identity)})
	})
	v1.POST("/execute", func(c *gin.Context) {
		var req executeRequest
		if !decodeSignedBody(c, &req) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "요청 형식이 올바르지 않습니다."})
			return
		}
		if req.Context != nil {
			err := boundary.ValidateAgentExecutionCapability(
				capabilitySecret,
				req.Expected,
				boundary.AgentExecutionContext{
					EpochID: req.Context.EpochID,
					ActorType: req.Context.ActorType,
					ActorID: req.Context.ActorID,
					Action: req.Context.Action,
					ApprovedFingerprint: req.Context.ApprovedFingerprint,
					CapabilityToken: req.Context.CapabilityToken,
				},
				time.Now(),
			)
			if err != nil {
				c.JSON(http.StatusForbidden, gin.H{"error": err.Error()})
				return
			}
		}
		observed, ok := store.Get(req.Expected)
		if !ok {
			c.JSON(http.StatusConflict, gin.H{"error": "executor가 live target을 아직 관찰하지 않았습니다."})
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
			c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "요청 형식이 올바르지 않습니다."})
			return
		}
		if !boundary.ValidSignature(
			secret,
			c.GetHeader("X-EpochDeploy-Timestamp"),
			body,
			c.GetHeader("X-EpochDeploy-Signature"),
			time.Now(),
		) {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "executor 서명이 유효하지 않습니다."})
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
		log.Fatal("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET 환경변수가 필요합니다.")
	}
	capabilitySecret := os.Getenv("EPOCHDEPLOY_CAPABILITY_SECRET")
	if capabilitySecret == "" {
		log.Fatal("EPOCHDEPLOY_CAPABILITY_SECRET 환경변수가 필요합니다.")
	}
	port := os.Getenv("EPOCHDEPLOY_EXECUTOR_PORT")
	if port == "" {
		port = "9080"
	}
	grpcPort := os.Getenv("EPOCHDEPLOY_EXECUTOR_GRPC_PORT")
	if grpcPort == "" {
		grpcPort = "9090"
	}
	store := boundary.NewTargetStore()
	grpcServer, err := startGRPCServer(grpcPort, secret, capabilitySecret, store)
	if err != nil {
		log.Fatalf("gRPC executor 시작 실패 :%s: %v", grpcPort, err)
	}

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           buildRouter(secret, capabilitySecret, store),
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
		grpcServer.GracefulStop()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			log.Printf("Gin executor 정상 종료 실패: %v", err)
		}
	}()

	log.Printf("epochdeploy Gin HTTP adapter 대기 중 :%s", port)
	log.Printf("epochdeploy gRPC executor 대기 중 :%s", grpcPort)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
