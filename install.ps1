param(
    [switch]$NoGui
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-Python313 {
    $knownPython313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    $candidates = @(
        @("py", "-3.13"),
        @("py", "-3"),
        @("python3.13"),
        @($knownPython313),
        @("python")
    )

    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        if (-not (Get-Command $command -ErrorAction SilentlyContinue) -and -not (Test-Path $command)) {
            continue
        }

        $baseArgs = @()
        if ($candidate.Count -gt 1) {
            $baseArgs = $candidate[1..($candidate.Count - 1)]
        }

        try {
            $probe = & $command @baseArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{sys.executable}')" 2>$null
            if (-not $probe) {
                continue
            }
            $parts = $probe.Trim().Split('|')
            $version = [version]$parts[0]
            $executable = $parts[1]
            if ($version.Major -eq 3 -and $version.Minor -eq 13) {
                return [PSCustomObject]@{
                    Command = $command
                    Args = $baseArgs
                    Version = $parts[0]
                    Executable = $executable
                }
            }
        }
        catch {
            continue
        }
    }

    return $null
}

Write-Host "Установка anime_enhancement" -ForegroundColor Cyan

$python = Find-Python313
if (-not $python) {
    throw "Python 3.13 не найден. Установите Python 3.13.2 или добавьте Python Launcher 'py' в PATH."
}

Write-Host "Используется Python $($python.Version): $($python.Executable)"

if (Test-Path "venv") {
    throw "Найдена старая папка venv. Удалите ее или переименуйте: $Root\venv"
}

if (-not (Test-Path ".venv")) {
    Write-Host "Создание единого виртуального окружения .venv на Python $($python.Version)"
    & $python.Command @($python.Args) -m venv .venv
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
if (-not $venvVersion.StartsWith("3.13")) {
    throw ".venv создан не на Python 3.13, найден $venvVersion. Удалите .venv и повторите install.ps1."
}

Write-Host "Окружение .venv использует Python $venvVersion"
& $venvPython -m pip install --upgrade pip poetry

$env:POETRY_VIRTUALENVS_CREATE = "false"
& $venvPython -m poetry install --no-root

& $venvPython scripts\install_ffmpeg.py

if (-not $NoGui) {
    Write-Host "Сборка GUI exe"
    & (Join-Path $Root "packaging\scripts\build_windows.ps1") -SkipChecks -SkipInstaller
}

Write-Host "Проверка окружения"
& $venvPython main.py --check-environment

Write-Host "Установка завершена."
Write-Host "Запуск GUI: .\dist\AnimeEnhancement\AnimeEnhancement.exe"
Write-Host "Запуск CLI: .venv\Scripts\python.exe main.py --config profiles\profile.json"
