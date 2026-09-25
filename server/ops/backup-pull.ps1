<#
.SYNOPSIS
  Pull the hosted box's newest backup set to this machine and verify it (Sprint 10 Goal 2; tracked by Sprint 13
  Task O3). A backup that lives only on the box dies with the box: run it after anything that matters (a new
  player's first login, a re-seed) and at least weekly.

.DESCRIPTION
  Reads ops.env (-EnvFile, else ops.env beside this script): OPS_BOX_HOST, OPS_BOX_USER, OPS_SSH_KEY,
  OPS_KNOWN_HOSTS, OPS_BACKUP_DIR (the sets' folder on the box) and OPS_PULL_DIR (where they land here).
  Nothing about the box is written in this file. Uses the ssh.exe (on PATH) and System32's tar.exe that ship with Windows 10 and 11.

  The set lands in <OPS_PULL_DIR>\<stamp>\ and every file is checked against the set's SHA256SUMS (bare names, or
  the absolute box paths the Sprint 10 sets carry). -VerifyOnly <folder> checks a set already pulled and needs no
  ops.env. Exit 0 verified, 1 a pull or a check failed, 2 ops.env missing, incomplete or still holding the
  example's placeholder address.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File server\ops\backup-pull.ps1
#>
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot 'ops.env'),
    [string]$VerifyOnly = ''
)
$ErrorActionPreference = 'Stop'

function Fail([int]$code, [string]$msg) { [Console]::Error.WriteLine("backup-pull: $msg"); exit $code }

function Test-Set([string]$dest) {
    $sums = Join-Path $dest 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $sums)) { Fail 1 "$dest has no SHA256SUMS" }
    $bad = @(); $n = 0; $db = $null
    foreach ($line in Get-Content -LiteralPath $sums) {
        if ($line -notmatch '^([0-9a-fA-F]{64})\s+\*?(.+)$') { continue }
        $want = $Matches[1].ToLower(); $name = Split-Path -Leaf $Matches[2]
        if ($name -eq 'simulated.db' -or $name -eq 'simulated.db.unsettled') { $db = $name }
        $file = Join-Path $dest $name
        $n++
        if (-not (Test-Path -LiteralPath $file)) { $bad += "$name missing"; continue }
        $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLower()
        if ($got -ne $want) { $bad += "$name differs" }
    }
    if ($n -eq 0) { Fail 1 "$sums lists no files" }
    if (-not $db) { Fail 1 "$sums does not list simulated.db: the set holds no account store" }
    if ($bad.Count -gt 0) { Fail 1 ("$dest did not verify: " + ($bad -join ', ')) }
    if ($db -eq 'simulated.db.unsettled') {
        Write-Output "backup-pull: $dest verified ($n files) -- but its database never settled (simulated.db.unsettled)"
        return
    }
    Write-Output "backup-pull: $dest verified ($n files)"
}

function Read-OpsEnv([string]$path) {
    $vals = @{}
    foreach ($line in Get-Content -LiteralPath $path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $v = $t.Substring($i + 1).Trim()
        if ($v.Length -ge 2 -and (($v[0] -eq '"' -and $v[-1] -eq '"') -or ($v[0] -eq "'" -and $v[-1] -eq "'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        $vals[$t.Substring(0, $i).Trim()] = $v
    }
    return $vals
}

if ($VerifyOnly) { Test-Set $VerifyOnly; exit 0 }

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Fail 2 "no ops.env at $EnvFile (copy server\ops\ops.env.example to it and fill it in)"
}
$ops = Read-OpsEnv $EnvFile
foreach ($k in 'OPS_BOX_HOST', 'OPS_BOX_USER', 'OPS_SSH_KEY', 'OPS_KNOWN_HOSTS', 'OPS_BACKUP_DIR', 'OPS_PULL_DIR') {
    if (-not $ops.ContainsKey($k) -or [string]::IsNullOrWhiteSpace($ops[$k])) { Fail 2 "ops.env must set $k" }
}
# RFC 5737 documentation ranges: the example's placeholder, never a box.
if ($ops.OPS_BOX_HOST -match '^(192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}$') {
    Fail 2 "OPS_BOX_HOST in $EnvFile is still the example's placeholder; set the box's address or name"
}
if (-not (Test-Path -LiteralPath $ops.OPS_SSH_KEY)) { Fail 2 "OPS_SSH_KEY names a file that does not exist" }
# The box's host key is pinned, never learnt: an empty or missing known_hosts would trust whatever answers first.
if (-not (Test-Path -LiteralPath $ops.OPS_KNOWN_HOSTS -PathType Leaf) -or (Get-Item -LiteralPath $ops.OPS_KNOWN_HOSTS).Length -eq 0) {
    Fail 2 "OPS_KNOWN_HOSTS must name a known_hosts file holding the box's host key (missing or empty)"
}

function Quote([string]$s) { '"' + $s + '"' }
# The call operator quotes each argument itself; Start-Process joins its list with spaces, so that one is quoted here.
function Ssh-Args([bool]$quoted) {
    $key = $ops.OPS_SSH_KEY; $kh = 'UserKnownHostsFile=' + $ops.OPS_KNOWN_HOSTS
    if ($quoted) { $key = Quote $key; $kh = Quote $kh }
    @('-o', 'IdentitiesOnly=yes', '-i', $key, '-o', $kh, '-o', 'StrictHostKeyChecking=yes',
      '-o', 'ConnectTimeout=15', ($ops.OPS_BOX_USER + '@' + $ops.OPS_BOX_HOST))
}
$sshArgs = Ssh-Args $false
$remoteDir = $ops.OPS_BACKUP_DIR.TrimEnd('/')

# The newest set's name. The sets are root-only on the box, so both reads go through sudo.
$names = & ssh.exe @sshArgs "sudo ls -1 '$remoteDir'"
if ($LASTEXITCODE -ne 0) { Fail 1 "ssh to the box failed (exit $LASTEXITCODE)" }
$newest = $names | Where-Object { $_ -match '^\d{8}T\d{6}Z$' } | Sort-Object | Select-Object -Last 1
if (-not $newest) { Fail 1 "no backup set on the box under $remoteDir" }

New-Item -ItemType Directory -Force -Path $ops.OPS_PULL_DIR | Out-Null
$tgz = Join-Path $ops.OPS_PULL_DIR ("$newest.tgz")
# Binary-safe: the tarball goes straight to a file (a PowerShell 5.1 pipeline would re-encode it as text).
$p = Start-Process -FilePath 'ssh.exe' -NoNewWindow -Wait -PassThru -RedirectStandardOutput $tgz `
    -ArgumentList ((Ssh-Args $true) + @((Quote "sudo tar -czf - -C '$remoteDir' '$newest'")))
if ($p.ExitCode -ne 0) {
    Remove-Item -LiteralPath $tgz -Force -ErrorAction SilentlyContinue
    Fail 1 "streaming the set failed (ssh exit $($p.ExitCode))"
}
& (Join-Path $env:SystemRoot 'System32\tar.exe') -xzf $tgz -C $ops.OPS_PULL_DIR
if ($LASTEXITCODE -ne 0) { Fail 1 "unpacking $tgz failed (tar exit $LASTEXITCODE)" }
Remove-Item -LiteralPath $tgz -Force

Test-Set (Join-Path $ops.OPS_PULL_DIR $newest)
