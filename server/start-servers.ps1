<#
.SYNOPSIS
  Start / stop / inspect the local Horizon Private Server stack for SOCOM II (app id 10472).

.DESCRIPTION
  Two launch modes:
    Separate (default) - four processes (NAT, MUIS, Medius, DME), each given <server>\config as its config directory.
                         Robust: every component has its own statics, file logger and console log.
    Unified            - one process, Server.Unified.Launcher.exe, hosting NAT + MUIS + Medius (MAS/MLS/MPS) + DME.
                         KNOWN UPSTREAM RACE: LogSettings.Singleton is a single static shared by all four components and is
                         rewritten by each one every RefreshConfigInterval (5 s). DME's Main (started 5 s after Medius) can
                         therefore read Medius'/MUIS' LogPath, fail to open the already-open log file (NReco FileLoggerProvider
                         uses FileShare.Read) and die silently inside its unobserved Task.Run - symptom: 10073 never listens.
                         Seen on the 2nd launch during bring-up. Use Separate unless you need a single process.

  Console output is captured to logs\console-<component>.log. Do NOT name anything in logs\ "<component>*.log"
  (e.g. dme-foo.log): NReco's rolling logger globs "<basename>*.log", tries to reopen the newest match, and the
  server crashes at start-up if that file is held open by another process.

  Everything runs with WorkingDirectory = this folder, because the servers resolve
  plugins/, logs/, files/ and simulated.db relative to the current directory.

  ADVERTISED ADDRESS: the servers hand clients an address to come back on (Medius PublicIpOverride/NATIp and
  the MUIS universe Endpoint). That address must be the one clients can reach - the host's LAN IP on a LAN,
  its public IP for a hosted server - and it is NOT the same thing as the bind address (everything binds
  0.0.0.0). -PublicIp rewrites exactly those fields in medius.json, dme.json and muis.json before starting;
  -ShowIp (also printed by -Status) shows what is currently advertised. dme.json's MPS.Ip stays 127.0.0.1:
  that is DME reaching Medius on the same machine, not something a client ever sees.

.PARAMETER Mode      Separate | Unified  (default Separate)
.PARAMETER Build     Run "dotnet build -c Release" on the solution first.
.PARAMETER Stop      Stop previously started servers (uses logs\pids.json, falls back to process names).
.PARAMETER Status    Show which Horizon ports are currently listening (and what address is advertised).
.PARAMETER PublicIp  Rewrite the advertised address in medius.json (PublicIpOverride, NATIp), dme.json
                     (PublicIpOverride) and muis.json (Universes[..].Endpoint) to this IP or hostname before
                     starting. Without it the config files are left exactly as they are. REQUIRED once: the
                     tracked configs carry the RFC 5737 placeholder 192.0.2.1, and the script refuses to start
                     the servers (exit 2) while any advertised field holds a documentation address.
.PARAMETER ShowIp    Print the currently advertised address from those three files and exit.
.PARAMETER ConfigDir Directory holding the *.json server configs (default: <this folder>\config).
.PARAMETER NoStart   Do the -PublicIp rewrite (and/or -ShowIp) and exit without starting anything.
.PARAMETER CheckOnly After any -PublicIp rewrite, run the advertised-address check the start runs and exit
                     0 (set) or 2 (an RFC 5737 placeholder remains) without starting anything.
.PARAMETER WaitSeconds  How long to poll for the listeners after starting (default 30).

.EXAMPLE
  .\start-servers.ps1                 # start the four servers, wait for ports, print status
  .\start-servers.ps1 -Status
  .\start-servers.ps1 -Stop
  .\start-servers.ps1 -Mode Unified -Build
  .\start-servers.ps1 -ShowIp                         # what will clients be told?
  .\start-servers.ps1 -PublicIp 203.0.113.7           # hosted box: advertise its public IP, then start
  .\start-servers.ps1 -PublicIp 192.0.2.50 -NoStart   # rewrite the configs only (192.0.2.50: an RFC 5737 example; use yours)
