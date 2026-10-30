#Requires -Version 5.1
<#
.SYNOPSIS
    Compila o frontend e gera o executável Windows com PyInstaller.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipTests
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

if (-not $SkipTests) {
    Write-Host "==> Lint e testes" -ForegroundColor Cyan
    & (Join-Path $Root ".venv\Scripts\ruff.exe") check backend tests desktop run_jarvis.py scripts\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Lint falhou." }
    & $VenvPython -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }
}

if (-not $SkipFrontend) {
    Write-Host "==> Compilando frontend" -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    try {
        if (Test-Path "package-lock.json") { npm ci } else { npm install }
        if ($LASTEXITCODE -ne 0) { throw "npm install falhou." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Build do frontend falhou." }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    throw "frontend\dist não encontrado. Compile o frontend antes de empacotar."
}

Write-Host "==> Gerando ícone" -ForegroundColor Cyan
& $VenvPython scripts\make_icon.py

Write-Host "==> Empacotando com PyInstaller" -ForegroundColor Cyan
& $VenvPython -m PyInstaller --noconfirm --clean jarvis.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

$exe = Join-Path $Root "dist\JARVIS\JARVIS.exe"
if (-not (Test-Path $exe)) {
    throw "Executável não encontrado em $exe"
}

Write-Host ""
Write-Host "Build concluído: $exe" -ForegroundColor Green
Write-Host "Os dados do usuário ficam em %LOCALAPPDATA%\JARVIS." -ForegroundColor DarkGray
