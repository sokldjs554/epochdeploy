package boundary

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
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
