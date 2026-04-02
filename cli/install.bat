@echo off
:: AgentSpan installer for Windows (CMD / double-click)
:: Launches the PowerShell installer script.
::
:: Usage: double-click this file, or paste into CMD:
::   curl -fsSL https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.bat -o install.bat && install.bat

echo.
echo  AgentSpan Installer
echo  -------------------
echo  This will install the AgentSpan CLI and Python SDK.
echo.

:: Check if PowerShell is available
where powershell >nul 2>&1
if %errorlevel% neq 0 (
    echo  Error: PowerShell is required but was not found.
    echo  Please install PowerShell: https://aka.ms/install-powershell
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "& { irm 'https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.ps1' | iex }"

if %errorlevel% neq 0 (
    echo.
    echo  Installation failed. See errors above.
    pause
    exit /b 1
)

pause