#>
[CmdletBinding()]
param(
    [ValidateSet('Unified', 'Separate')]
    [string]$Mode = 'Separate',
    [switch]$Build,
    [switch]$Stop,
    [switch]$Status,
    [string]$PublicIp,
    [switch]$ShowIp,
    [string]$ConfigDir,
    [switch]$NoStart,
    [switch]$CheckOnly,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = 'Stop'
$ServerDir  = $PSScriptRoot
$SrcDir     = Join-Path $ServerDir 'horizon-server'
if (-not $ConfigDir) { $ConfigDir = Join-Path $ServerDir 'config' }
$LogDir     = Join-Path $ServerDir 'logs'
$PidFile    = Join-Path $LogDir 'pids.json'
$BinRel     = 'bin\Release\net9.0'

$Exe = @{
    Unified = Join-Path $SrcDir "Server.Unified.Launcher\$BinRel\Server.Unified.Launcher.exe"
    NAT     = Join-Path $SrcDir "Server.NAT\$BinRel\Server.NAT.exe"
    MUIS    = Join-Path $SrcDir "Server.UniverseInformation\$BinRel\Server.UniverseInformation.exe"
    Medius  = Join-Path $SrcDir "Server.Medius\$BinRel\Server.Medius.exe"
    DME     = Join-Path $SrcDir "Server.Dme\$BinRel\Server.Dme.exe"
}

# Ports as configured in config\*.json
# NOTE: string keys on purpose - indexing an [ordered] dictionary with an int is positional, not a key lookup.
$TcpPorts = [ordered]@{
    '10071' = 'MUIS (universe info)'
    '10075' = 'MAS  (authentication)'
    '10078' = 'MLS  (lobby)'
    '10077' = 'MPS  (proxy / DME<->Medius)'
    '10073' = 'DME  TCP'
}
$UdpPorts = [ordered]@{
    '10070' = 'NAT  (UDP)'
    '50000' = 'DME  UDP (game data, bound per client on demand)'
}

# --- advertised address -----------------------------------------------------
# The fields the servers hand out to clients. dme.json's MPS.Ip is deliberately NOT in this set:
# it is DME -> Medius on the same host and must stay 127.0.0.1.

function Get-AdvertisedField {
    # -> one object per advertised field: File (name), Path (full), Field (label), Value (current)
    $out = @()

    $p = Join-Path $ConfigDir 'medius.json'
    if (Test-Path $p) {
        $j = Get-Content $p -Raw | ConvertFrom-Json
        foreach ($k in 'PublicIpOverride', 'NATIp') {
            $out += [pscustomobject]@{ File = 'medius.json'; Path = $p; Field = $k; Value = $j.$k }
        }
    }

    $p = Join-Path $ConfigDir 'dme.json'
    if (Test-Path $p) {
        $j = Get-Content $p -Raw | ConvertFrom-Json
        $out += [pscustomobject]@{ File = 'dme.json'; Path = $p; Field = 'PublicIpOverride'; Value = $j.PublicIpOverride }
    }

    $p = Join-Path $ConfigDir 'muis.json'
    if (Test-Path $p) {
        $j = Get-Content $p -Raw | ConvertFrom-Json
        if ($j.Universes) {
            foreach ($appId in $j.Universes.PSObject.Properties.Name) {
                $i = 0
                foreach ($u in @($j.Universes.$appId)) {
                    $out += [pscustomobject]@{ File = 'muis.json'; Path = $p; Field = ('Universes["{0}"][{1}].Endpoint' -f $appId, $i); Value = $u.Endpoint }
                    $i++
                }
            }
        }
    }
    return $out
}

function Show-AdvertisedIp {
    Write-Host ''
    Write-Host "Advertised address (what clients are told to connect back to), from $ConfigDir :" -ForegroundColor Cyan
    $fields = Get-AdvertisedField
    if (-not $fields) { Write-Warning "No server configs found in $ConfigDir"; return }
    foreach ($f in $fields) {
        Write-Host ("  {0,-11} {1,-32} {2}" -f $f.File, $f.Field, $f.Value)
    }
    $distinct = @($fields | Select-Object -ExpandProperty Value -Unique)
    if ($distinct.Count -gt 1) {
        Write-Warning ("Advertised addresses disagree ({0}) - clients will be sent to different hosts. Use -PublicIp <ip> to set all of them." -f ($distinct -join ', '))
    }
    # Host-local, never advertised - shown so nobody "fixes" it.
    $p = Join-Path $ConfigDir 'dme.json'
    if (Test-Path $p) {
        $mps = (Get-Content $p -Raw | ConvertFrom-Json).MPS
        Write-Host ("  {0,-11} {1,-32} {2}   (host-local: DME -> Medius, leave as 127.0.0.1)" -f 'dme.json', 'MPS.Ip', $mps.Ip) -ForegroundColor DarkGray
    }
    Write-Host ''
}

function Set-AdvertisedIp {
    param([Parameter(Mandatory)][string]$Ip)

    $ok = $false
    $parsed = [System.Net.IPAddress]::Any
    if ([System.Net.IPAddress]::TryParse($Ip, [ref]$parsed)) { $ok = $true }
    elseif ($Ip -match '^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$') { $ok = $true }
    if (-not $ok) { throw "-PublicIp '$Ip' is not a valid IP address or hostname." }

    # Key -> the fields rewritten in that file. Only these keys are touched; every other key, and all
    # whitespace/ordering, is preserved because the edit is a targeted rewrite of the raw text.
    $plan = [ordered]@{
        'medius.json' = @('PublicIpOverride', 'NATIp')
        'dme.json'    = @('PublicIpOverride')          # NOT MPS.Ip
        'muis.json'   = @('Endpoint')                  # Universes[..].Endpoint
    }

    $before = Get-AdvertisedField
    $changedAny = $false

    foreach ($file in $plan.Keys) {
        $path = Join-Path $ConfigDir $file
        if (-not (Test-Path $path)) { Write-Warning "config\$file is missing; not rewriting it."; continue }

        $raw = Get-Content $path -Raw
        $new = $raw
        foreach ($key in $plan[$file]) {
            $pattern = '("' + [regex]::Escape($key) + '"\s*:\s*")[^"]*(")'
            $new = [regex]::Replace($new, $pattern, ('${1}' + $Ip + '${2}'))
        }
        if ($new -ceq $raw) {
            Write-Host ("{0}: already {1}" -f $file, (@($before | Where-Object File -eq $file | Select-Object -ExpandProperty Value -Unique) -join ', '))
            continue
        }
        try { $null = $new | ConvertFrom-Json }
        catch { throw "Rewriting $file would produce invalid JSON; nothing was written. ($_)" }

        [System.IO.File]::WriteAllText($path, $new, (New-Object System.Text.UTF8Encoding($false)))
        $changedAny = $true
        foreach ($f in $before | Where-Object { $_.File -eq $file -and $_.Value -ne $Ip }) {
            Write-Host ("{0}: {1} -> {2}" -f $f.File, $f.Field, $Ip) -ForegroundColor Green
        }
    }

    if ($changedAny) {
        $mpsPath = Join-Path $ConfigDir 'dme.json'
        if (Test-Path $mpsPath) {
            $mpsIp = (Get-Content $mpsPath -Raw | ConvertFrom-Json).MPS.Ip
            if ($mpsIp -ne '127.0.0.1') { Write-Warning "dme.json MPS.Ip is $mpsIp (expected 127.0.0.1)." }
        }
    }
}

# ---------------------------------------------------------------------------

function Show-Status {
    Write-Host ''
    Write-Host 'TCP listeners:' -ForegroundColor Cyan
    foreach ($p in $TcpPorts.Keys) {
        $conn = Get-NetTCPConnection -LocalPort ([int]$p) -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            Write-Host ("  {0,-6} {1,-30} LISTENING  {2}  pid {3} ({4})" -f $p, $TcpPorts[$p], $conn.LocalAddress, $conn.OwningProcess, $proc.ProcessName) -ForegroundColor Green
        } else {
            Write-Host ("  {0,-6} {1,-30} not listening" -f $p, $TcpPorts[$p]) -ForegroundColor Yellow
        }
    }
    Write-Host 'UDP endpoints:' -ForegroundColor Cyan
    foreach ($p in $UdpPorts.Keys) {
        $ep = Get-NetUDPEndpoint -LocalPort ([int]$p) -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ep) {
            $proc = Get-Process -Id $ep.OwningProcess -ErrorAction SilentlyContinue
            Write-Host ("  {0,-6} {1,-30} BOUND      {2}  pid {3} ({4})" -f $p, $UdpPorts[$p], $ep.LocalAddress, $ep.OwningProcess, $proc.ProcessName) -ForegroundColor Green
        } else {
            Write-Host ("  {0,-6} {1,-30} not bound" -f $p, $UdpPorts[$p]) -ForegroundColor Yellow
        }
    }
    Write-Host ''
}

