param(
    [switch]$SkipChecks,
    [switch]$SkipInstaller,
    [switch]$ZipPortable
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "build_windows.ps1 нужно запускать на Windows. Каждая ОС собирается на своей ОС."
}

function Invoke-Poetry {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PoetryArgs)
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
        & poetry @PoetryArgs
        return
    }
    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        & $VenvPython -m poetry @PoetryArgs
        return
    }
    throw "Poetry не найден. Для dev-окружения запустите .\install.ps1 или установите Poetry."
}

function Find-Iscc {
    $Candidates = @(
        "ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($Candidate in $Candidates) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($Command) { return $Command.Source }
        if (Test-Path $Candidate) { return $Candidate }
    }
    return $null
}

$PythonVersion = Invoke-Poetry run python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
if (-not $PythonVersion.StartsWith("3.13.")) {
    throw "Требуется Python 3.13.x в Poetry-окружении, найден $PythonVersion"
}
Write-Host "Poetry окружение: Python $PythonVersion"

Write-Host "Установка зависимостей через Poetry"
Invoke-Poetry install --no-root

if (-not $SkipChecks) {
    Write-Host "Проверка pyproject"
    Invoke-Poetry check
    Write-Host "Ruff check"
    Invoke-Poetry run ruff check .
    Write-Host "Pytest"
    Invoke-Poetry run pytest
}

Write-Host "Очистка Windows build/dist/release"
Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "dist\AnimeEnhancement" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "release\windows" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "release\windows" | Out-Null

Write-Host "Сборка PyInstaller one-folder для Windows"
Invoke-Poetry run pyinstaller --noconfirm "packaging\pyinstaller\AnimeEnhancement.windows.spec"

$Exe = Join-Path $Root "dist\AnimeEnhancement\AnimeEnhancement.exe"
$CliExe = Join-Path $Root "dist\AnimeEnhancement\AnimeEnhancementCLI.exe"
if (-not (Test-Path $Exe)) { throw "Не найден GUI exe после сборки: $Exe" }
if (-not (Test-Path $CliExe)) { throw "Не найден CLI helper после сборки: $CliExe" }
Write-Host "Portable build готов: $Exe"

if ($ZipPortable) {
    $ZipPath = Join-Path $Root "release\windows\AnimeEnhancement-Windows.zip"
    if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Compress-Archive -Path "dist\AnimeEnhancement" -DestinationPath $ZipPath -Force
    Write-Host "Portable zip создан: $ZipPath"
}

if (-not $SkipInstaller) {
    $Iscc = Find-Iscc
    if ($Iscc) {
        Write-Host "Сборка Inno Setup installer"
        & $Iscc "packaging\windows\installer.iss"
        $Setup = Join-Path $Root "release\windows\AnimeEnhancementSetup.exe"
        if (-not (Test-Path $Setup)) { throw "Inno Setup не создал installer: $Setup" }
        Write-Host "Installer создан: $Setup"
    }
    else {
        Write-Host "Inno Setup ISCC.exe не найден. Установите Inno Setup 6 и повторите сборку installer." -ForegroundColor Yellow
        Write-Host "Portable build уже готов в dist\AnimeEnhancement." -ForegroundColor Yellow
    }
}

Write-Host "Windows release-сборка завершена. build\ является технической папкой, запускать exe из build не нужно."
