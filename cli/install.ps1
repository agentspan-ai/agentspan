# AgentSpan installer for Windows (PowerShell)
# Installs the CLI binary, the Python SDK, and runs agentspan doctor.
#
# Usage (run as one-liner in PowerShell):
#   irm https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.ps1 | iex
#
# Or download and run locally:
#   powershell -ExecutionPolicy Bypass -File install.ps1

#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$S3_BUCKET      = 'https://agentspan.s3.us-east-2.amazonaws.com'
$BINARY_NAME    = 'agentspan.exe'
$PYTHON_MIN     = [Version]'3.10'
$REPO_RAW       = 'https://raw.githubusercontent.com/agentspan-ai/agentspan/main'

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step   { param([int]$n, [string]$msg) Write-Host "`n[$n/5] $msg" -ForegroundColor Cyan }
function Write-Ok     { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn   { param([string]$msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Fail   { param([string]$msg) Write-Host "`nError: $msg" -ForegroundColor Red; exit 1 }

function Get-IsAdmin {
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-ToPath {
    param([string]$Dir, [string]$Scope)
    $current = [Environment]::GetEnvironmentVariable('PATH', $Scope)
    if ($current -notlike "*$Dir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$Dir;$current", $Scope)
        Write-Ok "Added $Dir to $Scope PATH"
    }
    # Also update PATH in the current session
    if ($env:PATH -notlike "*$Dir*") {
        $env:PATH = "$Dir;$env:PATH"
    }
}

# ── Step 1: Detect platform ───────────────────────────────────────────────────
Write-Step 1 'Detecting platform...'

$arch = $env:PROCESSOR_ARCHITECTURE
switch ($arch) {
    'AMD64' { $goArch = 'amd64' }
    'ARM64' { $goArch = 'arm64' }
    'x86'   { Write-Fail '32-bit Windows is not supported. Please use a 64-bit system.' }
    default { Write-Fail "Unrecognised architecture: $arch" }
}
Write-Ok "Platform: windows/$goArch"

# ── Step 2: Check prerequisites ───────────────────────────────────────────────
Write-Step 2 'Checking prerequisites...'

# Python
$pythonCmd = $null
$pythonOk  = $false
foreach ($candidate in @('python', 'python3', 'py')) {
    try {
        $verLine = & $candidate --version 2>&1 | Select-Object -First 1
        if ($verLine -match '(\d+)\.(\d+)') {
            $ver = [Version]"$($Matches[1]).$($Matches[2])"
            if ($ver -ge $PYTHON_MIN) {
                $pythonCmd = $candidate
                $pythonOk  = $true
                Write-Ok "Python $ver found ($candidate)"
                break
            } else {
                Write-Warn "Found Python $ver ($candidate) — version $PYTHON_MIN+ required."
            }
        }
    } catch { <# not found, try next #> }
}
if (-not $pythonOk) {
    Write-Warn "Python $PYTHON_MIN+ not found. The Python SDK will not be installed."
    Write-Warn "Download Python at: https://www.python.org/downloads/"
}

# uv
$uvAvailable = $false
try {
    & uv --version 2>&1 | Out-Null
    $uvAvailable = $true
    Write-Ok "uv found — will use uv for Python SDK install"
} catch { <# uv not present #> }

# ── Step 3: Download CLI binary + verify checksum ─────────────────────────────
Write-Step 3 'Downloading CLI binary...'

$binaryFilename  = "agentspan_windows_${goArch}.exe"
$downloadUrl     = "$S3_BUCKET/cli/latest/$binaryFilename"
$checksumUrl     = "$S3_BUCKET/cli/latest/${binaryFilename}.sha256"

# Determine install directory based on admin status
$isAdmin = Get-IsAdmin
if ($isAdmin) {
    $defaultDir = "$env:ProgramFiles\agentspan"
    $pathScope  = 'Machine'
    Write-Ok 'Running as administrator — installing system-wide'
} else {
    $defaultDir = "$env:USERPROFILE\.agentspan\bin"
    $pathScope  = 'User'
    Write-Ok 'Installing to user profile (no admin rights needed)'
}

$installDir = if ($env:AGENTSPAN_INSTALL_DIR) { $env:AGENTSPAN_INSTALL_DIR } else { $defaultDir }

if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

$tmpDir      = [System.IO.Path]::GetTempPath() + [System.Guid]::NewGuid().ToString()
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$tmpBinary   = Join-Path $tmpDir $binaryFilename
$tmpChecksum = Join-Path $tmpDir "${binaryFilename}.sha256"

try {
    Write-Host "  Downloading from: $downloadUrl"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $wc = New-Object Net.WebClient
    $wc.Headers.Add('User-Agent', 'agentspan-installer/1.0')
    $wc.DownloadFile($downloadUrl, $tmpBinary)
    Write-Ok 'Binary downloaded'

    # Verify checksum
    $checksumVerified = $false
    try {
        $wc.DownloadFile($checksumUrl, $tmpChecksum)
        $expected = (Get-Content $tmpChecksum -Raw).Trim()
        if ($expected) {
            $actual = (Get-FileHash -Algorithm SHA256 -Path $tmpBinary).Hash.ToLower()
            $expected = $expected.ToLower() -replace '\s.*', ''   # strip filename if present
            if ($actual -eq $expected) {
                Write-Ok "Checksum verified (SHA256: $($actual.Substring(0,16))...)"
                $checksumVerified = $true
            } else {
                Write-Fail "Checksum mismatch!`n  Expected: $expected`n  Got:      $actual`nThe download may be corrupted. Please try again."
            }
        }
    } catch {
        Write-Warn 'Checksum file not available — skipping signature verification.'
    }

    # Install
    $destPath = Join-Path $installDir $BINARY_NAME
    Copy-Item -Path $tmpBinary -Destination $destPath -Force
    Write-Ok "Installed to $destPath"

    # Add to PATH
    Add-ToPath -Dir $installDir -Scope $pathScope

} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

# ── Step 4: Install Python SDK ────────────────────────────────────────────────
Write-Step 4 'Installing Python SDK (agentspan)...'

if ($pythonOk) {
    $sdkInstalled = $false

    if ($uvAvailable) {
        Write-Host '  Trying: uv pip install agentspan'
        try {
            & uv pip install agentspan
            Write-Ok 'Python SDK installed via uv'
            $sdkInstalled = $true
        } catch {
            Write-Warn 'uv install failed — falling back to pip'
        }
    }

    if (-not $sdkInstalled) {
        foreach ($pipVariant in @("$pythonCmd -m pip", 'pip', 'pip3')) {
            Write-Host "  Trying: $pipVariant install agentspan"
            try {
                $parts = $pipVariant -split ' '
                if ($parts.Count -eq 1) {
                    & $pipVariant install agentspan
                } else {
                    & $parts[0] $parts[1..($parts.Count-1)] install agentspan
                }
                Write-Ok "Python SDK installed via $pipVariant"
                $sdkInstalled = $true
                break
            } catch {
                Write-Warn "$pipVariant failed"
            }
        }
    }

    if (-not $sdkInstalled) {
        Write-Warn 'Could not install the Python SDK automatically.'
        Write-Warn 'Run manually: pip install agentspan'
    }
} else {
    Write-Warn "Skipping Python SDK install (Python $PYTHON_MIN+ required)."
}

# ── Step 5: Verify with agentspan doctor ──────────────────────────────────────
Write-Step 5 'Running agentspan doctor...'

$agentspanExe = Join-Path $installDir $BINARY_NAME
if (Test-Path $agentspanExe) {
    Write-Host ''
    try {
        & $agentspanExe doctor
    } catch {
        Write-Warn 'agentspan doctor reported issues — see above for details.'
    }
} else {
    Write-Warn "agentspan not found at $agentspanExe — skipping doctor."
    Write-Warn "Restart your terminal, then run: agentspan doctor"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'AgentSpan installation complete!' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Set your LLM API key:   $env:OPENAI_API_KEY = "sk-..."'
Write-Host '  2. Start the server:       agentspan server start'
Write-Host '  3. Open the UI:            http://localhost:6767'
Write-Host ''
Write-Host 'NOTE: If agentspan is not found, restart your terminal to pick up the updated PATH.'
Write-Host 'Docs: https://docs.agentspan.dev'
Write-Host ''
