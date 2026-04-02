#!/bin/sh
# AgentSpan installer
# Installs the CLI binary, the Python SDK, and runs agentspan doctor.
# Usage: curl -fsSL https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.sh | sh
set -e

S3_BUCKET="https://agentspan.s3.us-east-2.amazonaws.com"
BINARY_NAME="agentspan"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

step()    { printf "\n${CYAN}${BOLD}[%s/5]${NC} %s\n" "$1" "$2"; }
ok()      { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "  ${YELLOW}!${NC} %s\n" "$1"; }
die()     { printf "\n${RED}Error:${NC} %s\n" "$1" >&2; exit 1; }

# ── Cleanup on unexpected exit ────────────────────────────────────────────────
TMP_DIR=""
cleanup() {
    [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

# ── Step 1: Detect platform ───────────────────────────────────────────────────
step 1 "Detecting platform..."

detect_os() {
    OS="$(uname -s)"
    case "$OS" in
        Linux*)   OS='linux';;
        Darwin*)  OS='darwin';;
        CYGWIN*)  OS='windows';;
        MINGW*)   OS='windows';;
        MSYS*)    OS='windows';;
        *) die "Unsupported operating system: $OS";;
    esac
}

detect_arch() {
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64|amd64)        ARCH='amd64';;
        arm64|aarch64)       ARCH='arm64';;
        *) die "Unsupported architecture: $ARCH";;
    esac
}

detect_os
detect_arch
ok "Platform: ${OS}/${ARCH}"

# ── Step 2: Check prerequisites ───────────────────────────────────────────────
step 2 "Checking prerequisites..."

PYTHON_CMD=""
PYTHON_OK=false

for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ver=$("$cmd" --version 2>&1 | sed 's/[^0-9.]//g' | cut -d. -f1-2)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge "$PYTHON_MIN_MAJOR" ] && [ "$minor" -ge "$PYTHON_MIN_MINOR" ] 2>/dev/null; then
            PYTHON_CMD="$cmd"
            PYTHON_OK=true
            ok "Python $("$cmd" --version 2>&1) found"
            break
        fi
    fi
done

if [ "$PYTHON_OK" = false ]; then
    warn "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ not found. The Python SDK will not be installed."
    warn "Download Python at: https://www.python.org/downloads/"
fi

if command -v uv >/dev/null 2>&1; then
    ok "uv found — will use uv for Python SDK install"
    UV_AVAILABLE=true
else
    UV_AVAILABLE=false
fi

if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
    ok "curl found"
elif command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
    ok "wget found"
else
    die "Neither curl nor wget found. Please install one and re-run."
fi

# ── Step 3: Download CLI binary + verify checksum ─────────────────────────────
step 3 "Downloading CLI binary..."

BINARY_FILENAME="${BINARY_NAME}_${OS}_${ARCH}"
if [ "$OS" = "windows" ]; then
    BINARY_FILENAME="${BINARY_FILENAME}.exe"
    BINARY_NAME="${BINARY_NAME}.exe"
fi

DOWNLOAD_URL="${S3_BUCKET}/cli/latest/${BINARY_FILENAME}"
CHECKSUM_URL="${S3_BUCKET}/cli/latest/${BINARY_FILENAME}.sha256"

TMP_DIR=$(mktemp -d)
TMP_FILE="$TMP_DIR/$BINARY_NAME"
TMP_CHECKSUM="$TMP_DIR/${BINARY_FILENAME}.sha256"

printf "  Downloading from: %s\n" "$DOWNLOAD_URL"

download() {
    url="$1"; dest="$2"
    if [ "$DOWNLOADER" = "curl" ]; then
        curl -fsSL --progress-bar "$url" -o "$dest"
    else
        wget -q --show-progress "$url" -O "$dest"
    fi
}

download "$DOWNLOAD_URL" "$TMP_FILE" || die "Failed to download binary."

