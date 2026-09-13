#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [switch]$SkipOnce,  # skip the immediate backup run after starting
    [switch]$NoClean,   # keep existing test archive / ES data
    [switch]$Down       # tear the stack down instead of starting it
)

# --- Configuration ---
$TestDir        = $PSScriptRoot                              # imapbox/test
$ComposeRoot    = Split-Path -Parent $PSScriptRoot           # imapbox/ (compose project root)
$StackFile      = Join-Path $ComposeRoot "docker-compose-stack.yaml"
$CacheDir       = Join-Path $TestDir "cache"                 # generated data (gitignored)
$TestCompose    = Join-Path $CacheDir "docker-compose.test.yaml"
$ConfigDir      = Join-Path $CacheDir "config"
$ConfigFile     = Join-Path $ConfigDir "config.cfg"
$OnceConfigFile = Join-Path $ConfigDir "config-once.cfg"
$ArchiveVol     = Join-Path $CacheDir "archive"
$EsDataVol      = Join-Path $CacheDir "esdata"

$ImapHost       = "host.docker.internal"   # resolves to the host inside the compose network (extra_hosts in the stack)
$ImapPort       = 3143
$GreenMailHost  = "127.0.0.1"              # GreenMail (mock-server.ps1) port probe
$GreenMailPort  = 3143
$GreenMailUiPort = 8089
$GreenMailUrl   = "http://${GreenMailHost}:${GreenMailUiPort}"
$Accounts       = @("alice@example.com", "bob@example.com")

$EsUrl          = "http://localhost:9200"
$CalacaUrl      = "http://localhost:8088"

function Test-Port([string]$HostName, [int]$Port, [int]$TimeoutMs = 1000) {
    $TcpClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connection = $TcpClient.ConnectAsync($HostName, $Port)
        return $Connection.Wait($TimeoutMs) -and $TcpClient.Connected
    }
    catch { return $false }
    finally { $TcpClient.Dispose() }
}

function Wait-Port([string]$HostName, [int]$Port, [int]$Attempts, [string]$What) {
    Write-Host "⏳ Waiting for $What ($HostName`:$Port) ..." -ForegroundColor Cyan
    for ($i = 1; $i -le $Attempts; $i++) {
        if (Test-Port $HostName $Port) { return $true }
        Write-Host "." -NoNewline -ForegroundColor Gray
        Start-Sleep -Seconds 1
    }
    Write-Host ""
    return $false
}

function Wait-EsApi([int]$Attempts = 45) {
    Write-Host "⏳ Waiting for Elasticsearch REST API ..." -ForegroundColor Cyan
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            $Health = Invoke-RestMethod -Uri "$EsUrl/_cluster/health" -TimeoutSec 3
            if ($Health.status -in @("green", "yellow")) { return $true }
        }
        catch { }
        Write-Host "." -NoNewline -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
    Write-Host ""
    return $false
}

