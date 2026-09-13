# Kill stale harness DRIVERS and game instances before a launch.
#
# A finished drive.py taskkills the NEXT run's game, and a leftover online_match_ours.py keeps writing
# pad files into it, so run this before every launch (Sprint 5 plan, handoff notes "Harness hazards").
#
# Kills only:
#   - python whose command line runs a driver module: tools_py.parity.drive, .online_match_ours,
#     .online_login_ours, .gate, .sp_death_probe (as `-m tools_py.parity.X` or `tools_py/parity/X.py`);
#   - socom2*.exe.
# Never kills its own ancestor chain (a gate or driver that calls this script), nor lock-free offline
# tools_py.parity scorers (verdict_core, object_diff, montage, ...) that parallel agents may be running.
# Prints one line per process killed (KILLED) or considered and spared (SKIPPED ... (reason)).
# Exit 0 unless a kill failed.
#
# It cannot tell a stale driver from a live one of ANOTHER checkout or agent; the loop lock is what says
# whether one is live (scripts/loop_lock.sh check) -- run this only while you hold it.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 [-DryRun]
# -OnlyCommandLineContaining / -ExeNamePattern exist so tests can confine it to decoy processes.
param(
    [switch]$DryRun,
    [string]$OnlyCommandLineContaining = '',
    [string]$ExeNamePattern = 'socom2*.exe'
)

$driverRe = 'tools_py[.\\/]parity[.\\/](drive|online_match_ours|online_login_ours|gate|sp_death_probe)(\.py)?(?![\w.])'
$parityRe = 'tools_py[.\\/]parity'

$all = @(Get-CimInstance Win32_Process)
$byId = @{}
foreach ($p in $all) { $byId[[int]$p.ProcessId] = $p }
$ancestors = @{}
$cur = [int]$PID
$steps = 0
while ($byId.ContainsKey($cur) -and -not $ancestors.ContainsKey($cur) -and $steps -lt 64) {
    $ancestors[$cur] = $true
    $cur = [int]$byId[$cur].ParentProcessId
    $steps++
}

$killed = 0
$failed = 0
foreach ($p in $all) {
    $cmd = [string]$p.CommandLine
    if ($OnlyCommandLineContaining -and -not $cmd.Contains($OnlyCommandLineContaining)) { continue }
    $isExe = $p.Name -like $ExeNamePattern
    $isPy = $p.Name -like 'python*'
    $isParity = $isPy -and ($cmd -match $parityRe)
    if (-not ($isExe -or $isParity)) { continue }
    $desc = "pid=$($p.ProcessId) name=$($p.Name) cmd=$cmd"
    if ($ancestors.ContainsKey([int]$p.ProcessId)) { Write-Output "SKIPPED $desc (ancestor of this script)"; continue }
    if (-not $isExe -and -not ($cmd -match $driverRe)) { Write-Output "SKIPPED $desc (not a driver module)"; continue }
    if ($DryRun) { Write-Output "WOULD KILL $desc"; $killed++; continue }
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Output "KILLED $desc"
        $killed++
    } catch {
        Write-Output "FAILED $desc ($($_.Exception.Message))"
        $failed++
    }
}
Write-Output ("kill_stale_drivers: {0} {1}, {2} failed" -f $killed, $(if ($DryRun) { 'would be killed' } else { 'killed' }), $failed)
if ($failed -gt 0) { exit 1 }
exit 0
