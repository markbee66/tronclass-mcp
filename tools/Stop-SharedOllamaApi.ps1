#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$stateRoot = Join-Path $env:LOCALAPPDATA 'TronClassOllamaAPI'
$pidPath = Join-Path $stateRoot 'processes.json'
if (Test-Path -LiteralPath $pidPath) {
    foreach ($saved in @(Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json)) {
        $live = Get-Process -Id $saved.Id -ErrorAction SilentlyContinue
        if ($live -and $live.StartTime.ToUniversalTime().Ticks -eq [long]$saved.StartTimeUtcTicks) {
            Stop-Process -Id $live.Id
        }
    }
    Remove-Item -LiteralPath $pidPath
}
Remove-Item -LiteralPath (Join-Path $stateRoot 'endpoint.txt') -ErrorAction SilentlyContinue
Write-Output 'Public API stopped. Local Ollama remains available.'