function Set-EsDiskThreshold {
    for ($i = 1; $i -le 5; $i++) {
        try {
            Invoke-RestMethod -Method Put -Uri "$EsUrl/_cluster/settings" -ContentType "application/json" `
                -Body '{"transient":{"cluster.routing.allocation.disk.threshold_enabled":false}}' -TimeoutSec 10 | Out-Null
            return $true
        }
        catch { Start-Sleep -Seconds 3 }
    }
    return $false
}

function Compose-Args {
    @("--project-directory", $ComposeRoot, "-f", $StackFile, "-f", $TestCompose)
}

# --- Down mode ---
if ($Down) {
    Write-Host "🛑 Tearing down the imapbox stack ..." -ForegroundColor Yellow
    docker compose @(Compose-Args) down
    exit 0
}

# --- 1. Preflight: is the GreenMail mock server running? ---
if (-not (Test-Port $GreenMailHost $GreenMailPort)) {
    Write-Warning "GreenMail is not reachable on $GreenMailHost`:$GreenMailPort. Run './mock-server.ps1' first to seed the accounts!"
}

# --- 2. Prepare the test folders ---
Write-Host "🗂  Preparing test folders under $TestDir ..." -ForegroundColor Cyan
if (-not $NoClean) {
    Write-Host "🛑 Stopping containers before cleaning test data ..." -ForegroundColor Yellow
    docker compose @(Compose-Args) down
    foreach ($Dir in @($ArchiveVol, $EsDataVol)) {
        if (Test-Path -LiteralPath $Dir) { Remove-Item -LiteralPath $Dir -Recurse -Force }
    }
}
foreach ($Dir in @($ArchiveVol, $ConfigDir, $EsDataVol)) {
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
}

# --- 3. Write the config beforehand, with random passwords ---
$RandomPasswords = @{}
$AccountSections = @()
foreach ($User in $Accounts) {
    $Login = ($User -split "@")[0]
    $Password = [Guid]::NewGuid().ToString("N")
    $RandomPasswords[$User] = $Password
    $Dsn = "imap://$User`:$Password@$ImapHost`:$ImapPort/INBOX"
    $AccountSections += @("[$Login]`ndsn=$Dsn`n")
}

# main config: has the 2-minute cron in the [imapbox] section (drives the server, since the
# test compose file does not pass --server anymore)
@"
[imapbox]
server=*/2 * * * *

$($AccountSections -join "`n")
"@ | Set-Content -LiteralPath $ConfigFile -Encoding utf8

# one-shot config (accounts only, no [imapbox] server): used for the immediate backup run
@"
$($AccountSections -join "`n")
"@ | Set-Content -LiteralPath $OnceConfigFile -Encoding utf8

Write-Host "✅ Wrote config: $ConfigFile" -ForegroundColor Green

# --- 4. Write the test compose override (top-level volumes only + command without --server) ---
# note: compose is resolved against the imapbox/ folder (--project-directory). Both the stack
# and this override live inside imapbox/, so build contexts are "./" and the bind-mounted
# test data folders sit under ./test/cache.
# The hook command is a webhook test: imapbox PUTs the item payload straight into
# Elasticsearch. "$$" is compose's literal-$ escape (compose would otherwise try to
# interpolate ${...}); the placeholder is resolved to the mail id at hook run time.
$WebhookEsHook = 'newmail,\"put+http://elasticsearch:9200/imapbox/_doc/$${metadata.id}\"'
$WebhookEsInitHook = 'serverstart,\"put+http://elasticsearch:9200/imapbox\"'
@"
services:
  imapbox:
    build:
      context: $($ComposeRoot)
    command: ["--hook", "$($WebhookEsInitHook)", "--hook", "$($WebhookEsHook)"]
  calaca:
    build:
      context: $($ComposeRoot)
    ports:
      - "8088:80"
volumes:
  archive:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: $($ArchiveVol)
  config:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: $($ConfigDir)
  esdata:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: $($EsDataVol)
"@ | Set-Content -LiteralPath $TestCompose -Encoding utf8

Write-Host "✅ Wrote compose override: $TestCompose" -ForegroundColor Green

# --- 5. Validate the merged compose file ---
Write-Host "🧪 Validating merged compose file ..." -ForegroundColor Cyan
docker compose @(Compose-Args) config
if ($LASTEXITCODE -ne 0) {
    Write-Error "Compose validation failed, aborting."
    exit 1
}

# --- 6. Start the stack ---
Write-Host "🚀 Starting the imapbox stack (imapbox + elasticsearch + calaca) ..." -ForegroundColor Cyan
docker compose @(Compose-Args) up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed."
    exit 1
}

# --- 7. Readiness check ---
$Ready = $true
if (-not (Wait-Port "127.0.0.1" 9200 90 "Elasticsearch")) {
    Write-Warning "Elasticsearch did not become ready in time."
    docker compose @(Compose-Args) logs --tail=50 elasticsearch
    $Ready = $false
}
elseif (-not (Wait-EsApi)) {
    Write-Warning "Elasticsearch REST API never became ready."
    docker compose @(Compose-Args) logs --tail=50 elasticsearch
    $Ready = $false
}
if (-not (Wait-Port "127.0.0.1" 8088 30 "Calaca")) {
    Write-Warning "Calaca did not become ready in time."
    $Ready = $false
}

if ($Ready) {
    Write-Host "🧊 Disabling ES disk watermark checks (test drive is nearly full) ..." -ForegroundColor Cyan
    if (Set-EsDiskThreshold) {
        Write-Host "✅ ES disk thresholds disabled" -ForegroundColor Green
    }
    else {
        Write-Warning "Could not confirm ES disk thresholds disabled; indexing may be blocked on this disk."
    }
}

# --- 8. Immediate backup run (default) ---
if (-not $SkipOnce -and $Ready) {
    Write-Host "⚙️ Performing one immediate backup run ..." -ForegroundColor Cyan
    # uses the one-shot config so the (config based) server mode does not take over
    # previous local-file hook (indexes metadata.json via shell script), kept for reference:
    # docker compose @(Compose-Args) exec -T imapbox python ./imapbox.py -c /etc/imapbox/config-once.cfg '--hook' 'newmail,"./hook-addToElasticSearch.sh"'
    # tested hook: PUT the item payload to Elasticsearch through the webhook feature
    docker compose @(Compose-Args) exec -T imapbox python ./imapbox.py -c /etc/imapbox/config-once.cfg '--hook' 'newmail,"put+http://elasticsearch:9200/imapbox/_doc/${metadata.id}"'
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Immediate backup run reported a non-zero exit code ($LASTEXITCODE)."
    }
    Write-Host "🔎 Verifying Elasticsearch index ..." -ForegroundColor Cyan
    $ExpectedCount = $Accounts.Count * 10
    $CountChecked = $false
    for ($i = 1; $i -le 10; $i++) {
        try {
            $Count = (Invoke-RestMethod -Uri "$EsUrl/imapbox/_count" -TimeoutSec 5).count
            if ($Count -eq $ExpectedCount) {
                Write-Host "✅ Indexed $Count/$ExpectedCount emails" -ForegroundColor Green
                $CountChecked = $true
                break
            }
        }
        catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $CountChecked) {
        Write-Warning "Indexed count did not reach $ExpectedCount. Check $EsUrl/_cat/indices"
    }
}

# --- 9. Summary ---
Write-Host "`n"
Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "🚀 ENVIRONMENT IS UP"                                       -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "  Calaca UI:      $CalacaUrl"                               -ForegroundColor Yellow
Write-Host "  Elasticsearch:  $EsUrl"                                   -ForegroundColor Yellow
Write-Host "  GreenMail UI:   $GreenMailUrl"                            -ForegroundColor Yellow
Write-Host "  Archive folder: $ArchiveVol"                              -ForegroundColor Yellow
Write-Host "  Server cron:    */2 * * * * (in $ConfigFile)"             -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  🔑 TEST ACCOUNTS (random passwords, any works on GreenMail):" -ForegroundColor Yellow
foreach ($User in $Accounts) {
    $Login = ($User -split "@")[0]
    Write-Host "  $User [$Login]  password: $($RandomPasswords[$User])" -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Yellow