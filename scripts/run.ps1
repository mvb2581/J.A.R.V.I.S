#Requires -Version 5.1
<#
.SYNOPSIS
    Inicia o JARVIS com a janela desktop (ou no navegador com -Browser).
#>
[CmdletBinding()]
param(
    [switch]$Browser,
    [switch]$ServerOnly,
    [switch]$DebugWindow,
    [string]$HostAddress,
    [int]$Port
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Ambiente virtual não encontrado. Execute scripts\install.ps1 primeiro."
}

if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Write-Host "Frontend não compilado. Execute: cd frontend; npm install; npm run build" -ForegroundColor Yellow
}

$Arguments = @("run_jarvis.py")
if ($Browser) { $Arguments += "--browser" }
if ($ServerOnly) { $Arguments += "--server-only" }
if ($DebugWindow) { $Arguments += "--debug" }
if ($HostAddress) { $Arguments += @("--host", $HostAddress) }
if ($Port -gt 0) { $Arguments += @("--port", "$Port") }

& $VenvPython @Arguments
exit $LASTEXITCODE
