#!/bin/sh
# AgentSpan installer
# Installs Java 21+, the CLI binary, the Python SDK, and runs agentspan doctor.
# Usage: curl -fsSL https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.sh | sh
set -e

S3_BUCKET="https://agentspan.s3.us-east-2.amazonaws.com"
BINARY_NAME="agentspan"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10
JAVA_MIN=21

ADOPTIUM_URL="https://adoptium.net/temurin/releases/?version=${JAVA_MIN}"
PYTHON_URL="https://www.python.org/downloads/"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

step() { printf "\n${CYAN}${BOLD}[%s/6]${NC} %s\n" "$1" "$2"; }
ok()   { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${NC} %s\n" "$1"; }
info() { printf "       %s\n" "$1"; }
die()  { printf "\n${RED}Error:${NC} %s\n" "$1" >&2; exit 1; }

# ── Prompt helper ─────────────────────────────────────────────────────────────
# Works even when the script is piped through `curl | sh` by reading from /dev/tty.
prompt_yn() {
    printf "  ${YELLOW}?${NC} %s [y/N] " "$1"
    read -r answer </dev/tty 2>/dev/null || answer="n"
    case "$answer" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

# ── Cleanup on unexpected exit ────────────────────────────────────────────────
TMP_DIR=""
cleanup() { [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

# ── Step 1: Detect platform ───────────────────────────────────────────────────
step 1 "Detecting platform..."

detect_os() {
    OS="$(uname -s)"
    case "$OS" in
        Linux*)            OS='linux';;
        Darwin*)           OS='darwin';;
        CYGWIN*|MINGW*|MSYS*) OS='windows';;
        *) die "Unsupported operating system: $OS";;
    esac
}

detect_arch() {
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64|amd64)    ARCH='amd64';;
        arm64|aarch64)   ARCH='arm64';;
        armv7l|armv6l)   die "32-bit ARM (${ARCH}) is not supported. Pre-built binaries require arm64 or amd64.";;
        *) die "Unsupported architecture: $ARCH. See https://docs.agentspan.dev for manual install options.";;
    esac
}

detect_os
detect_arch
ok "Platform: ${OS}/${ARCH}"

# Detect Linux package manager for auto-installs
PKG_MGR=""
if [ "$OS" = "linux" ]; then
    if   command -v apt-get >/dev/null 2>&1; then PKG_MGR="apt"
    elif command -v dnf     >/dev/null 2>&1; then PKG_MGR="dnf"
    elif command -v yum     >/dev/null 2>&1; then PKG_MGR="yum"
    elif command -v pacman  >/dev/null 2>&1; then PKG_MGR="pacman"
    fi
fi

# ── Step 2: Check + install prerequisites ─────────────────────────────────────
step 2 "Checking prerequisites..."

# ── Java ──────────────────────────────────────────────────────────────────────
# Check Java version for a given binary path. Sets JAVA_OK=true and returns 0 if ok.
check_java_bin() {
    _bin="$1"
    [ -z "$_bin" ] && return 1
    command -v "$_bin" >/dev/null 2>&1 || [ -x "$_bin" ] || return 1
    _ver=$("$_bin" -version 2>&1 | head -1 | sed 's/.*"\(.*\)".*/\1/' | cut -d. -f1)
    # Old 1.x versioning (e.g. Java 8 reports "1.8")
    if [ "$_ver" = "1" ]; then
        _ver=$("$_bin" -version 2>&1 | head -1 | sed 's/.*"\(.*\)".*/\1/' | cut -d. -f2)
    fi
    if [ "$_ver" -ge "$JAVA_MIN" ] 2>/dev/null; then
        ok "Java $_ver found"
        JAVA_OK=true
        return 0
    fi
    return 1
}

JAVA_OK=false

# Search order: JAVA_HOME → sdkman → asdf → PATH
# This covers users who have Java installed via version managers that don't
# activate in non-interactive shells (which is what `curl | sh` runs as).
for _java_candidate in \
    "${JAVA_HOME:+$JAVA_HOME/bin/java}" \
    "$HOME/.sdkman/candidates/java/current/bin/java" \
    "$HOME/.asdf/shims/java" \
    "java"; do
    [ -z "$_java_candidate" ] && continue
    if check_java_bin "$_java_candidate"; then
        break
    fi
done

# Also check JAVA_HOME env if set but not already found (handles jenv, jabba, etc.)
if [ "$JAVA_OK" = false ] && [ -n "$JAVA_HOME" ]; then
    _jenv_java="$(jenv which java 2>/dev/null)" || true
    [ -n "$_jenv_java" ] && check_java_bin "$_jenv_java" || true
fi

