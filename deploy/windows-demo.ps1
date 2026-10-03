# Run the Swangz AI Gateway on a Windows laptop and put it online through a Cloudflare quick tunnel.
# The Windows counterpart of laptop-demo.sh.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows-demo.ps1            start it all, print the tunnel link
#   powershell -ExecutionPolicy Bypass -File deploy\windows-demo.ps1 -Restart   restart only the gateway (new code,
#                                                                                new .env) — the tunnel link stays
#   powershell -ExecutionPolicy Bypass -File deploy\windows-demo.ps1 -Stop      stop it all
#
# Settings: $HOME\swangz-gateway-demo\.env (copy .env.example). If it sets DEMO_PROVIDER_KEY, the stand-in
# model (tests\fake_upstream.py --demo on port 18902) is started too, so nothing real is spent.
# Each start of the tunnel gives a NEW link: put it in Netlify's SWANGZ_GATEWAY and redeploy.
# Everything runs as hidden background programs, so closing this window doesn't stop them.

param([switch]$Restart, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Dir = Join-Path $env:USERPROFILE 'swangz-gateway-demo'
$EnvFile = Join-Path $Dir '.env'
$Logs = Join-Path $Dir 'logs'
$PidFile = Join-Path $Dir 'pids.txt'

function Find-Python {
    foreach ($c in @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
                     Sort-Object FullName -Descending | ForEach-Object FullName) + @('py', 'python')) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike '*WindowsApps*') { return $cmd.Source }  # not the Store placeholder
    }
    throw 'Python 3.10+ is not installed: winget install Python.Python.3.13'
}

function Find-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $env:USERPROFILE '.local\bin\cloudflared.exe'
    if (Test-Path $local) { return $local }
    throw "cloudflared is not installed: download cloudflared-windows-amd64.exe from Cloudflare's GitHub releases to $local"
}

# what we started, found again by command line (process ids get reused)
function Get-Ours {
    if (-not (Test-Path $PidFile)) { return @() }
    $ids = Get-Content $PidFile | ForEach-Object { [int](($_ -split ' ')[0]) }
    Get-CimInstance Win32_Process | Where-Object { $ids -contains $_.ProcessId } | ForEach-Object {
        $role = if ($_.CommandLine -match '-m gateway serve') { 'gateway' }
                elseif ($_.CommandLine -match 'fake_upstream') { 'model' }
                elseif ($_.Name -eq 'cloudflared.exe') { 'tunnel' } else { $null }
        if ($role) { [pscustomobject]@{ Id = $_.ProcessId; Role = $role } }
    }
}

function Save-Ours($procs) { $procs | ForEach-Object { "$($_.Id) $($_.Role)" } | Set-Content $PidFile }

function Start-Gateway($py) {
    $env:GATEWAY_ENV_FILE = $EnvFile
    $p = Start-Process $py -ArgumentList '-m', 'gateway', 'serve' -WorkingDirectory $Repo -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$Logs\gateway.out.log" -RedirectStandardError "$Logs\gateway.log"
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try { if ((Invoke-WebRequest 'http://127.0.0.1:8787/healthz' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
            return [pscustomobject]@{ Id = $p.Id; Role = 'gateway' } } } catch {}
    }
    throw "The gateway did not start - see $Logs\gateway.log"
}

if (-not (Test-Path $EnvFile)) { throw "No settings yet: copy .env.example to $EnvFile and fill it in." }
New-Item -ItemType Directory -Force $Logs | Out-Null
$ours = @(Get-Ours)

if ($Stop) {
    $ours | ForEach-Object { Stop-Process -Id $_.Id -Force -Confirm:$false; Write-Host "stopped $($_.Role)" }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    return
}

$py = Find-Python
if ($Restart) {
    $ours | Where-Object Role -eq 'gateway' | ForEach-Object { Stop-Process -Id $_.Id -Force -Confirm:$false }
    Start-Sleep -Seconds 1
    $ours = @($ours | Where-Object Role -ne 'gateway') + @(Start-Gateway $py)
    Save-Ours $ours
    Write-Host 'Gateway restarted on http://localhost:8787 - the tunnel link is unchanged.'
    return
}

$ours | ForEach-Object { Stop-Process -Id $_.Id -Force -Confirm:$false }
$ours = @()
if (Select-String -Path $EnvFile -Pattern '^DEMO_PROVIDER_KEY=.+' -Quiet) {
    $m = Start-Process $py -ArgumentList 'tests\fake_upstream.py', '18902', '--demo' -WorkingDirectory $Repo -WindowStyle Hidden `
        -PassThru -RedirectStandardOutput "$Logs\demo-model.out.log" -RedirectStandardError "$Logs\demo-model.log"
    $ours += [pscustomobject]@{ Id = $m.Id; Role = 'model' }
}
$ours += Start-Gateway $py
Remove-Item "$Logs\tunnel.log" -ErrorAction SilentlyContinue
$t = Start-Process (Find-Cloudflared) -ArgumentList 'tunnel', '--no-autoupdate', '--url', 'http://localhost:8787' -WindowStyle Hidden `
    -PassThru -RedirectStandardOutput "$Logs\tunnel.out.log" -RedirectStandardError "$Logs\tunnel.log"
$ours += [pscustomobject]@{ Id = $t.Id; Role = 'tunnel' }
Save-Ours $ours
Write-Host 'Gateway running on http://localhost:8787. Opening the tunnel...'

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    $hit = Select-String -Path "$Logs\tunnel.log" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $url = $hit.Matches[0].Value }
}
if (-not $url) { throw "No tunnel link yet - see $Logs\tunnel.log" }
$url | Set-Content (Join-Path $Dir 'tunnel-url.txt')
Write-Host ''
Write-Host "  Tunnel link:   $url"
Write-Host ''
Write-Host '  Netlify -> swangz-ai -> Environment variables -> SWANGZ_GATEWAY = that link, then Deploys -> Trigger deploy.'
