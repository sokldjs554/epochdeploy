package core

import "testing"

func sample() Identity {
	return Identity{Project: "payments-api", Environment: "prod", CommitSHA: "abc1234", ArtifactDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111", ConfigHash: "cfg:22222222222222222222222222222222"}
}

func TestCompareExactMatchExecutes(t *testing.T) {
	v := sample()
	got := Compare(v, v)
	if got.Outcome != "EXECUTED" {
		t.Fatalf("got %s", got.Outcome)
	}
	if len(got.Differences) != 0 {
		t.Fatalf("unexpected diffs: %+v", got.Differences)
	}
}

func TestCompareCommitDriftFailsClosed(t *testing.T) {
	expected := sample()
	observed := sample()
	observed.CommitSHA = "def5678"
	got := Compare(expected, observed)
	if got.Outcome != "DENIED_STALE" {
		t.Fatalf("got %s", got.Outcome)
	}
	if len(got.Differences) != 1 || got.Differences[0].Field != "commit_sha" {
		t.Fatalf("bad diffs: %+v", got.Differences)
	}
}

func TestFingerprintIsDeterministic(t *testing.T) {
	v := sample()
	if Fingerprint(v) != Fingerprint(v) {
		t.Fatal("fingerprint changed")
	}
}

func TestCrossRuntimeFingerprintVector(t *testing.T) {
	const expected = "074034cdaccbb753732b0212fb10ce1418aeda971956c570f586ed6f04bbdc13"
	v := sample()
	if got := Fingerprint(v); got != expected {
		t.Fatalf("fingerprint mismatch: got %s want %s", got, expected)
	}
	v.Project = "  " + v.Project + "  "
	v.Environment = "  " + v.Environment + "  "
	v.CommitSHA = "  " + v.CommitSHA + "  "
	v.ArtifactDigest = "  " + v.ArtifactDigest + "  "
	v.ConfigHash = "  " + v.ConfigHash + "  "
	if got := Fingerprint(v); got != expected {
		t.Fatalf("canonicalization mismatch: got %s want %s", got, expected)
	}
}