function Stop-Servers {
    $stopped = 0
    if (Test-Path $PidFile) {
        $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($entry in $pids) {
            $p = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
            if ($p) {
                Write-Host "Stopping $($entry.Name) (pid $($entry.Pid))"
                Stop-Process -Id $entry.Pid -Force -Confirm:$false
                Wait-Process -Id $entry.Pid -Timeout 10 -ErrorAction SilentlyContinue
                $stopped++
            }
        }
        Remove-Item $PidFile -Force
    }
    # Fallback: anything left by name
    foreach ($name in 'Server.Unified.Launcher', 'Server.NAT', 'Server.UniverseInformation', 'Server.Medius', 'Server.Dme') {
        Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited } | ForEach-Object {
            Write-Host "Stopping stray $name (pid $($_.Id))"
            Stop-Process -Id $_.Id -Force -Confirm:$false -ErrorAction SilentlyContinue
            $stopped++
        }
    }
    Write-Host "Stopped $stopped process(es)."
}

function Start-One {
    param([string]$Name, [string]$Path, [string[]]$Arguments)
    if (-not (Test-Path $Path)) { throw "Missing executable: $Path  (run with -Build first)" }
    # "console-" prefix keeps these clear of NReco's "<component>*.log" rolling glob (see header).
    $out = Join-Path $LogDir "console-$Name.log"
    $err = Join-Path $LogDir "console-$Name.err.log"
    $sp = @{
        FilePath               = $Path
        WorkingDirectory       = $ServerDir
        RedirectStandardOutput = $out
        RedirectStandardError  = $err
        PassThru               = $true
        WindowStyle            = 'Hidden'
    }
    if ($Arguments) { $sp.ArgumentList = $Arguments }
    $proc = Start-Process @sp
    Write-Host ("Started {0,-8} pid {1}  -> {2}" -f $Name, $proc.Id, $out)
    return [pscustomobject]@{ Name = $Name; Pid = $proc.Id }
}

