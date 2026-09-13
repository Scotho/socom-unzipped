# Kill stale harness drivers and game instances before a launch.
#
# A finished drive.py taskkills the NEXT run's game, and a leftover online_match_ours.py keeps writing
# pad files into it, so run this before every launch (Sprint 5 plan, handoff notes "Harness hazards").
# Kills every python process whose command line contains tools_py.parity and every socom2*.exe, and
# prints one line per process it killed (or would kill, with -DryRun). Exit 0 unless a kill failed.
#
# Do not run it while a gate or a match you want is in flight: it cannot tell a stale driver from a live
# one. The loop lock is what says whether one is live (scripts/loop_lock.sh check).
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 [-DryRun]
# -CommandLineMarker / -ExeNamePattern exist so tests can aim it at a harmless decoy process.
param(
    [switch]$DryRun,
    [string]$CommandLineMarker = 'tools_py.parity',
    [string]$ExeNamePattern = 'socom2*.exe'
)

$self = $PID
$targets = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $self -and (
        ($_.Name -like 'python*' -and $_.CommandLine -and $_.CommandLine.Contains($CommandLineMarker)) -or
        ($_.Name -like $ExeNamePattern)
    )
})

$failed = 0
foreach ($p in $targets) {
    $desc = "pid=$($p.ProcessId) name=$($p.Name) cmd=$($p.CommandLine)"
    if ($DryRun) { Write-Output "WOULD KILL $desc"; continue }
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Output "KILLED $desc"
    } catch {
        Write-Output "FAILED $desc ($($_.Exception.Message))"
        $failed++
    }
}
if ($targets.Count -eq 0) { Write-Output "kill_stale_drivers: nothing to kill" }
else { Write-Output ("kill_stale_drivers: {0} {1}" -f $targets.Count, $(if ($DryRun) { 'would be killed' } else { 'matched' })) }
if ($failed -gt 0) { exit 1 }
exit 0
