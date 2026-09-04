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

.PARAMETER Mode      Separate | Unified  (default Separate)
.PARAMETER Build     Run "dotnet build -c Release" on the solution first.
.PARAMETER Stop      Stop previously started servers (uses logs\pids.json, falls back to process names).
.PARAMETER Status    Show which Horizon ports are currently listening.
.PARAMETER WaitSeconds  How long to poll for the listeners after starting (default 30).

.EXAMPLE
  .\start-servers.ps1                 # start the four servers, wait for ports, print status
  .\start-servers.ps1 -Status
  .\start-servers.ps1 -Stop
  .\start-servers.ps1 -Mode Unified -Build
#>
[CmdletBinding()]
param(
    [ValidateSet('Unified', 'Separate')]
    [string]$Mode = 'Separate',
    [switch]$Build,
    [switch]$Stop,
    [switch]$Status,
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = 'Stop'
$ServerDir  = $PSScriptRoot
$SrcDir     = Join-Path $ServerDir 'horizon-server'
$ConfigDir  = Join-Path $ServerDir 'config'
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

# ---------------------------------------------------------------------------

if ($Status) { Show-Status; return }
if ($Stop)   { Stop-Servers; return }

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
