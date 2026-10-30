#Requires -Version 5.1
<#
.SYNOPSIS
    Instala o JARVIS: ambiente Python, dependências, frontend e .env local.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipEnv
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

Write-Host "JARVIS — instalação" -ForegroundColor Cyan
Write-Host "Diretório: $Root"

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Step "Criando ambiente virtual (.venv)"
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -eq 0 -and (Test-Path $VenvPython)) {
            $created = $true
        }
        else {
            Write-Host "py -3.12 indisponível; tentando python..." -ForegroundColor Yellow
        }
    }
    if (-not $created) {
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            throw "Python não encontrado. Instale o Python 3.11+ e marque 'Add to PATH'."
        }
        & python -m venv .venv
    }
    if (-not (Test-Path $VenvPython)) {
        throw "Falha ao criar o ambiente virtual."
    }
}

Write-Step "Atualizando pip e instalando dependências Python"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao instalar as dependências Python."
}

if (-not $SkipEnv) {
    Write-Step "Preparando .env"
    if (-not (Test-Path (Join-Path $Root ".env"))) {
        Copy-Item ".env.example" ".env"
        Write-Host "Criado .env a partir de .env.example. Preencha suas chaves de API." -ForegroundColor Yellow
    }
    else {
        Write-Host ".env já existe; preservado."
    }
}

if (-not $SkipFrontend) {
    Write-Step "Instalando e compilando o frontend"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm não encontrado. Instale o Node.js 20+ (https://nodejs.org)."
    }
    Push-Location (Join-Path $Root "frontend")
    try {
        if (Test-Path "package-lock.json") {
            npm ci
        }
        else {
            npm install
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Falha no npm install."
        }
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao compilar o frontend."
        }
    }
    finally {
        Pop-Location
    }
}

Write-Step "Verificando instalação"
& $VenvPython -c "import fastapi, uvicorn, webview; print('Dependências principais OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Verificação das dependências falhou."
}

Write-Host ""
Write-Host "Instalação concluída." -ForegroundColor Green
Write-Host "Execute: powershell -ExecutionPolicy Bypass -File scripts\run.ps1"
Write-Host "Ou:      .\.venv\Scripts\python.exe run_jarvis.py"