if [ "$JAVA_OK" = false ]; then
    warn "Java ${JAVA_MIN}+ is required to run the AgentSpan server."
    if prompt_yn "Install Java ${JAVA_MIN} (Eclipse Temurin) now?"; then
        JAVA_INSTALLED=false

        if [ "$OS" = "darwin" ] && command -v brew >/dev/null 2>&1; then
            info "Running: brew install --cask temurin@${JAVA_MIN}"
            brew install --cask "temurin@${JAVA_MIN}" && JAVA_INSTALLED=true

        elif [ "$OS" = "linux" ]; then
            case "$PKG_MGR" in
                apt)
                    info "Adding Eclipse Temurin apt repository..."
                    sudo apt-get install -y wget apt-transport-https gnupg 2>/dev/null
                    sudo mkdir -p /etc/apt/keyrings
                    wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public \
                        | sudo tee /etc/apt/keyrings/adoptium.asc >/dev/null
                    printf "deb [signed-by=/etc/apt/keyrings/adoptium.asc] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo "$VERSION_CODENAME") main\n" \
                        | sudo tee /etc/apt/sources.list.d/adoptium.list >/dev/null
                    sudo apt-get update -q
                    sudo apt-get install -y "temurin-${JAVA_MIN}-jdk" && JAVA_INSTALLED=true
                    ;;
                dnf|yum)
                    info "Adding Eclipse Temurin RPM repository..."
                    cat <<EOF | sudo tee /etc/yum.repos.d/adoptium.repo >/dev/null
[Adoptium]
name=Adoptium
baseurl=https://packages.adoptium.net/artifactory/rpm/\$releasever/\$basearch
enabled=1
gpgcheck=1
gpgkey=https://packages.adoptium.net/artifactory/api/gpg/key/public
EOF
                    sudo "$PKG_MGR" install -y "temurin-${JAVA_MIN}-jdk" && JAVA_INSTALLED=true
                    ;;
                pacman)
                    if command -v yay >/dev/null 2>&1; then
                        yay -S --noconfirm "jdk${JAVA_MIN}-temurin" && JAVA_INSTALLED=true
                    else
                        warn "yay not found. Install Java manually: $ADOPTIUM_URL"
                    fi
                    ;;
                *)
                    warn "Unknown package manager. Install Java ${JAVA_MIN}+ manually:"
                    warn "  $ADOPTIUM_URL"
                    ;;
            esac
        else
            warn "Automatic Java install not supported on this platform."
            warn "Download Java ${JAVA_MIN} from: $ADOPTIUM_URL"
        fi

        if [ "$JAVA_INSTALLED" = true ]; then
            ok "Java ${JAVA_MIN} installed"
        else
            warn "Java install did not complete. Install manually before running 'agentspan server start':"
            warn "  $ADOPTIUM_URL"
        fi
    else
        warn "Skipping Java install. You will need Java ${JAVA_MIN}+ to run 'agentspan server start'."
        warn "  $ADOPTIUM_URL"
    fi
fi

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON_CMD=""
PYTHON_OK=false

# Search order: versioned names first (more specific), then generic python3/python.
# This avoids picking up the macOS system stub (Python 3.9) when a newer version
# is installed via Homebrew, pyenv, or asdf but not symlinked as `python3`.
for cmd in \
    "python3.13" "python3.12" "python3.11" "python3.10" \
    "$HOME/.asdf/shims/python3" \
    "$HOME/.pyenv/shims/python3" \
    "python3" "python"; do
    command -v "$cmd" >/dev/null 2>&1 || continue
    ver=$("$cmd" --version 2>&1 | sed 's/[^0-9.]//g' | cut -d. -f1-2)
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -ge "$PYTHON_MIN_MAJOR" ] && [ "$minor" -ge "$PYTHON_MIN_MINOR" ] 2>/dev/null; then
        PYTHON_CMD="$cmd"
        PYTHON_OK=true
        ok "Python $("$cmd" --version 2>&1) found ($cmd)"
        break
    fi
done

if [ "$PYTHON_OK" = false ]; then
    warn "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ is required for the Python SDK."
    if prompt_yn "Install Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} now?"; then
        PYTHON_INSTALLED=false

        if [ "$OS" = "darwin" ] && command -v brew >/dev/null 2>&1; then
            info "Running: brew install python@3.${PYTHON_MIN_MINOR}"
            brew install "python@3.${PYTHON_MIN_MINOR}" && PYTHON_INSTALLED=true
            PYTHON_CMD="python3.${PYTHON_MIN_MINOR}"; PYTHON_OK=true

        elif [ "$OS" = "linux" ]; then
            case "$PKG_MGR" in
                apt)
                    sudo apt-get install -y \
                        "python${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}" \
                        "python${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}-venv" \
                        "python${PYTHON_MIN_MAJOR}-pip" && PYTHON_INSTALLED=true
                    PYTHON_CMD="python${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"; PYTHON_OK=true
                    ;;
                dnf|yum)
                    sudo "$PKG_MGR" install -y "python${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}" && PYTHON_INSTALLED=true
                    PYTHON_CMD="python${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"; PYTHON_OK=true
                    ;;
                pacman)
                    sudo pacman -S --noconfirm python && PYTHON_INSTALLED=true
                    PYTHON_CMD="python"; PYTHON_OK=true
                    ;;
                *)
                    warn "Unknown package manager. Install Python manually: $PYTHON_URL"
                    ;;
            esac
        else
            warn "Automatic Python install not supported on this platform."
            warn "Download from: $PYTHON_URL"
        fi

        if [ "$PYTHON_INSTALLED" = true ]; then
            ok "Python installed"
        else
            warn "Python install did not complete. Install manually: $PYTHON_URL"
        fi
    else
        warn "Skipping Python install. The Python SDK will not be installed."
        warn "  $PYTHON_URL"
    fi
