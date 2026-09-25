# Capture ONLY the StarCraft II game window to a PNG via PrintWindow (renders the
# window's own pixels even when it is occluded by the IDE/other windows).
# No desktop, no IDE, no log panel, no taskbar. Usage:
#   .\capture-game-window.ps1 -Out <path.png>
param([Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public struct RECT { public int Left, Top, Right, Bottom; }
public class WinCap {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumW p, IntPtr l);
  public delegate bool EnumW(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
}
'@
# Find the window by exact title (same EnumWindows method layout-screengrab uses).
$script:__h = [IntPtr]::Zero
$cb = [WinCap+EnumW]{
  param([IntPtr]$h, [IntPtr]$l)
  if ([WinCap]::IsWindowVisible($h)) {
    $sb = New-Object Text.StringBuilder 512
    if ([WinCap]::GetWindowText($h, $sb, 512) -gt 0) {
      if ($sb.ToString() -eq 'StarCraft II') { $script:__h = $h; return $false }
    }
  }
  return $true
}
[void][WinCap]::EnumWindows($cb, [IntPtr]::Zero)
$hwnd = $script:__h
if ($hwnd -eq [IntPtr]::Zero) { Write-Error 'StarCraft II window not found'; exit 1 }
$rect = New-Object RECT
[void][WinCap]::GetWindowRect($hwnd, [ref]$rect)
$w = $rect.Right - $rect.Left
$hgt = $rect.Bottom - $rect.Top
if ($w -le 0 -or $hgt -le 0) { Write-Error 'bad window rect'; exit 1 }
$bmp = New-Object System.Drawing.Bitmap $w, $hgt
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# PW_RENDERFULLCONTENT = 2: ask the app to render its full content (works for DirectX).
$ok = [WinCap]::PrintWindow($hwnd, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()
if (-not $ok) { $bmp.Dispose(); Write-Error 'PrintWindow failed'; exit 1 }
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("CAPTURED " + $Out + " " + $w + "x" + $hgt)
