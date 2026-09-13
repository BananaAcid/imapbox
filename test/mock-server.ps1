#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [switch]$SkipDocker  # skip the Docker/GreenMail launch and readiness checks, only generate mock emails
)

# --- Configuration ---
$ContainerName = "local-imap"
$SmtpServer    = "127.0.0.1"   # Forced IPv4 to prevent IPv6 loopback issues
$SmtpPort      = 3025
$ImapPort      = 3143
$ImapsPort     = 3993
$UiPort        = 8089
$Users         = @("alice@example.com", "bob@example.com")

# --- 1. Manage Docker Container (skipped with -SkipDocker) ---
if (-not $SkipDocker) {
    if (docker ps -a --format '{{.Names}}' | Select-String -Quiet -Pattern "^$ContainerName$") {
        Write-Host "🔄 Found existing container '$ContainerName'. Restarting clean..." -ForegroundColor Yellow
        docker rm -f $ContainerName | Out-Null
    }

    Write-Host "🐳 Launching GreenMail Docker container..." -ForegroundColor Cyan
    docker run -d `
        --name $ContainerName `
        -p "${SmtpPort}:3025" `
        -p "${ImapPort}:3143" `
        -p "${ImapsPort}:3993" `
        -p "${UiPort}:8080" `
        greenmail/standalone | Out-Null

    # --- 2. Dynamic Readiness Check ---
    Write-Host "⏳ Waiting for GreenMail network ports to open..." -ForegroundColor Cyan
    $MaxAttempts = 30
    $Attempt = 1
    $IsReady = $false

    while (-not $IsReady -and $Attempt -le $MaxAttempts) {
        $TcpClient = New-Object System.Net.Sockets.TcpClient
        try {
            $Connection = $TcpClient.ConnectAsync($SmtpServer, $SmtpPort)
            if ($Connection.Wait(1000) -and $TcpClient.Connected) {
                $IsReady = $true
            }
        }
        catch {}
        finally { $TcpClient.Dispose() }

        if (-not $IsReady) {
            Write-Host "." -NoNewline -ForegroundColor Gray
            Start-Sleep -Seconds 1
            $Attempt++
        }
    }

    if (-not $IsReady) {
        Write-Error "`n❌ Timeout: GreenMail failed to become ready within $MaxAttempts seconds."
        exit 1
    }

    # 🛠️ STABILITY PATCH: Port is open, wait briefly for the SMTP background engine to spawn
    Start-Sleep -Seconds 2

    Write-Host "`n🚀 GreenMail is ready and listening on port $SmtpPort!" -ForegroundColor Green
}
else {
    Write-Host "⏩ Skipping Docker launch (GreenMail expected to already be running)..." -ForegroundColor DarkYellow
}

# --- 3. Email Generator Loop ---
$SmtpClient = [System.Net.Mail.SmtpClient]::new($SmtpServer, $SmtpPort)

try {
    foreach ($User in $Users) {
        Write-Host "⚙️ Generating 10 mock emails for: $User" -ForegroundColor Cyan
        
        for ($i = 1; $i -le 10; $i++) {
            $Subject = "Mock Email #$i for $User"
            $Body    = @"
Hello,

This is dummy email number $i systematically generated for testing purposes.
Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
UUID: $([Guid]::NewGuid().ToString())

Regards,
Mock System Generator
"@

            $MailMessage = [System.Net.Mail.MailMessage]::new("system@mock-generator.local", $User, $Subject, $Body)
            $SmtpClient.Send($MailMessage)
            $MailMessage.Dispose()
            
            Write-Host "  -> Sent email $i/10..." -ForegroundColor Gray
            Start-Sleep -Milliseconds 50
        }
        Write-Host "✅ Completed seeding $User" -ForegroundColor Green
    }

    # --- 4. Final Connection Instructions (Yellow Output) ---
    Write-Host "`n"
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "🎉 ENVIRONMENT IS LIVE & SEEDED SUCCESSFULLY"               -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  IMAP Server:  $SmtpServer"                                -ForegroundColor Yellow
    Write-Host "  IMAP Port:    $ImapPort (Non-SSL / Plain text)"           -ForegroundColor Yellow
    Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  🔑 TEST USER ACCOUNTS AVAILABLE (10 emails each):"        -ForegroundColor Yellow
    Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  User 1 Username:  $($Users[0])"                           -ForegroundColor Yellow
    Write-Host "  User 1 Password:  [Any text or password will work]"       -ForegroundColor Yellow
    Write-Host ""                                                           -ForegroundColor Yellow
    Write-Host "  User 2 Username:  $($Users[1])"                           -ForegroundColor Yellow
    Write-Host "  User 2 Password:  [Any text or password will work]"       -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
}
catch {
    Write-Error "Connection error during seeding: $_"
    if ($_.Exception.InnerException) {
        Write-Error "Details: $($_.Exception.InnerException.Message)"
    }
}
finally {
    $SmtpClient.Dispose()
}
