# ============================================================================
# COMPILE CHECK -- load the owner's real mod list, parse every script, quit.
#
# Hidden and harmless, so it can run while the owner is playing something else:
#
#   -norun      D_DoomMain returns (d_main.cpp "special exit") BEFORE V_Init2, so no
#               game window, no fullscreen, no video mode change. OpenXR is started
#               only from MainWindow::ShowGameView -> I_InitInput, which the video
#               init calls -- never reached. The startup window is created hidden
#               and only ever SW_HIDE'd. Launched -WindowStyle Hidden on top of that.
#   -config     a SCRATCH COPY of doomxr.ini. The engine saves its config on exit;
#               the copy takes that write, the owner's ini is never opened for write.
#   scratch cwd the engine writes log-debug.txt / doomxr-log.txt into its working
#               directory, and the ones beside the exe hold the last headset test.
#               Checked before and after: if either changes, the run says so loudly.
#
# LOAD ORDER: read from the exe folder's doomxr-log.txt ("adding ...") -- the files
# the owner's last real launch loaded, in order -- unless -Files is given. The
# engine's own pk3s and the IWAD are skipped from that list (the engine adds them).
#
# PASS only on "script parsing took" with no script error lines. Compile errors in
# this engine never contain the word "error" on their own line, so the check looks
# for the pk3:zscript location lines and "Script error" as well.
#
#   powershell -File tools\compile_check.ps1
#   powershell -File tools\compile_check.ps1 -Files E:\DOOMWork\RS_VRBody\RS_VRBody.pk3
# ============================================================================
[CmdletBinding()]
param(
    [string[]] $Files,
    [string]   $Engine = '',   # another build's exe folder (e.g. the Selaco engine folder); iwad, load order and guards stay the owner's
    [int]      $TimeoutSec = 180
)
$ErrorActionPreference = 'Stop'

$eng  = 'E:\DOOMWork\UZDXREMA\build-dxr\RelWithDebInfo'
$exe  = Join-Path $eng 'doomxr.exe'
if ($Engine) { $exe = Join-Path $Engine 'doomxr.exe' }   # the exe only: its own pk3s sit beside it
$iwad = Join-Path $eng 'doom.wad'
$ini  = Join-Path $env:USERPROFILE 'Documents\My Games\DoomXR\doomxr.ini'
if (-not (Test-Path $exe))  { throw "no engine at $exe" }
if (-not (Test-Path $iwad)) { throw "no iwad at $iwad" }

# ---- the load order ---------------------------------------------------------
if (-not $Files) {
    $src = Join-Path $eng 'doomxr-log.txt'
    if (-not (Test-Path $src)) { throw "no -Files and no $src to read the load order from" }
    $engineOwn = 'doomxr.pk3','game_support.pk3','lights.pk3','brightmaps.pk3','game_widescreen_gfx.pk3'
    $Files = @(Select-String -Path $src -Pattern '^adding (.+?), \d+ lumps' | ForEach-Object {
        $_.Matches[0].Groups[1].Value -replace '/', '\'
    } | Where-Object {
        $leaf = Split-Path $_ -Leaf
        ($engineOwn -notcontains $leaf) -and ($leaf -notmatch '\.wad$')
    })
}
foreach ($f in $Files) { if (-not (Test-Path $f)) { throw "load order names a missing file: $f" } }

