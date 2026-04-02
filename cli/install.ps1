# AgentSpan installer for Windows (PowerShell)
# Installs Java 21+, the CLI binary, the Python SDK, and runs agentspan doctor.
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

$S3_BUCKET     = 'https://agentspan.s3.us-east-2.amazonaws.com'
$BINARY_NAME   = 'agentspan.exe'
$PYTHON_MIN    = [Version]'3.10'
$JAVA_MIN      = 21
$ADOPTIUM_URL  = "https://adoptium.net/temurin/releases/?version=$JAVA_MIN"
$ADOPTIUM_API  = "https://api.adoptium.net/v3/assets/latest/$JAVA_MIN/hotspot?architecture={0}&image_type=jdk&jvm_impl=hotspot&os=windows&page=0&page_size=1&project=jdk&vendor=eclipse"
$PYTHON_URL    = 'https://www.python.org/downloads/'
$TOTAL_STEPS   = 6

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step { param([int]$n, [string]$msg) Write-Host "`n[$n/$TOTAL_STEPS] $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Info { param([string]$msg) Write-Host "       $msg" }
function Write-Fail { param([string]$msg) Write-Host "`nError: $msg" -ForegroundColor Red; exit 1 }

function Get-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]::new($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-ToPath {
    param([string]$Dir, [string]$Scope)
    $current = [Environment]::GetEnvironmentVariable('PATH', $Scope)
    if ($current -notlike "*$Dir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$Dir;$current", $Scope)
        Write-Ok "Added $Dir to $Scope PATH"
    }
    if ($env:PATH -notlike "*$Dir*") { $env:PATH = "$Dir;$env:PATH" }
}

# Prompt helper — reads from the console even when stdin is piped
function Read-YesNo {
    param([string]$Question)
    Write-Host "  [?] $Question [y/N] " -ForegroundColor Yellow -NoNewline
    try   { $answer = $Host.UI.ReadLine() }
    catch { $answer = 'n' }
    return ($answer -match '^[Yy]')
}

function Invoke-Download {
    param([string]$Url, [string]$Dest)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $wc = New-Object Net.WebClient
    $wc.Headers.Add('User-Agent', 'agentspan-installer/1.0')
    $wc.DownloadFile($Url, $Dest)
}

# ── Step 1: Detect platform ───────────────────────────────────────────────────
Write-Step 1 'Detecting platform...'

$goArch = switch ($env:PROCESSOR_ARCHITECTURE) {
    'AMD64' { 'amd64' }
    'ARM64' { 'arm64' }
    'x86'   { Write-Fail '32-bit Windows is not supported.' }
    default { Write-Fail "Unrecognised architecture: $($env:PROCESSOR_ARCHITECTURE)" }
}
Write-Ok "Platform: windows/$goArch"

# ── Step 2: Check + install prerequisites ────────────────────────────────────
Write-Step 2 'Checking prerequisites...'