# Verify checksum if the .sha256 sidecar is available
CHECKSUM_VERIFIED=false
if download "$CHECKSUM_URL" "$TMP_CHECKSUM" 2>/dev/null; then
    EXPECTED=$(cat "$TMP_CHECKSUM" | tr -d '[:space:]')
    if [ -n "$EXPECTED" ]; then
        if command -v sha256sum >/dev/null 2>&1; then
            ACTUAL=$(sha256sum "$TMP_FILE" | awk '{print $1}')
        elif command -v shasum >/dev/null 2>&1; then
            ACTUAL=$(shasum -a 256 "$TMP_FILE" | awk '{print $1}')
        else
            warn "No sha256sum or shasum available — skipping checksum verification."
            ACTUAL=""
        fi

        if [ -n "$ACTUAL" ]; then
            if [ "$ACTUAL" = "$EXPECTED" ]; then
                ok "Checksum verified (SHA256: ${ACTUAL:0:16}...)"
                CHECKSUM_VERIFIED=true
            else
                die "Checksum mismatch!\n  Expected: $EXPECTED\n  Got:      $ACTUAL\nThe download may be corrupted. Please try again."
            fi
        fi
    fi
else
    warn "Checksum file not available — skipping signature verification."
fi

chmod +x "$TMP_FILE"

# Install binary
if [ -w "$INSTALL_DIR" ]; then
    mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME"
    ok "Installed to $INSTALL_DIR/$BINARY_NAME"
else
    warn "$INSTALL_DIR is not writable — trying sudo..."
    sudo mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME" || die "Could not install to $INSTALL_DIR. Re-run with INSTALL_DIR=~/bin or as root."
    ok "Installed to $INSTALL_DIR/$BINARY_NAME (via sudo)"
fi

# Verify CLI is on PATH
if ! command -v "$BINARY_NAME" >/dev/null 2>&1; then
    warn "agentspan not found in PATH."
    warn "Add this to your shell profile and restart your terminal:"
    warn "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi

# ── Step 4: Install Python SDK ────────────────────────────────────────────────
step 4 "Installing Python SDK (agentspan)..."

if [ "$PYTHON_OK" = true ]; then
    SDK_INSTALLED=false

    if [ "$UV_AVAILABLE" = true ]; then
        printf "  Trying: uv pip install agentspan\n"
        if uv pip install agentspan 2>&1 | sed 's/^/  /'; then
            ok "Python SDK installed via uv"
            SDK_INSTALLED=true
        else
            warn "uv install failed — falling back to pip"
        fi
    fi

    if [ "$SDK_INSTALLED" = false ]; then
        for pip_cmd in pip3 "python3 -m pip" "python -m pip"; do
            printf "  Trying: %s install agentspan\n" "$pip_cmd"
            if $pip_cmd install agentspan 2>&1 | sed 's/^/  /'; then
                ok "Python SDK installed via $pip_cmd"
                SDK_INSTALLED=true
                break
            fi
        done
    fi

    if [ "$SDK_INSTALLED" = false ]; then
        warn "Could not install the Python SDK automatically."
        warn "Run manually: pip install agentspan"
    fi
else
    warn "Skipping Python SDK install (Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ required)."
fi

# ── Step 5: Verify with agentspan doctor ──────────────────────────────────────
step 5 "Running agentspan doctor..."

if command -v agentspan >/dev/null 2>&1; then
    printf "\n"
    agentspan doctor || warn "agentspan doctor reported issues — see above for details."
else
    warn "agentspan not in PATH yet — skipping doctor."
    warn "Run 'agentspan doctor' after adding $INSTALL_DIR to your PATH."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
printf "\n${GREEN}${BOLD}AgentSpan installation complete!${NC}\n"
printf "\nNext steps:\n"
printf "  1. Set your LLM API key:   export OPENAI_API_KEY=sk-...\n"
printf "  2. Start the server:       agentspan server start\n"
printf "  3. Open the UI:            http://localhost:6767\n"
printf "\nDocs: https://docs.agentspan.dev\n\n"
