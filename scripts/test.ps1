#Requires -Version 5.1
<#
.SYNOPSIS
    Executa lint, testes e build do frontend.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend
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
$Ruff = Join-Path $Root ".venv\Scripts\ruff.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Ambiente virtual não encontrado. Execute scripts\install.ps1 primeiro."
}

Write-Host "==> Ruff" -ForegroundColor Cyan
& $Ruff check backend tests desktop run_jarvis.py scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Lint falhou." }

Write-Host "==> Pytest" -ForegroundColor Cyan
& $VenvPython -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }

if (-not $SkipFrontend) {
    Write-Host "==> TypeScript + Vite" -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Build do frontend falhou." }
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Tudo certo." -ForegroundColor Green
