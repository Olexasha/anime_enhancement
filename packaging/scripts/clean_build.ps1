param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

foreach ($Path in @("build", "dist", "release")) {
    $Resolved = Join-Path $Root $Path
    if (Test-Path $Resolved) {
        Remove-Item -LiteralPath $Resolved -Recurse -Force
        Write-Host "Удалено: $Resolved"
    }
}
Write-Host "Очистка build/dist/release завершена."
