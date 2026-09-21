# Tile game + Jev SC2 Controller 50/50 for jevbench screengrabs.
# Usage: .\scripts\opencode\layout-screengrab.ps1 [-GameTitle 'Minecraft*']
# Finds windows by exact game title (default "StarCraft II") + controller,
# restores them if minimized, and places game left / controller right.
# Refuses to move anything unless BOTH are found (safe to run anytime).
# The controller widget is a separate Edge --app process: it intentionally
# stays open after SC2 quits so stills can be grabbed post-run.
# For other games (e.g. Minecraft on the remote box), pass -GameTitle:
#   .\layout-screengrab.ps1 -GameTitle 'Minecraft*'
param([string]$GameTitle = 'StarCraft II')
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinTile {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc p, IntPtr l);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr o, int x, int y, int w, int h2, uint f);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int n);
}
'@

function Find-ByTitle([string]$frag) {
  $found = @()
  $cb = [WinTile+EnumWindowsProc]{
    param([IntPtr]$h, [IntPtr]$l)
    if ([WinTile]::IsWindowVisible($h)) {
      $sb = New-Object Text.StringBuilder 512
      if ([WinTile]::GetWindowText($h, $sb, 512) -gt 0) {
        $t = $sb.ToString()
        if ($t -like ("*" + $frag + "*")) { $script:__hits += @{ h = $h; title = $t } }
      }
    }
    return $true
  }
  $script:__hits = @()
  [WinTile]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  return $script:__hits
}

# Exact-match the game window (bare "StarCraft" also hits IDE windows such as
# "...jev-plays-starcraft-2 - Cursor"). Wildcards allowed via -GameTitle.
$sc2 = Find-ByTitle $GameTitle | Where-Object { $_.title -like $GameTitle } | Select-Object -First 1
$ctl = Find-ByTitle 'Jev SC2 Controller' | Select-Object -First 1
if ($sc2) { Write-Output ("FOUND game: " + $sc2.title) } else { Write-Output ("MISSING game window (title like '" + $GameTitle + "')") }
if ($ctl) { Write-Output ("FOUND controller: " + $ctl.title) } else { Write-Output 'MISSING controller window (title *Jev SC2 Controller*)' }
if (-not $sc2 -or -not $ctl) { Write-Output 'LAYOUT_ABORT need both windows; moved nothing'; exit 1 }

$w = [WinTile]::GetSystemMetrics(0)   # SM_CXSCREEN
$h = [WinTile]::GetSystemMetrics(1)   # SM_CYSCREEN
$half = [int]($w / 2)
foreach ($win in @($sc2, $ctl)) {
  if ([WinTile]::IsIconic($win.h)) { [WinTile]::ShowWindow($win.h, 9) | Out-Null }  # SW_RESTORE
}
# SC2 left, controller right (top-level, keep order, show).
[WinTile]::SetWindowPos($sc2.h, [IntPtr]::Zero, 0, 0, $half, $h, 0x0040) | Out-Null
[WinTile]::SetWindowPos($ctl.h, [IntPtr]::Zero, $half, 0, $w - $half, $h, 0x0040) | Out-Null
Write-Output ("LAYOUT_OK sc2=left(0,0,${half}x${h}) controller=right(${half},0)")
