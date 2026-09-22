FROM golang:1.23-alpine AS build
WORKDIR /src
COPY executor /src/executor
COPY executor-gin /src/executor-gin
WORKDIR /src/executor-gin
RUN go mod download \
    && CGO_ENABLED=0 go test ./... \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/executor-gin ./cmd/server

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/executor-gin /executor-gin
EXPOSE 9080 9090
ENTRYPOINT ["/executor-gin"]
