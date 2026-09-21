package core

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

type Identity struct {
	Project        string `json:"project"`
	Environment    string `json:"environment"`
	CommitSHA      string `json:"commit_sha"`
	ArtifactDigest string `json:"artifact_digest"`
	ConfigHash     string `json:"config_hash"`
}

type Difference struct {
	Field    string `json:"field"`
	Expected string `json:"expected"`
	Observed string `json:"observed"`
}

type Result struct {
	Outcome             string       `json:"outcome"`
	ObservedFingerprint string       `json:"observed_fingerprint"`
	Reason              string       `json:"reason"`
	Differences         []Difference `json:"differences"`
}

func canonical(v string) string {
	return strings.TrimSpace(v)
}

func Fingerprint(v Identity) string {
	payload := map[string]string{
		"artifact_digest": canonical(v.ArtifactDigest),
		"commit_sha":      canonical(v.CommitSHA),
		"config_hash":     canonical(v.ConfigHash),
		"environment":     canonical(v.Environment),
		"project":         canonical(v.Project),
	}
	keys := make([]string, 0, len(payload))
	for k := range payload {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	ordered := make(map[string]string, len(payload))
	for _, k := range keys {
		ordered[k] = payload[k]
	}
	b, _ := json.Marshal(ordered)
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func Compare(expected, observed Identity) Result {
	diffs := make([]Difference, 0, 3)
	add := func(field, e, o string) {
		if e != o {
			diffs = append(diffs, Difference{Field: field, Expected: e, Observed: o})
		}
	}
	add("project", canonical(expected.Project), canonical(observed.Project))
	add("environment", canonical(expected.Environment), canonical(observed.Environment))
	add("commit_sha", canonical(expected.CommitSHA), canonical(observed.CommitSHA))
	add("artifact_digest", canonical(expected.ArtifactDigest), canonical(observed.ArtifactDigest))
	add("config_hash", canonical(expected.ConfigHash), canonical(observed.ConfigHash))

	observedFP := Fingerprint(observed)
	if len(diffs) > 0 {
		fields := ""
		for i, d := range diffs {
			if i > 0 {
				fields += ", "
			}
			fields += d.Field
		}
		return Result{Outcome: "DENIED_STALE", ObservedFingerprint: observedFP, Reason: fmt.Sprintf("execution target changed after approval: %s", fields), Differences: diffs}
	}
	return Result{Outcome: "EXECUTED", ObservedFingerprint: observedFP, Reason: "approved deployment identity matches live target", Differences: diffs}
}
