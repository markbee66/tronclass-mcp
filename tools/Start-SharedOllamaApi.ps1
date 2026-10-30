#Requires -Version 7.0
param(
    [int]$RequestsPerMinute = 30,
    [switch]$RotateKey,
    [switch]$LocalOnly,
    [string]$CloudflaredPath
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$stateRoot = Join-Path $env:LOCALAPPDATA 'TronClassOllamaAPI'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if ($RequestsPerMinute -lt 1) { throw 'RequestsPerMinute must be positive.' }
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install requirements-gateway.txt first.' }
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
# Keep keys, endpoint and logs outside Git and readable only by this Windows user and SYSTEM.
$acl = [Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
foreach ($sid in @($currentSid, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
$existingAcl = Get-Acl -LiteralPath $stateRoot
$expectedSids = @($currentSid.Value, 'S-1-5-18')
$actualSids = @($existingAcl.Access | ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value })
$aclReady = $existingAcl.AreAccessRulesProtected -and $actualSids.Count -eq 2
foreach ($sidValue in $expectedSids) { if ($sidValue -notin $actualSids) { $aclReady = $false } }
foreach ($rule in $existingAcl.Access) {
    if ($rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl') { $aclReady = $false }
}
if (-not $aclReady) { Set-Acl -LiteralPath $stateRoot -AclObject $acl }
$pidPath = Join-Path $stateRoot 'processes.json'
if (Test-Path -LiteralPath $pidPath) {
    foreach ($saved in @(Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json)) {
        $live = Get-Process -Id $saved.Id -ErrorAction SilentlyContinue
        if ($live -and $live.StartTime.ToUniversalTime().Ticks -eq [long]$saved.StartTimeUtcTicks) {
            throw 'API is running. Stop it before rotating a key or restarting.'
        }
    }
}
$listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
$ollamaListeners = @($listeners | Where-Object Port -eq 11434)
if (-not $ollamaListeners.Count -or @($ollamaListeners | Where-Object { -not [Net.IPAddress]::IsLoopback($_.Address) }).Count) {
    throw 'Ollama must listen exclusively on loopback port 11434.'
}
if (@($listeners | Where-Object Port -eq 11435).Count) { throw 'Gateway port 11435 is already occupied.' }
Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 5 | Out-Null
$keyPath = Join-Path $stateRoot 'api-key.txt'
if ($RotateKey -or -not (Test-Path -LiteralPath $keyPath)) {
    $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    $newKey = 'sk-' + [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    [IO.File]::WriteAllText($keyPath, $newKey)
}
$apiKey = [IO.File]::ReadAllText($keyPath).Trim()
$env:TRONCLASS_API_KEY_FILE = $keyPath
$env:TRONCLASS_API_RPM = $RequestsPerMinute.ToString()
$children = @()
$endpointPath = Join-Path $stateRoot 'endpoint.txt'
Remove-Item -LiteralPath $endpointPath -ErrorAction SilentlyContinue
try {
    $gatewayArgs = @('-m','uvicorn','tronclass.gateway:create_gateway','--factory',
        '--host','127.0.0.1','--port','11435','--workers','1','--no-access-log',
        '--no-proxy-headers','--no-server-header')
    $gateway = Start-Process -FilePath $pythonExe -ArgumentList $gatewayArgs -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateRoot 'gateway.out.log') -RedirectStandardError (Join-Path $stateRoot 'gateway.err.log') -PassThru
    $children += $gateway
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            Invoke-RestMethod 'http://127.0.0.1:11435/v1/models' -Headers @{Authorization='Bearer ' + $apiKey} -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Gateway not ready; see private gateway.err.log.' }
    try {
        Invoke-RestMethod 'http://127.0.0.1:11435/v1/models' -TimeoutSec 2 | Out-Null
        throw 'Gateway accepted an unauthenticated request.'
    } catch {
        if ([int]$_.Exception.Response.StatusCode -ne 401) { throw }
    }
    $bound = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object Port -eq 11435
    if (@($bound | Where-Object { -not [Net.IPAddress]::IsLoopback($_.Address) }).Count) {
        throw 'Gateway is not restricted to loopback.'
    }
    if (-not $LocalOnly) {
        if (-not $CloudflaredPath) {
            $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
            $CloudflaredPath = (Get-Command cloudflared.exe -ErrorAction Stop).Source
        }
        $tunnel = Start-Process -FilePath $CloudflaredPath -ArgumentList @('tunnel','--no-autoupdate','--protocol','http2','--url','http://127.0.0.1:11435') -WorkingDirectory $stateRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateRoot 'tunnel.out.log') -RedirectStandardError (Join-Path $stateRoot 'tunnel.err.log') -PassThru
        $children += $tunnel
        $found = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            $tunnelLog = Get-Content -LiteralPath (Join-Path $stateRoot 'tunnel.err.log') -Raw -ErrorAction SilentlyContinue
            if ([string]::IsNullOrEmpty($tunnelLog)) { $tunnelLog = ' ' }
            $match = [regex]::Match($tunnelLog, 'https://[a-z0-9-]+\.trycloudflare\.com')
            if ($match.Success) {
                [IO.File]::WriteAllText($endpointPath, $match.Value + '/v1')
                $found = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $found) { throw 'Tunnel URL not ready; see private tunnel.err.log.' }
    }
    $children | ForEach-Object { @{Id=$_.Id; StartTimeUtcTicks=$_.StartTime.ToUniversalTime().Ticks} } |
        ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding utf8
    Write-Output ('API started. Shared request rate: ' + $RequestsPerMinute + '/minute.')
    Write-Output ('Connection details are in the private folder: ' + $stateRoot)
    if ($LocalOnly) { Write-Output 'Local-only verification mode; no tunnel was created.' }
} catch {
    foreach ($child in $children) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $pidPath,$endpointPath -ErrorAction SilentlyContinue
    throw
} finally {
    Remove-Item Env:TRONCLASS_API_KEY_FILE,Env:TRONCLASS_API_RPM -ErrorAction SilentlyContinue
    Remove-Variable apiKey,newKey -ErrorAction SilentlyContinue
}