fi

# ── uv (optional, faster installs) ───────────────────────────────────────────
UV_AVAILABLE=false
if command -v uv >/dev/null 2>&1; then
    ok "uv found — will use uv for Python SDK install"
    UV_AVAILABLE=true
fi

# ── curl / wget ───────────────────────────────────────────────────────────────
if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
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
VERSION_URL="${S3_BUCKET}/cli/latest/version.txt"

TMP_DIR=$(mktemp -d)
TMP_FILE="$TMP_DIR/$BINARY_NAME"
TMP_CHECKSUM="$TMP_DIR/${BINARY_FILENAME}.sha256"

download() {
    url="$1"; dest="$2"
    if [ "$DOWNLOADER" = "curl" ]; then
        curl -fsSL --progress-bar "$url" -o "$dest"
    else
        wget -q --show-progress "$url" -O "$dest"
    fi
}

# Check if already up to date — skip the 306MB download if version matches
CLI_SKIP=false
if command -v agentspan >/dev/null 2>&1; then
    CURRENT_VER=$(agentspan version 2>/dev/null | awk '{print $2}') || CURRENT_VER=""
    if [ -n "$CURRENT_VER" ]; then
        if download "$VERSION_URL" "$TMP_DIR/version.txt" 2>/dev/null; then
            LATEST_VER=$(tr -d '[:space:]' < "$TMP_DIR/version.txt")
            if [ "$CURRENT_VER" = "$LATEST_VER" ]; then
                ok "CLI already up to date ($CURRENT_VER) — skipping download"
                CLI_SKIP=true
            else
                info "Upgrading CLI: $CURRENT_VER → $LATEST_VER"
            fi
        fi
    fi
fi

if [ "$CLI_SKIP" = false ]; then
    info "From: $DOWNLOAD_URL"
    download "$DOWNLOAD_URL" "$TMP_FILE" || die "Failed to download binary."

    # Verify checksum
    if download "$CHECKSUM_URL" "$TMP_CHECKSUM" 2>/dev/null; then
        EXPECTED=$(tr -d '[:space:]' < "$TMP_CHECKSUM")
        if [ -n "$EXPECTED" ]; then
            if   command -v sha256sum >/dev/null 2>&1; then ACTUAL=$(sha256sum "$TMP_FILE" | awk '{print $1}')
            elif command -v shasum    >/dev/null 2>&1; then ACTUAL=$(shasum -a 256 "$TMP_FILE" | awk '{print $1}')
            else warn "sha256sum/shasum not available — skipping checksum verification."; ACTUAL=""
            fi
            if [ -n "$ACTUAL" ]; then
                if [ "$ACTUAL" = "$EXPECTED" ]; then
                    ok "Checksum verified (SHA256: $(printf '%.16s' "$ACTUAL")...)"
                else
                    die "Checksum mismatch!\n  Expected: $EXPECTED\n  Got:      $ACTUAL\nDownload may be corrupted. Please try again."
                fi
            fi
        fi
    else
        warn "Checksum file not available — skipping signature verification."
    fi

    chmod +x "$TMP_FILE"

    # Install
    if [ -w "$INSTALL_DIR" ]; then
        mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME"
        ok "Installed to $INSTALL_DIR/$BINARY_NAME"
    else
        warn "$INSTALL_DIR is not writable — trying sudo..."
        sudo mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME" \
            || die "Could not install to $INSTALL_DIR. Re-run with INSTALL_DIR=~/bin or as root."
        ok "Installed to $INSTALL_DIR/$BINARY_NAME (via sudo)"
    fi
fi

