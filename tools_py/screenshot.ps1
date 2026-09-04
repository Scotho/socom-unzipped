# Capture a window (by process name) or the whole primary screen to a PNG.
# Usage: powershell -File screenshot.ps1 -Process pcsx2-qt -Out C:\path\shot.png
param(
    [string]$Process = "",
    [string]$Out = "shot.png"
)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$rect = $null
if ($Process -ne "") {
    $p = Get-Process -Name $Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) {
        [Win32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
        Start-Sleep -Milliseconds 300
        $r = New-Object Win32+RECT
        [Win32]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
        if ($r.Right - $r.Left -gt 0) { $rect = $r }
        Write-Host ("window '{0}' rect {1},{2}-{3},{4}" -f $p.MainWindowTitle, $r.Left, $r.Top, $r.Right, $r.Bottom)
    } else { Write-Host "process '$Process' has no window; capturing screen" }
}
if ($rect -eq $null) {
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $rect = New-Object Win32+RECT; $rect.Left=$b.Left; $rect.Top=$b.Top; $rect.Right=$b.Right; $rect.Bottom=$b.Bottom
}
$w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size $w, $h))
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "saved $Out ($w x $h)"
