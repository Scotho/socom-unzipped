<#
.SYNOPSIS
Moves old gate stamps and run logs out of logs/ to an archive drive (Sprint 6 Task 8).

.DESCRIPTION
Gate stamps (logs/parity/gate/<stamp>/) and run logs (logs/run_*.log) older than -Days (14) are moved to
-Dest (D:\socom_archive), keeping their relative paths. Anything docs/KNOWN.md section 1 ("Proven") names --
a stamp, a run log, a `logs/...` path, including shell patterns like run_[AB]_2026... -- is never moved: those
are the artefacts the proven rows point at. Dry-run by default: prints what would move and the total size;
-Apply moves.

.EXAMPLE
powershell -File scripts/archive_logs.ps1              # dry run
powershell -File scripts/archive_logs.ps1 -Apply       # move
powershell -File scripts/archive_logs.ps1 -Root .\logs -Dest D:\socom_archive -Days 14 -Known .\docs\KNOWN.md
#>
param(
    [string]$Root = (Join-Path $PSScriptRoot "..\logs"),
    [string]$Dest = "D:\socom_archive",
    [int]$Days = 14,
    [string]$Known = (Join-Path $PSScriptRoot "..\docs\KNOWN.md"),
    [switch]$Apply
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $Root).Path
$cutoff = (Get-Date).AddDays(-$Days)

# The names KNOWN section 1 protects: every backticked logs/ path (as a regex, so a shell pattern such as
# run_[AB]_2026... or frost{A,B}_... protects every expansion) and every stamp-looking token.
$patterns = New-Object System.Collections.Generic.List[string]
$names = New-Object System.Collections.Generic.HashSet[string]
if (Test-Path $Known) {
    $text = Get-Content $Known -Raw
    $start = $text.IndexOf("## 1.")
    $end = $text.IndexOf("## 2.", [Math]::Max($start, 0))
    if ($start -ge 0) {
        $section = if ($end -gt $start) { $text.Substring($start, $end - $start) } else { $text.Substring($start) }
        foreach ($m in [regex]::Matches($section, '`logs/([^`]+)`')) {
            $rel = $m.Groups[1].Value.Replace('/', '\')
            $rx = [regex]::Escape($rel)
            # [regex]::Escape turned [AB] into \[AB] and {A,B} into \{A,B}: put the class back, and turn the
            # brace list into an alternation
            $rx = $rx.Replace('\[', '[')
            while ($rx -match '\\\{([^}]+)}') {
                $alt = '(' + ($matches[1].Replace(',', '|')) + ')'
                $rx = $rx.Replace($matches[0], $alt)
            }
            $patterns.Add('^' + $rx)
        }
        foreach ($m in [regex]::Matches($section, '\b(s\d_[a-z0-9_]+|ours_[a-z0-9_]+|run_[AB]_\d{8}_\d{6})\b')) {
            [void]$names.Add($m.Value)
        }
    }
}

function Is-Protected([string]$relative, [string]$name) {
    foreach ($p in $patterns) {
        if ($relative -imatch $p -or $name -imatch $p) { return $true }
    }
    foreach ($n in $names) {
        if ($name -ieq $n) { return $true }
        if ($name.StartsWith($n + ".", [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

$candidates = @()
$gate = Join-Path $Root "parity\gate"
if (Test-Path $gate) {
    foreach ($d in Get-ChildItem $gate -Directory) {
        if ($d.LastWriteTime -ge $cutoff) { continue }
        $rel = "parity\gate\" + $d.Name
        if (Is-Protected $rel $d.Name) { continue }
        $size = (Get-ChildItem $d.FullName -Recurse -File | Measure-Object Length -Sum).Sum
        $candidates += [pscustomobject]@{ Kind = "stamp"; Path = $d.FullName; Relative = $rel; Bytes = [int64]$size }
    }
}
foreach ($f in Get-ChildItem $Root -File -Filter "run_*.log") {
    if ($f.LastWriteTime -ge $cutoff) { continue }
    if (Is-Protected $f.Name $f.BaseName) { continue }
    $candidates += [pscustomobject]@{ Kind = "run log"; Path = $f.FullName; Relative = $f.Name; Bytes = [int64]$f.Length }
}

$total = ($candidates | Measure-Object Bytes -Sum).Sum
if (-not $total) { $total = 0 }
$mode = if ($Apply) { "MOVING" } else { "DRY RUN (add -Apply to move)" }
Write-Output ("archive_logs: {0}: {1} items, {2:N1} GB, older than {3} days, {4} protected names from KNOWN section 1 -> {5}" -f `
    $mode, $candidates.Count, ($total / 1GB), $Days, ($patterns.Count + $names.Count), $Dest)
foreach ($c in $candidates) {
    Write-Output ("  {0,-8} {1,8:N1} MB  {2}" -f $c.Kind, ($c.Bytes / 1MB), $c.Relative)
    if ($Apply) {
        $target = Join-Path $Dest $c.Relative
        $parent = Split-Path $target -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Move-Item -LiteralPath $c.Path -Destination $target
    }
}
