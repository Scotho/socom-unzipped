<#
  Sprint 7 Task 1b: hold the game window in the modal size-move loop, the way a player dragging the
  title bar does, so the back-pressure latch trips and the bounded command queue is measured under
  the condition that used to balloon it (KNOWN section 4: ~15 GB working set after a drag).

      powershell.exe -NoProfile -File scripts/parity/drag_window.ps1 -Title "PS2-Recomp" -Seconds 30

  Posts WM_SYSCOMMAND/SC_MOVE (the window enters the loop and stops pumping), waits -Seconds, then
  sends {ESC} to leave it. Exits 1 when no window matches -Title.
#>
param(
  [string]$Title = "PS2-Recomp",
  [int]$Seconds = 30
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class DragWin
{
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
}
"@

$WM_SYSCOMMAND = 0x0112
$SC_MOVE = 0xF010

$proc = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if ($null -eq $proc) {
  Write-Output "drag_window: no window titled '$Title'"
  exit 1
}

$hwnd = $proc.MainWindowHandle
Write-Output ("drag_window: '{0}' (pid {1}, hwnd 0x{2:X}) -> SC_MOVE for {3} s" -f $proc.MainWindowTitle, $proc.Id, [int64]$hwnd, $Seconds)
[void][DragWin]::SetForegroundWindow($hwnd)
if (-not [DragWin]::PostMessage($hwnd, $WM_SYSCOMMAND, [IntPtr]$SC_MOVE, [IntPtr]::Zero)) {
  Write-Output "drag_window: PostMessage(SC_MOVE) failed"
  exit 1
}

Start-Sleep -Seconds $Seconds

# ESC leaves the size-move loop and puts the window back where it was. SendKeys goes to the
# foreground window, which is the one holding the loop.
[void][DragWin]::SetForegroundWindow($hwnd)
(New-Object -ComObject WScript.Shell).SendKeys("{ESC}")
Start-Sleep -Milliseconds 500
Write-Output ("drag_window: released after {0} s (window alive: {1})" -f $Seconds, [DragWin]::IsWindow($hwnd))
exit 0