# ---- scratch: config copy and working directory ------------------------------
$scratch = Join-Path $env:TEMP 'doomxr_compile_check'
New-Item -ItemType Directory -Force $scratch | Out-Null
$cfg = Join-Path $scratch 'doomxr_check.ini'
if (Test-Path $ini) { Copy-Item $ini $cfg -Force } else { Set-Content $cfg '' }
# vr_mode 0 in the SCRATCH copy only: the owner's ini asks for OpenXR (vr_mode 15), and the engine probes the
# OpenXR runtime at startup even under -norun (found by selacovr-4b, 2026-09-14) -- a check must never wake a
# headset. The owner's own ini is never written.
$cfgText = [IO.File]::ReadAllText($cfg)
if ($cfgText -match '(?m)^vr_mode=') { $cfgText = $cfgText -replace '(?m)^vr_mode=.*$', 'vr_mode=0' }
else { $cfgText = $cfgText.TrimEnd() + "`r`n[GlobalSettings]`r`nvr_mode=0`r`n" }
[IO.File]::WriteAllText($cfg, $cfgText, (New-Object System.Text.UTF8Encoding($false)))
$out = Join-Path $scratch ("check_{0}.txt" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

# What must not change: the owner's ini and the logs beside the exe.
$guard = @($ini, (Join-Path $eng 'log-debug.txt'), (Join-Path $eng 'doomxr-log.txt')) | Where-Object { Test-Path $_ }
$before = @{}; foreach ($g in $guard) { $before[$g] = (Get-Item $g).LastWriteTimeUtc }

# ---- run ----------------------------------------------------------------------
$argList = @('-iwad', $iwad, '-config', $cfg, '-file') + $Files + @('-norun', '-nosound', '-nomusic', '-stdout')
Write-Output "compile check: $($Files.Count) mod file(s), hidden, scratch $scratch"
$Files | ForEach-Object { Write-Output "  $_" }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $scratch `
     -RedirectStandardOutput $out -WindowStyle Hidden -PassThru

# A FATAL COMPILE DOES NOT EXIT. The engine prints the script error and then sits on
# a (hidden) "Execution could not continue" dialog until something kills it -- the
# first failing run took 165 s to come back. So watch the output as it is written:
# the moment a script error line appears, the answer is known, and the process is
# killed rather than waited out. A pass still exits on its own in a few seconds.
# pk3:zscript too: a SEMANTIC compile error ("Attempt to redefine", "does not represent a class
# type") prints only its location line, never "Script error", and waited out the whole timeout.
$failPattern = 'Script error|Execution could not continue|VM execution aborted|pk3:zscript'
$killedOnError = $false
while (-not $p.HasExited) {
    if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) {
        $p.Kill()
        throw "TIMED OUT after $TimeoutSec s -- NOT a pass. Output: $out"
    }
    if ((Test-Path $out) -and (Select-String -Path $out -Pattern $failPattern -Quiet)) {
        Start-Sleep -Milliseconds 500      # let the rest of the error block reach the file
        if (-not $p.HasExited) { $p.Kill(); $killedOnError = $true }
        break
    }
    Start-Sleep -Milliseconds 250
}
$p.WaitForExit(5000) | Out-Null
$sw.Stop()
if ($killedOnError) { Write-Output "(stopped the engine at its script error instead of waiting on its dialog)" }

# ---- judge ----------------------------------------------------------------------
$errs = @(Select-String -Path $out -Pattern 'Script error|pk3:zscript|\.zs"?\s*G?line \d+|Execution could not continue|Unknown identifier|VM execution aborted' |
          ForEach-Object { $_.Line.Trim() })
$ok = Select-String -Path $out -Pattern 'script parsing took [0-9.]+ ms' | Select-Object -First 1

foreach ($g in $guard) {
    if ((Get-Item $g).LastWriteTimeUtc -ne $before[$g]) { Write-Warning "GUARD: $g CHANGED during the check -- report this" }
}

if ($errs.Count -gt 0) {
    Write-Output "COMPILE FAILED ($([int]$sw.Elapsed.TotalSeconds) s) -- output kept at $out"
    $errs | Select-Object -First 40 | ForEach-Object { Write-Output "  $_" }
    exit 1
}
if (-not $ok) {
    Write-Output "NO PASS: no 'script parsing took' line ($([int]$sw.Elapsed.TotalSeconds) s, exit $($p.ExitCode)) -- output kept at $out"
    Get-Content $out -Tail 25 | ForEach-Object { Write-Output "  $_" }
    exit 2
}
Write-Output "COMPILED -- $($ok.Matches[0].Value), $([int]$sw.Elapsed.TotalSeconds) s, exe $((Get-Item $exe).LastWriteTime.ToString('MM-dd HH:mm'))"
Remove-Item $out -Force
exit 0
