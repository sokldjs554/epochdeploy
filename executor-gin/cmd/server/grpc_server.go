package main

import (
	"context"
	"log"
	"net"
	"time"

	"epochdeploy/executor/internal/boundary"
	"epochdeploy/executor/internal/core"
	executorv1 "epochdeploy/executor/ginserver/gen/executorv1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

type grpcExecutorService struct {
	executorv1.UnimplementedExecutorServer
	store            *boundary.TargetStore
	capabilitySecret string
}

func newGRPCServer(secret, capabilitySecret string, store *boundary.TargetStore) *grpc.Server {
	server := grpc.NewServer(grpc.UnaryInterceptor(grpcAuthInterceptor(secret)))
	executorv1.RegisterExecutorServer(server, &grpcExecutorService{
		store:            store,
		capabilitySecret: capabilitySecret,
	})
	return server
}

func startGRPCServer(port, secret, capabilitySecret string, store *boundary.TargetStore) (*grpc.Server, error) {
	listener, err := net.Listen("tcp", ":"+port)
	if err != nil {
		return nil, err
	}
	server := newGRPCServer(secret, capabilitySecret, store)
	go func() {
		if err := server.Serve(listener); err != nil {
			log.Printf("gRPC executor server 중지: %v", err)
		}
	}()
	return server, nil
}

func grpcAuthInterceptor(secret string) grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req any,
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (any, error) {
		if info.FullMethod == executorv1.Executor_Health_FullMethodName {
			return handler(ctx, req)
		}
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			return nil, status.Error(codes.Unauthenticated, "executor metadata가 없습니다.")
		}
		timestamps := md.Get("x-epochdeploy-timestamp")
		signatures := md.Get("x-epochdeploy-signature")
		if len(timestamps) != 1 || len(signatures) != 1 {
			return nil, status.Error(codes.Unauthenticated, "executor 서명이 없습니다.")
		}
		message, ok := req.(proto.Message)
		if !ok {
			return nil, status.Error(codes.Internal, "요청이 protobuf message가 아닙니다.")
		}
		payload, err := proto.MarshalOptions{Deterministic: true}.Marshal(message)
		if err != nil {
			return nil, status.Error(codes.Internal, "요청 직렬화에 실패했습니다.")
		}
		if !boundary.ValidRPCSignature(
			secret,
			timestamps[0],
			info.FullMethod,
			payload,
			signatures[0],
			time.Now(),
		) {
			return nil, status.Error(codes.Unauthenticated, "executor 서명이 유효하지 않습니다.")
		}
		return handler(ctx, req)
	}
}

func (s *grpcExecutorService) Health(
	context.Context,
	*executorv1.HealthRequest,
) (*executorv1.HealthResponse, error) {
	return &executorv1.HealthResponse{
		Status:         "ok",
		Service:        "epochdeploy-executor",
		Implementation: "gin",
		Transport:      "grpc",
	}, nil
}

func (s *grpcExecutorService) Observe(
	_ context.Context,
	req *executorv1.ObserveRequest,
) (*executorv1.ObserveResponse, error) {
	if req.GetIdentity() == nil {
		return nil, status.Error(codes.InvalidArgument, "identity가 필요합니다.")
	}
	identity := identityFromProto(req.GetIdentity())
	s.store.Put(identity)
	return &executorv1.ObserveResponse{
		ObservedFingerprint: core.Fingerprint(identity),
	}, nil
}

func (s *grpcExecutorService) Execute(
	_ context.Context,
	req *executorv1.ExecuteRequest,
) (*executorv1.ExecuteResponse, error) {
	if req.GetExpected() == nil {
		return nil, status.Error(codes.InvalidArgument, "expected identity가 필요합니다.")
	}
	expected := identityFromProto(req.GetExpected())
	if ctx := req.GetContext(); ctx != nil {
		err := boundary.ValidateAgentExecutionCapability(
			s.capabilitySecret,
			expected,
			boundary.AgentExecutionContext{
				EpochID:             ctx.GetEpochId(),
				ActorType:           ctx.GetActorType(),
				ActorID:             ctx.GetActorId(),
				Action:              ctx.GetAction(),
				ApprovedFingerprint: ctx.GetApprovedFingerprint(),
				CapabilityToken:     ctx.GetCapabilityToken(),
			},
			time.Now(),
		)
		if err != nil {
			return nil, status.Error(codes.PermissionDenied, err.Error())
		}
	}
	observed, ok := s.store.Get(expected)
	if !ok {
		return nil, status.Error(codes.FailedPrecondition, "executor가 live target을 아직 관찰하지 않았습니다.")
	}
	result := core.Compare(expected, observed)
	diffs := make([]*executorv1.Difference, 0, len(result.Differences))
	for _, diff := range result.Differences {
		diffs = append(diffs, &executorv1.Difference{
			Field:    diff.Field,
			Expected: diff.Expected,
			Observed: diff.Observed,
		})
	}
	return &executorv1.ExecuteResponse{
		Outcome:             result.Outcome,
		ObservedFingerprint: result.ObservedFingerprint,
		Reason:              result.Reason,
		Differences:         diffs,
	}, nil
}

func identityFromProto(in *executorv1.DeploymentIdentity) core.Identity {
	return core.Identity{
		Project:        in.GetProject(),
		Environment:    in.GetEnvironment(),
		CommitSHA:      in.GetCommitSha(),
		ArtifactDigest: in.GetArtifactDigest(),
		ConfigHash:     in.GetConfigHash(),
	}
}
