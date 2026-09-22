package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net"
	"strconv"
	"testing"
	"time"

	"epochdeploy/executor/internal/boundary"
	"epochdeploy/executor/internal/core"
	executorv1 "epochdeploy/executor/ginserver/gen/executorv1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/proto"
)

const grpcBufSize = 1024 * 1024

func grpcTestClient(t *testing.T) (executorv1.ExecutorClient, func()) {
	t.Helper()
	listener := bufconn.Listen(grpcBufSize)
	server := newGRPCServer(testSecret, testCapabilitySecret, boundary.NewTargetStore())
	go func() {
		_ = server.Serve(listener)
	}()
	dialer := func(context.Context, string) (net.Conn, error) {
		return listener.Dial()
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	conn, err := grpc.DialContext(
		ctx,
		"bufnet",
		grpc.WithContextDialer(dialer),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	cancel()
	if err != nil {
		t.Fatal(err)
	}
	return executorv1.NewExecutorClient(conn), func() {
		_ = conn.Close()
		server.Stop()
		_ = listener.Close()
	}
}

func signedGRPCContext(t *testing.T, method string, message proto.Message) context.Context {
	t.Helper()
	payload, err := proto.MarshalOptions{Deterministic: true}.Marshal(message)
	if err != nil {
		t.Fatal(err)
	}
	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	mac := hmac.New(sha256.New, []byte(testSecret))
	_, _ = mac.Write([]byte(timestamp))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write([]byte(method))
	_, _ = mac.Write([]byte("."))
	_, _ = mac.Write(payload)
	return metadata.NewOutgoingContext(
		context.Background(),
		metadata.Pairs(
			"x-epochdeploy-timestamp", timestamp,
			"x-epochdeploy-signature", "sha256="+hex.EncodeToString(mac.Sum(nil)),
		),
	)
}

func protoIdentity(v core.Identity) *executorv1.DeploymentIdentity {
	return &executorv1.DeploymentIdentity{
		Project:        v.Project,
		Environment:    v.Environment,
		CommitSha:      v.CommitSHA,
		ArtifactDigest: v.ArtifactDigest,
		ConfigHash:     v.ConfigHash,
	}
}

func TestGRPCHealthAdvertisesTransport(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	response, err := client.Health(context.Background(), &executorv1.HealthRequest{})
	if err != nil {
		t.Fatal(err)
	}
	if response.GetImplementation() != "gin" || response.GetTransport() != "grpc" {
		t.Fatalf("unexpected health response: %+v", response)
	}
}

func TestGRPCObserveRejectsUnsignedRequest(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	_, err := client.Observe(
		context.Background(),
		&executorv1.ObserveRequest{Identity: protoIdentity(identity())},
	)
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("status = %s, want Unauthenticated: %v", status.Code(err), err)
	}
}

func TestGRPCObserveAndExecuteExactIdentity(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	want := identity()
	observe := &executorv1.ObserveRequest{Identity: protoIdentity(want)}
	if _, err := client.Observe(
		signedGRPCContext(t, executorv1.Executor_Observe_FullMethodName, observe),
		observe,
	); err != nil {
		t.Fatal(err)
	}
	execute := &executorv1.ExecuteRequest{Expected: protoIdentity(want)}
	response, err := client.Execute(
		signedGRPCContext(t, executorv1.Executor_Execute_FullMethodName, execute),
		execute,
	)
	if err != nil {
		t.Fatal(err)
	}
	if response.GetOutcome() != "EXECUTED" || len(response.GetDifferences()) != 0 {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestGRPCStaleArtifactFailsClosed(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	expected := identity()
	observed := expected
	observed.ArtifactDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	observe := &executorv1.ObserveRequest{Identity: protoIdentity(observed)}
	if _, err := client.Observe(
		signedGRPCContext(t, executorv1.Executor_Observe_FullMethodName, observe),
		observe,
	); err != nil {
		t.Fatal(err)
	}
	execute := &executorv1.ExecuteRequest{Expected: protoIdentity(expected)}
	response, err := client.Execute(
		signedGRPCContext(t, executorv1.Executor_Execute_FullMethodName, execute),
		execute,
	)
	if err != nil {
		t.Fatal(err)
	}
	if response.GetOutcome() != "DENIED_STALE" || len(response.GetDifferences()) != 1 {
		t.Fatalf("unexpected response: %+v", response)
	}
	if response.GetDifferences()[0].GetField() != "artifact_digest" {
		t.Fatalf("unexpected differences: %+v", response.GetDifferences())
	}
}

func TestGRPCAgentCapabilityIsVerifiedAtExecutor(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	want := identity()
	observe := &executorv1.ObserveRequest{Identity: protoIdentity(want)}
	if _, err := client.Observe(
		signedGRPCContext(t, executorv1.Executor_Observe_FullMethodName, observe),
		observe,
	); err != nil {
		t.Fatal(err)
	}
	token := capabilityToken(t, want, "epoch-grpc-001", "release-agent-01", time.Now().Add(5*time.Minute))
	execute := &executorv1.ExecuteRequest{
		Expected: protoIdentity(want),
		Context: &executorv1.ExecutionContext{
			EpochId:             "epoch-grpc-001",
			ActorType:           "ai_agent",
			ActorId:             "release-agent-01",
			Action:              "deploy",
			ApprovedFingerprint: core.Fingerprint(want),
			CapabilityToken:     token,
			PolicyDecision:      "ASK",
			PolicyRule:          "ask-agent-production-write",
		},
	}
	response, err := client.Execute(
		signedGRPCContext(t, executorv1.Executor_Execute_FullMethodName, execute),
		execute,
	)
	if err != nil {
		t.Fatal(err)
	}
	if response.GetOutcome() != "EXECUTED" {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestGRPCRejectsCrossEpochCapability(t *testing.T) {
	client, cleanup := grpcTestClient(t)
	defer cleanup()
	want := identity()
	observe := &executorv1.ObserveRequest{Identity: protoIdentity(want)}
	if _, err := client.Observe(
		signedGRPCContext(t, executorv1.Executor_Observe_FullMethodName, observe),
		observe,
	); err != nil {
		t.Fatal(err)
	}
	token := capabilityToken(t, want, "epoch-original", "release-agent-01", time.Now().Add(5*time.Minute))
	execute := &executorv1.ExecuteRequest{
		Expected: protoIdentity(want),
		Context: &executorv1.ExecutionContext{
			EpochId:             "epoch-other",
			ActorType:           "ai_agent",
			ActorId:             "release-agent-01",
			Action:              "deploy",
			ApprovedFingerprint: core.Fingerprint(want),
			CapabilityToken:     token,
		},
	}
	_, err := client.Execute(
		signedGRPCContext(t, executorv1.Executor_Execute_FullMethodName, execute),
		execute,
	)
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("status = %s, want PermissionDenied: %v", status.Code(err), err)
	}
}
