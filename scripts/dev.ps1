#Requires -Version 5.1
<#
.SYNOPSIS
    Ambiente de desenvolvimento: backend com reload + frontend Vite.
#>
[CmdletBinding()]
param()

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
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm não encontrado. Instale o Node.js 20+."
}

Write-Host "Backend: http://127.0.0.1:8765 (reload)" -ForegroundColor Cyan
Write-Host "Frontend: http://127.0.0.1:5173 (Vite)" -ForegroundColor Cyan
Write-Host "Pressione Ctrl+C para encerrar ambos." -ForegroundColor DarkGray

$backend = Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--reload", "--host", "127.0.0.1", "--port", "8765") `
    -PassThru -NoNewWindow

try {
    Push-Location (Join-Path $Root "frontend")
    try {
        npm run dev
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($backend -and -not $backend.HasExited) {
        Write-Host "Encerrando backend..." -ForegroundColor DarkGray
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