# The advertised address is a REQUIRED value (Sprint 13 S6). The tracked configs carry a documentation placeholder
# from RFC 5737 -- never anybody's own network -- and a stack that would hand it to clients refuses to start and
# names the switch that sets it. (A field left empty is Horizon's own public-IP lookup, and is not refused.)
function Assert-AdvertisedIp {
    # -> exits 2 with one sentence on stderr when any advertised field holds an RFC 5737 address
    $placeholder = @(Get-AdvertisedField | Where-Object { "$($_.Value)" -match '^(192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}$' })
    if ($placeholder.Count -gt 0) {
        $where = ($placeholder | ForEach-Object { '{0} {1}' -f $_.File, $_.Field }) -join ', '
        $values = @($placeholder | Select-Object -ExpandProperty Value -Unique) -join ', '
        $msg = "start-servers: the advertised address is not set -- $where still hold $values, a documentation " +
               "placeholder (RFC 5737) that no client can reach. Run .\start-servers.ps1 -PublicIp <this machine's LAN or " +
               "public address> (it rewrites medius.json, dme.json and muis.json), then start again. Nothing was started."
        [Console]::Error.WriteLine($msg)
        exit 2
    }
}

# ---------------------------------------------------------------------------

if ($Stop)     { Stop-Servers; return }
if ($PublicIp) { Set-AdvertisedIp -Ip $PublicIp }
if ($CheckOnly) { Assert-AdvertisedIp; Write-Host 'CheckOnly: the advertised address is set; nothing was started.'; exit 0 }
if ($Status)   { Show-AdvertisedIp; Show-Status; return }
if ($ShowIp)   { Show-AdvertisedIp; return }
if ($NoStart)  { Write-Host 'NoStart: configuration only, no servers were started.'; return }
Assert-AdvertisedIp


