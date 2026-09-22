package boundary

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"strconv"
	"strings"
	"sync"
	"time"

	"epochdeploy/executor/internal/core"
)

const MaxClockSkew = 30 * time.Second

type TargetStore struct {
	mu      sync.RWMutex
	targets map[string]core.Identity
}

func NewTargetStore() *TargetStore {
	return &TargetStore{targets: make(map[string]core.Identity)}
}

func TargetKey(identity core.Identity) string {
	return strings.TrimSpace(identity.Project) + "\x00" + strings.TrimSpace(identity.Environment)
}

func (s *TargetStore) Put(identity core.Identity) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.targets[TargetKey(identity)] = identity
}

func (s *TargetStore) Get(expected core.Identity) (core.Identity, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	identity, ok := s.targets[TargetKey(expected)]
	return identity, ok
}

func DecodeOne(body []byte, dst any) bool {
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return false
	}
	return dec.Decode(&struct{}{}) == io.EOF
}


type CapabilityClaims struct {
	Ver         int    `json:"ver"`
	JTI         string `json:"jti"`
	Typ         string `json:"typ"`
	EpochID     string `json:"epoch_id"`
	ActorType   string `json:"actor_type"`
	ActorID     string `json:"actor_id"`
	Project     string `json:"project"`
	Environment string `json:"environment"`
	Action      string `json:"action"`
	Fingerprint string `json:"fingerprint"`
	Exp         int64  `json:"exp"`
}

type CapabilityExpectation struct {
	EpochID     string
	ActorType   string
	ActorID     string
	Project     string
	Environment string
	Action      string
	Fingerprint string
}

func VerifyCapability(secret, token string, expected CapabilityExpectation, now time.Time) (CapabilityClaims, error) {
	var claims CapabilityClaims
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return claims, errors.New("invalid capability token")
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return claims, errors.New("invalid capability header")
	}
	var header map[string]any
	if err := json.Unmarshal(headerBytes, &header); err != nil || header["alg"] != "HS256" {
		return claims, errors.New("unsupported capability algorithm")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return claims, errors.New("invalid capability signature")
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(parts[0] + "." + parts[1]))
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return claims, errors.New("invalid capability signature")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || json.Unmarshal(payload, &claims) != nil {
		return claims, errors.New("invalid capability payload")
	}
	if claims.Ver != 1 || claims.Typ != "epochdeploy-capability" || claims.JTI == "" {
		return claims, errors.New("unsupported capability token")
	}
	if claims.Exp <= now.Unix() {
		return claims, errors.New("capability expired")
	}
	checks := []struct {
		name string
		got  string
		want string
	}{
		{"epoch_id", claims.EpochID, expected.EpochID},
		{"actor_type", claims.ActorType, expected.ActorType},
		{"actor_id", claims.ActorID, expected.ActorID},
		{"project", claims.Project, expected.Project},
		{"environment", claims.Environment, expected.Environment},
		{"action", claims.Action, expected.Action},
		{"fingerprint", claims.Fingerprint, expected.Fingerprint},
	}
	for _, check := range checks {
		if check.got != check.want {
			return claims, errors.New("capability scope mismatch: " + check.name)
		}
	}
	return claims, nil
}


type AgentExecutionContext struct {
	EpochID             string
	ActorType           string
	ActorID             string
	Action              string
	ApprovedFingerprint string
	CapabilityToken     string
}

func ValidateAgentExecutionCapability(secret string, expected core.Identity, exec AgentExecutionContext, now time.Time) error {
	if exec.ActorType != "ai_agent" {
		return nil
	}
	if exec.Action != "deploy" || exec.CapabilityToken == "" {
		return errors.New("AI agent execution requires a scoped deploy capability")
	}
	expectedFP := core.Fingerprint(expected)
	if exec.ApprovedFingerprint != expectedFP {
		return errors.New("capability approved fingerprint does not match expected release")
	}
	_, err := VerifyCapability(
		secret,
		exec.CapabilityToken,
		CapabilityExpectation{
			EpochID: exec.EpochID,
			ActorType: "ai_agent",
			ActorID: exec.ActorID,
			Project: expected.Project,
			Environment: expected.Environment,
			Action: "deploy",
			Fingerprint: expectedFP,
		},
		now,
	)
	return err
}

func ValidRPCSignature(secret, timestamp, method string, payload []byte, signature string, now time.Time) bool {
	unixSeconds, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	requestTime := time.Unix(unixSeconds, 0)
	if now.Sub(requestTime) > MaxClockSkew || requestTime.Sub(now) > MaxClockSkew {
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
	_, _ = mac.Write([]byte(method))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write(payload)
	return hmac.Equal(provided, mac.Sum(nil))
}

func ValidSignature(secret, timestamp string, body []byte, signature string, now time.Time) bool {
	unixSeconds, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	requestTime := time.Unix(unixSeconds, 0)
	if now.Sub(requestTime) > MaxClockSkew || requestTime.Sub(now) > MaxClockSkew {
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
