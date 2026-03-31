#!/bin/bash
set -e

VERSION="${VERSION:-dev}"
COMMIT="${COMMIT:-$(git rev-parse --short HEAD 2>/dev/null || echo 'none')}"
DATE="${DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
LDFLAGS="-X github.com/agentspan-ai/agentspan/cli/cmd.Version=${VERSION} -X github.com/agentspan-ai/agentspan/cli/cmd.Commit=${COMMIT} -X github.com/agentspan-ai/agentspan/cli/cmd.Date=${DATE}"

mkdir -p dist

echo "Building agentspan CLI v${VERSION}..."

GOOS=darwin GOARCH=amd64 go build -ldflags "$LDFLAGS" -o dist/agentspan_darwin_amd64 .
echo "  Built: darwin/amd64"

GOOS=darwin GOARCH=arm64 go build -ldflags "$LDFLAGS" -o dist/agentspan_darwin_arm64 .
echo "  Built: darwin/arm64"

GOOS=linux GOARCH=amd64 go build -ldflags "$LDFLAGS" -o dist/agentspan_linux_amd64 .
echo "  Built: linux/amd64"

GOOS=linux GOARCH=arm64 go build -ldflags "$LDFLAGS" -o dist/agentspan_linux_arm64 .
echo "  Built: linux/arm64"

GOOS=windows GOARCH=amd64 go build -ldflags "$LDFLAGS" -o dist/agentspan_windows_amd64.exe .
echo "  Built: windows/amd64"

GOOS=windows GOARCH=arm64 go build -ldflags "$LDFLAGS" -o dist/agentspan_windows_arm64.exe .
echo "  Built: windows/arm64"

chmod +x dist/agentspan_*

echo ""
echo "Build complete! Binaries in dist/"
ls -lh dist/
