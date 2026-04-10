# AgentSpan installer for Windows (PowerShell)
# Installs Java 21+ and the CLI binary, then runs agentspan doctor.
# SDK install is language-specific: pip install agentspan / npm install @agentspan-ai/sdk
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

$S3_BUCKET    = 'https://agentspan.s3.us-east-2.amazonaws.com'
$BINARY_NAME  = 'agentspan.exe'
$JAVA_MIN     = 21
$ADOPTIUM_URL = "https://adoptium.net/temurin/releases/?version=$JAVA_MIN"
$ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/$JAVA_MIN/hotspot?architecture={0}&image_type=jdk&jvm_impl=hotspot&os=windows&page=0&page_size=1&project=jdk&vendor=eclipse"
$TOTAL_STEPS  = 4

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

# ── Step 2: Check + install Java 21+ ─────────────────────────────────────────
Write-Step 2 "Checking Java $JAVA_MIN+..."

$javaOk = $false

# Check JAVA_HOME first — covers users whose version manager (sdkman-for-windows,
# jabba, etc.) sets JAVA_HOME but doesn't update PATH in this session.
$javaCandidates = @()
if ($env:JAVA_HOME) { $javaCandidates += Join-Path $env:JAVA_HOME 'bin\java.exe' }
$javaCandidates += 'java'

foreach ($candidate in $javaCandidates) {
    try {
        $javaVerLine = & $candidate -version 2>&1 | Select-Object -First 1
        if ($javaVerLine -match '"(\d+)') {
            $javaMajor = [int]$Matches[1]
            if ($javaMajor -eq 1 -and $javaVerLine -match '"1\.(\d+)') { $javaMajor = [int]$Matches[1] }
            if ($javaMajor -ge $JAVA_MIN) {
                Write-Ok "Java $javaMajor found"
                $javaOk = $true
                break
            } else {
                Write-Warn "Java $javaMajor found — Java $JAVA_MIN+ is required."
            }
        }
    } catch { <# not found, try next #> }
}

if (-not $javaOk) {
    Write-Warn "Java $JAVA_MIN+ not found. It is required to run the AgentSpan server."
    if (Read-YesNo "Install Java $JAVA_MIN (Eclipse Temurin) now?") {
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

# ── Step 3: Download CLI binary + verify checksum ─────────────────────────────
Write-Step 3 'Downloading CLI binary...'

$binaryFilename = "agentspan_windows_${goArch}.exe"
$downloadUrl    = "$S3_BUCKET/cli/latest/$binaryFilename"
$checksumUrl    = "$S3_BUCKET/cli/latest/${binaryFilename}.sha256"
$versionUrl     = "$S3_BUCKET/cli/latest/version.txt"

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

$tmpDir   = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid())
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmpBin   = Join-Path $tmpDir $binaryFilename
$tmpCksum = Join-Path $tmpDir "${binaryFilename}.sha256"

try {
    # Skip download if already on latest version
    $cliSkip = $false
    $agentspanExe = Join-Path $installDir $BINARY_NAME
    if (Test-Path $agentspanExe) {
        try {
            $currentVer = (& $agentspanExe version 2>&1) -split ' ' | Select-Object -Index 1
            $tmpVer = Join-Path $tmpDir 'version.txt'
            Invoke-Download -Url $versionUrl -Dest $tmpVer
            $latestVer = (Get-Content $tmpVer -Raw).Trim()
            if ($currentVer -eq $latestVer) {
                Write-Ok "CLI already up to date ($currentVer) — skipping download"
                $cliSkip = $true
            } else {
                Write-Info "Upgrading CLI: $currentVer -> $latestVer"
            }
        } catch { <# version check failed, proceed with download #> }
    }

    if (-not $cliSkip) {
        Write-Info "From: $downloadUrl"
        Invoke-Download -Url $downloadUrl -Dest $tmpBin
        Write-Ok 'Binary downloaded'

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
    }
} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

# ── Step 4: Verify with agentspan doctor ──────────────────────────────────────
Write-Step 4 'Running agentspan doctor...'

$agentspanExe = Join-Path $installDir $BINARY_NAME
if (Test-Path $agentspanExe) {
    Write-Host ''
    try { & $agentspanExe doctor }
    catch { Write-Warn 'agentspan doctor reported issues — see above.' }
} else {
    Write-Warn "agentspan not found at $agentspanExe — skipping doctor."
    Write-Warn 'Restart your terminal then run: agentspan doctor'
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'AgentSpan CLI is ready.' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Install your SDK:'
Write-Host '       Python:     pip install agentspan'
Write-Host '       TypeScript: npm install @agentspan-ai/sdk'
Write-Host '       Java:       https://docs.agentspan.dev/sdk/java'
Write-Host '  2. Set your LLM API key:   $env:OPENAI_API_KEY = "sk-..."'
Write-Host '  3. Start the server:       agentspan server start'
Write-Host '  4. Open the UI:            http://localhost:6767'
Write-Host ''
Write-Host 'NOTE: If agentspan is not found, restart your terminal to pick up the updated PATH.'
Write-Host 'Docs: https://docs.agentspan.dev'
Write-Host ''
