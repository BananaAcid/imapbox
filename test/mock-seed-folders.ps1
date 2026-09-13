#!/usr/bin/env pwsh

[CmdletBinding()]
param(
    [int]$Port = 3143
)

# Seeds GreenMail with test folders (Draft, Trash, INBOX.important projects.someemail)
# containing dummy emails via IMAP APPEND. SMTP can only deliver into INBOX,
# so non-INBOX folders require IMAP.

$ImapHost = "127.0.0.1"
$User     = "alice@example.com"
$Password = "c6332d839548482fbf92fa94943ba039"

$Client = [System.Net.Sockets.TcpClient]::new($ImapHost, $Port)
$Stream = $Client.GetStream()
$Buffer = New-Object byte[] 65536
$Tag    = 0

function Read-Response {
    $out = ""
    while ($Stream.DataAvailable) {
        $n = $Stream.Read($Buffer, 0, $Buffer.Length)
        $out += [Text.Encoding]::ASCII.GetString($Buffer, 0, $n)
    }
    return $out
}

function Wait-And-Respond {
    param([string]$Cmd)
    Start-Sleep -Milliseconds 400
    Read-Response | Out-Null
    $script:Tag++
    $bytes = [Text.Encoding]::ASCII.GetBytes("A$($script:Tag) $Cmd`r`n")
    $Stream.Write($bytes, 0, $bytes.Length)
    $Stream.Flush()
    Start-Sleep -Milliseconds 500
    return Read-Response
}

function Send-Append {
    param([string]$Folder, [string]$Message)
    Start-Sleep -Milliseconds 400
    Read-Response | Out-Null
    $script:Tag++
    $literal = "$Message`r`n"
    $bytes = [Text.Encoding]::ASCII.GetBytes($literal)
    $cmd = "A$($script:Tag) APPEND `"$Folder`" (\Seen) {$($bytes.Length)}"
    $cmdBytes = [Text.Encoding]::ASCII.GetBytes("$cmd`r`n")
    $Stream.Write($cmdBytes, 0, $cmdBytes.Length)
    $Stream.Flush()
    Start-Sleep -Milliseconds 500
    $cont = Read-Response
    $Stream.Write($bytes, 0, $bytes.Length)
    $Stream.Flush()
    $crlf = [Text.Encoding]::ASCII.GetBytes("`r`n")
    $Stream.Write($crlf, 0, 2)
    $Stream.Flush()
    Start-Sleep -Milliseconds 500
    return Read-Response
}

function New-DummyMail {
    param([string]$Subject, [string]$Date)
    $msgId = "$([Guid]::NewGuid().ToString('N'))@mock-generator.local"
    return "From: system@mock-generator.local`r`nTo: $User`r`nSubject: $Subject`r`nDate: $Date`r`nMessage-ID: <$msgId>`r`nMIME-Version: 1.0`r`nContent-Type: text/plain; charset=UTF-8`r`nContent-Transfer-Encoding: 7bit`r`n`r`nDummy email: $Subject`r`nUUID: $([Guid]::NewGuid().ToString())`r`n"
}

try {
    Start-Sleep -Milliseconds 500
    $banner = Read-Response
    Write-Host "⚙️ Connected to GreenMail ($($banner.Trim()))" -ForegroundColor Cyan

    Write-Host "🔑 Logging in as $User ..." -ForegroundColor Cyan
    Wait-And-Respond "LOGIN $User $Password" | ForEach-Object { Write-Host "  -> $_" }

    $Folders = @("Draft", "Trash", "INBOX.important projects.someemail")

    foreach ($Folder in $Folders) {
        Write-Host "📁 Creating folder: $Folder" -ForegroundColor Cyan
        $result = Wait-And-Respond "CREATE `"$Folder`""
        $result | ForEach-Object { Write-Host "  -> $_" }
    }

    Write-Host "✉️ Appending dummy emails..." -ForegroundColor Cyan
    $Appends = @(
        @{ Folder = "Draft"; Subject = "Draft 2026 #1"; Date = "Wed, 15 Jan 2026 10:30:00 +0000" },
        @{ Folder = "Draft"; Subject = "Draft 2026 #2"; Date = "Sat, 20 Jun 2026 14:45:00 +0000" },
        @{ Folder = "Draft"; Subject = "Draft 2024 #1"; Date = "Sun, 03 Mar 2024 09:15:00 +0000" },
        @{ Folder = "Trash"; Subject = "Trash 2026 #1"; Date = "Mon, 02 Feb 2026 08:00:00 +0000" },
        @{ Folder = "Trash"; Subject = "Trash 2026 #2"; Date = "Fri, 10 Jul 2026 16:20:00 +0000" },
        @{ Folder = "INBOX.important projects.someemail"; Subject = "Important 2026 #1"; Date = "Tue, 21 Apr 2026 11:05:00 +0000" }
    )

    foreach ($Item in $Appends) {
        $mail = New-DummyMail -Subject $Item.Subject -Date $Item.Date
        $result = Send-Append -Folder $Item.Folder -Message $mail
        $result | ForEach-Object { Write-Host "  [$($Item.Folder)] -> $_" }
    }

    Write-Host "📋 Folder list:" -ForegroundColor Yellow
    Wait-And-Respond 'LIST "" "*"' | ForEach-Object { Write-Host "  $_" }

    foreach ($Folder in $Folders) {
        Write-Host "📊 STATUS: $Folder" -ForegroundColor Yellow
        Wait-And-Respond "STATUS `"$Folder`" (MESSAGES)" | ForEach-Object { Write-Host "  $_" }
    }

    Write-Host "`n✅ SEEDING COMPLETE" -ForegroundColor Green
}
catch {
    Write-Error "Seeding failed: $_"
    if ($_.Exception.InnerException) {
        Write-Error "Details: $($_.Exception.InnerException.Message)"
    }
}
finally {
    $Client.Close()
}