if ($Build) {
    Write-Host 'Building Horizon.Server.sln (Release)...' -ForegroundColor Cyan
    & dotnet build (Join-Path $SrcDir 'Horizon.Server.sln') -c Release --nologo -v minimal
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed with exit code $LASTEXITCODE" }
}

# Folders the servers expect relative to the working directory
foreach ($d in 'config', 'logs', 'medius-plugins', 'dme-plugins', 'files') {
    $full = Join-Path $ServerDir $d
    if (-not (Test-Path $full)) { New-Item -ItemType Directory -Path $full | Out-Null }
}
foreach ($f in 'nat.json', 'muis.json', 'medius.json', 'dme.json', 'db.config.json') {
    if (-not (Test-Path (Join-Path $ConfigDir $f))) {
        Write-Warning "config\$f is missing; the server will generate a default one (NOT tuned for SOCOM II)."
    }
}

if (Test-Path $PidFile) {
    Write-Warning 'pids.json exists - stopping previous instance first.'
    Stop-Servers
}

Show-AdvertisedIp

$started = @()
switch ($Mode) {
    'Unified' {
        # The launcher hard-codes its config directory to <cwd>\config and sets simulated DB mode.
        $started += Start-One -Name 'Unified' -Path $Exe.Unified
    }
    'Separate' {
        $started += Start-One -Name 'NAT'    -Path $Exe.NAT    -Arguments @($ConfigDir)
        $started += Start-One -Name 'MUIS'   -Path $Exe.MUIS   -Arguments @($ConfigDir)
        $started += Start-One -Name 'Medius' -Path $Exe.Medius -Arguments @($ConfigDir)
        # DME connects to MPS (10077); give Medius a moment first.
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline -and -not (Get-NetTCPConnection -LocalPort 10077 -State Listen -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 500 }
        $started += Start-One -Name 'DME'    -Path $Exe.DME    -Arguments @($ConfigDir)
    }
}
$started | ConvertTo-Json | Set-Content -Path $PidFile -Encoding utf8

# Poll until all TCP listeners are up (or timeout)
$deadline = (Get-Date).AddSeconds($WaitSeconds)
do {
    $missing = @($TcpPorts.Keys | Where-Object { -not (Get-NetTCPConnection -LocalPort ([int]$_) -State Listen -ErrorAction SilentlyContinue) })
    if ($missing.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

Show-Status
if ($missing.Count -gt 0) {
    Write-Warning ("Ports still not listening after {0}s: {1}. Check logs\console-*.log" -f $WaitSeconds, ($missing -join ', '))
}
Write-Host "Logs: $LogDir   Stop with: .\start-servers.ps1 -Stop"