# ── PATH ──────────────────────────────────────────────────────────────────────
if ! command -v agentspan >/dev/null 2>&1; then
    warn "agentspan not found in PATH."
    SHELL_NAME=$(basename "${SHELL:-sh}")
    case "$SHELL_NAME" in
        zsh)  PROFILE="$HOME/.zshrc" ;;
        bash) if [ -f "$HOME/.bashrc" ]; then PROFILE="$HOME/.bashrc"
              else PROFILE="$HOME/.bash_profile"; fi ;;
        fish) PROFILE="$HOME/.config/fish/config.fish" ;;
        *)    PROFILE="" ;;
    esac
    if [ -n "$PROFILE" ] && prompt_yn "Add $INSTALL_DIR to PATH in $PROFILE?"; then
        printf '\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$PROFILE"
        ok "Added to $PROFILE"
        warn "Run this now or restart your terminal: export PATH=\"$INSTALL_DIR:\$PATH\""
    else
        warn "Add manually to your shell profile: export PATH=\"$INSTALL_DIR:\$PATH\""
    fi
fi

# ── Step 4: Install Python SDK ────────────────────────────────────────────────
step 4 "Installing Python SDK (agentspan)..."

if [ "$PYTHON_OK" = true ]; then
    SDK_INSTALLED=false

    # 1. uv — fastest, handles all environments including Homebrew-managed Python
    if [ "$UV_AVAILABLE" = true ]; then
        info "Trying: uv pip install agentspan"
        if uv pip install agentspan 2>&1 | sed 's/^/       /'; then
            ok "Python SDK installed via uv"; SDK_INSTALLED=true
        else
            warn "uv install failed — trying pip"
        fi
    fi

    # 2. pip via the specific Python binary we detected
    #    Using $PYTHON_CMD -m pip ensures we install into the right Python
    #    (avoids the macOS trap where pip3 points to system Python 3.9)
    if [ "$SDK_INSTALLED" = false ]; then
        info "Trying: $PYTHON_CMD -m pip install agentspan"
        if "$PYTHON_CMD" -m pip install agentspan 2>&1 | sed 's/^/       /'; then
            ok "Python SDK installed"; SDK_INSTALLED=true
        fi
    fi

    # 3. --user flag — works on systems where the site-packages dir is not writable
    if [ "$SDK_INSTALLED" = false ]; then
        info "Trying: $PYTHON_CMD -m pip install --user agentspan"
        if "$PYTHON_CMD" -m pip install --user agentspan 2>&1 | sed 's/^/       /'; then
            ok "Python SDK installed (--user)"; SDK_INSTALLED=true
        fi
    fi

    # 4. --break-system-packages — Homebrew/Debian managed Python environments
    #    (Python 3.11+ on macOS/Debian refuse pip installs without this flag)
    if [ "$SDK_INSTALLED" = false ]; then
        warn "Standard pip install failed — this usually means Python is managed by Homebrew or the OS."
        if prompt_yn "Install with --break-system-packages? (safe for this package, Homebrew may warn)"; then
            if "$PYTHON_CMD" -m pip install --break-system-packages agentspan 2>&1 | sed 's/^/       /'; then
                ok "Python SDK installed (--break-system-packages)"; SDK_INSTALLED=true
            fi
        fi
    fi

    # 5. Last resort: create a venv at ~/.agentspan-sdk and install there
    if [ "$SDK_INSTALLED" = false ]; then
        VENV_DIR="$HOME/.agentspan-sdk"
        warn "Falling back to a virtual environment at $VENV_DIR"
        if "$PYTHON_CMD" -m venv "$VENV_DIR" 2>&1 | sed 's/^/       /' \
            && "$VENV_DIR/bin/pip" install agentspan 2>&1 | sed 's/^/       /'; then
            ok "Python SDK installed in $VENV_DIR"
            warn "To use the SDK, activate the venv first:"
            warn "  source $VENV_DIR/bin/activate"
            SDK_INSTALLED=true
        fi
    fi

    if [ "$SDK_INSTALLED" = false ]; then
        warn "Could not install the Python SDK automatically."
        warn "Install manually: pip install agentspan"
        warn "Or with uv:       uv pip install agentspan"
    fi
else
    warn "Skipping Python SDK install (Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ not found)."
fi

# ── Step 5: Verify with agentspan doctor ──────────────────────────────────────
step 5 "Running agentspan doctor..."

if command -v agentspan >/dev/null 2>&1; then
    printf "\n"
    agentspan doctor || warn "agentspan doctor reported issues — see above."
else
    warn "agentspan not in PATH yet — skipping doctor."
    warn "Run 'agentspan doctor' after restarting your terminal."
fi

# ── Step 6: Done ──────────────────────────────────────────────────────────────
step 6 "Installation complete!"

printf "\n${GREEN}${BOLD}AgentSpan is ready.${NC}\n"
printf "\nNext steps:\n"
printf "  1. Set your LLM API key:   export OPENAI_API_KEY=sk-...\n"
printf "  2. Start the server:       agentspan server start\n"
printf "  3. Open the UI:            http://localhost:6767\n"
printf "\nDocs: https://docs.agentspan.dev\n\n"