# ── Java ──────────────────────────────────────────────────────────────────────
$javaOk = $false
try {
    $javaVerLine = & java -version 2>&1 | Select-Object -First 1
    if ($javaVerLine -match '"(\d+)') {
        $javaMajor = [int]$Matches[1]
        if ($javaMajor -eq 1 -and $javaVerLine -match '"1\.(\d+)') { $javaMajor = [int]$Matches[1] }
        if ($javaMajor -ge $JAVA_MIN) {
            Write-Ok "Java $javaMajor found"
            $javaOk = $true
        } else {
            Write-Warn "Java $javaMajor found — Java $JAVA_MIN+ is required."
        }
    }
} catch { <# java not on PATH #> }

if (-not $javaOk) {
    Write-Warn "Java $JAVA_MIN+ is required to run the AgentSpan server."
    if (Read-YesNo "Install Java $JAVA_MIN (Eclipse Temurin) now?") {
        Write-Info "Querying Adoptium API for latest Temurin $JAVA_MIN JDK..."
        try {
            $apiUrl  = $ADOPTIUM_API -f $goArch
            $apiResp = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
            $msiUrl  = ($apiResp[0].binary.installer |
                        Where-Object { $_.extension -eq 'msi' } |
                        Select-Object -First 1).link
            if (-not $msiUrl) { $msiUrl = $apiResp[0].binary.package.link }

            $tmpMsi = [IO.Path]::GetTempFileName() + '.msi'
            Write-Info "Downloading from: $msiUrl"
            Invoke-Download -Url $msiUrl -Dest $tmpMsi

            Write-Info 'Running installer (this may take a minute)...'
            $proc = Start-Process msiexec.exe `
                -ArgumentList "/i `"$tmpMsi`" ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJarFileRunWith /quiet /norestart" `
                -Wait -PassThru
            Remove-Item $tmpMsi -Force -ErrorAction SilentlyContinue

            if ($proc.ExitCode -eq 0) {
                Write-Ok "Java $JAVA_MIN installed"
                # Refresh PATH so java is usable in this session
                $env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine') + ';' +
                            [Environment]::GetEnvironmentVariable('PATH','User')
            } else {
                Write-Warn "Installer exited with code $($proc.ExitCode)."
                Write-Warn "Download Java $JAVA_MIN manually: $ADOPTIUM_URL"
            }
        } catch {
            Write-Warn "Automatic Java install failed: $_"
            Write-Warn "Download Java $JAVA_MIN from: $ADOPTIUM_URL"
        }
    } else {
        Write-Warn "Skipping Java install. You will need Java $JAVA_MIN+ to run 'agentspan server start'."
        Write-Warn "  $ADOPTIUM_URL"
    }
}

# ── Python ────────────────────────────────────────────────────────────────────
$pythonCmd = $null
$pythonOk  = $false
foreach ($candidate in @('python', 'python3', 'py')) {
    try {
        $verLine = & $candidate --version 2>&1 | Select-Object -First 1
        if ($verLine -match '(\d+)\.(\d+)') {
            $ver = [Version]"$($Matches[1]).$($Matches[2])"
            if ($ver -ge $PYTHON_MIN) {
                $pythonCmd = $candidate; $pythonOk = $true
                Write-Ok "Python $ver found ($candidate)"
                break
            } else {
                Write-Warn "Found Python $ver ($candidate) — $PYTHON_MIN+ required."
            }
        }
    } catch { <# not on PATH #> }
}

if (-not $pythonOk) {
    Write-Warn "Python $PYTHON_MIN+ is required for the Python SDK."
    if (Read-YesNo "Install Python $PYTHON_MIN now?") {
        try {
            # Discover latest patch release via python.org JSON API
            Write-Info "Querying python.org for latest Python $($PYTHON_MIN.Major).$($PYTHON_MIN.Minor)..."
            $releases = Invoke-RestMethod -Uri 'https://www.python.org/api/v2/downloads/release/?is_published=true&pre_release=false' -UseBasicParsing
            $pyRelease = $releases |
                Where-Object { $_.name -like "Python $($PYTHON_MIN.Major).$($PYTHON_MIN.Minor)*" } |
                Sort-Object name -Descending |
                Select-Object -First 1
            $pyVer    = $pyRelease.name -replace 'Python ', ''
            $arch64   = if ($goArch -eq 'amd64') { 'amd64' } else { 'arm64' }
            $pyExeUrl = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-$arch64.exe"

            $tmpPy = [IO.Path]::GetTempFileName() + '.exe'
            Write-Info "Downloading from: $pyExeUrl"
            Invoke-Download -Url $pyExeUrl -Dest $tmpPy

            Write-Info 'Running Python installer (this may take a minute)...'
            $proc = Start-Process $tmpPy `
                -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' `
                -Wait -PassThru
            Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue

            if ($proc.ExitCode -eq 0) {
                Write-Ok "Python $pyVer installed"
                $env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine') + ';' +
                            [Environment]::GetEnvironmentVariable('PATH','User')
                # Re-detect
                foreach ($candidate in @('python', 'python3', 'py')) {
                    try {
                        $vl = & $candidate --version 2>&1 | Select-Object -First 1
                        if ($vl -match '(\d+)\.(\d+)' -and
                            [Version]"$($Matches[1]).$($Matches[2])" -ge $PYTHON_MIN) {
                            $pythonCmd = $candidate; $pythonOk = $true; break
                        }
                    } catch { }
                }
            } else {
                Write-Warn "Installer exited with code $($proc.ExitCode)."
                Write-Warn "Download Python from: $PYTHON_URL"
            }
        } catch {
            Write-Warn "Automatic Python install failed: $_"
            Write-Warn "Download Python from: $PYTHON_URL"
        }
    } else {
        Write-Warn "Skipping Python install. The Python SDK will not be installed."
        Write-Warn "  $PYTHON_URL"
    }
}

# ── uv ────────────────────────────────────────────────────────────────────────
$uvAvailable = $false
try { & uv --version 2>&1 | Out-Null; $uvAvailable = $true; Write-Ok 'uv found' } catch { }

# ── Step 3: Download CLI binary + verify checksum ─────────────────────────────
Write-Step 3 'Downloading CLI binary...'

$binaryFilename = "agentspan_windows_${goArch}.exe"
$downloadUrl    = "$S3_BUCKET/cli/latest/$binaryFilename"
$checksumUrl    = "$S3_BUCKET/cli/latest/${binaryFilename}.sha256"

$isAdmin = Get-IsAdmin
if ($isAdmin) {
    $defaultDir = "$env:ProgramFiles\agentspan"; $pathScope = 'Machine'
    Write-Ok 'Running as administrator — installing system-wide'
} else {
    $defaultDir = "$env:USERPROFILE\.agentspan\bin"; $pathScope = 'User'
    Write-Ok 'Installing to user profile (no admin rights needed)'
}
$installDir = if ($env:AGENTSPAN_INSTALL_DIR) { $env:AGENTSPAN_INSTALL_DIR } else { $defaultDir }
if (-not (Test-Path $installDir)) { New-Item -ItemType Directory -Path $installDir -Force | Out-Null }

$tmpDir    = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid())
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmpBin    = Join-Path $tmpDir $binaryFilename
$tmpCksum  = Join-Path $tmpDir "${binaryFilename}.sha256"

try {
    Write-Info "From: $downloadUrl"
    Invoke-Download -Url $downloadUrl -Dest $tmpBin
    Write-Ok 'Binary downloaded'

    # Checksum
    try {
        Invoke-Download -Url $checksumUrl -Dest $tmpCksum
        $expected = (Get-Content $tmpCksum -Raw).Trim().ToLower() -replace '\s.*', ''
        $actual   = (Get-FileHash -Algorithm SHA256 -Path $tmpBin).Hash.ToLower()
        if ($actual -eq $expected) {
            Write-Ok "Checksum verified (SHA256: $($actual.Substring(0,16))...)"
        } else {
            Write-Fail "Checksum mismatch!`n  Expected: $expected`n  Got:      $actual"
        }
    } catch {
        Write-Warn 'Checksum file not available — skipping signature verification.'
    }

    Copy-Item -Path $tmpBin -Destination (Join-Path $installDir $BINARY_NAME) -Force
    Write-Ok "Installed to $installDir\$BINARY_NAME"
    Add-ToPath -Dir $installDir -Scope $pathScope

} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

# ── Step 4: Install Python SDK ────────────────────────────────────────────────
Write-Step 4 'Installing Python SDK (agentspan)...'

if ($pythonOk) {
    $sdkInstalled = $false

    if ($uvAvailable) {
        Write-Info 'Trying: uv pip install agentspan'
        try { & uv pip install agentspan; Write-Ok 'Python SDK installed via uv'; $sdkInstalled = $true }
        catch { Write-Warn 'uv install failed — falling back to pip' }
    }

    if (-not $sdkInstalled) {
        foreach ($pipVariant in @("$pythonCmd -m pip", 'pip', 'pip3')) {
            Write-Info "Trying: $pipVariant install agentspan"
            try {
                $parts = $pipVariant -split ' '
                if ($parts.Count -eq 1) { & $pipVariant install agentspan }
                else { & $parts[0] ($parts[1..($parts.Count-1)]) install agentspan }
                Write-Ok "Python SDK installed via $pipVariant"; $sdkInstalled = $true; break
            } catch { Write-Warn "$pipVariant failed" }
        }
    }
    if (-not $sdkInstalled) {
        Write-Warn 'Could not install SDK automatically. Run: pip install agentspan'
    }
} else {
    Write-Warn "Skipping Python SDK install (Python $PYTHON_MIN+ required)."
}

# ── Step 5: Verify with agentspan doctor ──────────────────────────────────────
Write-Step 5 'Running agentspan doctor...'

$agentspanExe = Join-Path $installDir $BINARY_NAME
if (Test-Path $agentspanExe) {
    Write-Host ''
    try { & $agentspanExe doctor }
    catch { Write-Warn 'agentspan doctor reported issues — see above.' }
} else {
    Write-Warn "agentspan not found at $agentspanExe — skipping doctor."
    Write-Warn 'Restart your terminal then run: agentspan doctor'
}

# ── Step 6: Done ──────────────────────────────────────────────────────────────
Write-Step 6 'Installation complete!'

Write-Host ''
Write-Host 'AgentSpan is ready.' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Set your LLM API key:   $env:OPENAI_API_KEY = "sk-..."'
Write-Host '  2. Start the server:       agentspan server start'
Write-Host '  3. Open the UI:            http://localhost:6767'
Write-Host ''
Write-Host 'NOTE: If agentspan is not found, restart your terminal to pick up the updated PATH.'
Write-Host 'Docs: https://docs.agentspan.dev'
Write-Host ''
