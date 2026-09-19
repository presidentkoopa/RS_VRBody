# Build RS_VRBody.pk3
#
# Entry-by-entry .NET ZipArchive with forward slashes, and an ALLOWLIST rather
# than an exclusion list -- same reasons as the other packers here: Windows
# PowerShell's Compress-Archive writes backslashes that SLADE will not open, and
# a lump name ignores its extension, so a stray MODELDEF.bak in a pk3 root has
# silently shadowed the real one before.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = $PSScriptRoot
$out  = Join-Path $root 'RS_VRBody.pk3'

$rootLumps = @('ANIMDEFS.txt', 'CVARINFO.txt', 'KEYCONF', 'MAPINFO.txt', 'MENUDEF.txt', 'MODELDEF.txt', 'zscript.txt')

$files = @()
foreach ($l in $rootLumps) {
    $p = Join-Path $root $l
    if (-not (Test-Path $p)) { throw "missing required lump: $l" }
    $files += Get-Item $p
}
$files += Get-ChildItem -Path (Join-Path $root 'zscript') -Recurse -File -Filter *.zs
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.mdl
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.md3
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.iqm
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.obj
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.kvx
$files += Get-ChildItem -Path (Join-Path $root 'models')  -Recurse -File -Filter *.png
$files += Get-ChildItem -Path (Join-Path $root 'sprites') -Recurse -File -Filter *.png

if (Test-Path $out) { Remove-Item $out -Force }

$fs  = [System.IO.File]::Open($out, [System.IO.FileMode]::CreateNew)
$zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
foreach ($f in $files) {
    $rel = ($f.FullName.Substring($root.Length + 1)) -replace ([regex]::Escape([char]92)), '/'
    $e   = $zip.CreateEntry($rel, [System.IO.Compression.CompressionLevel]::Optimal)
    $st  = $e.Open()
    $b   = [System.IO.File]::ReadAllBytes($f.FullName)
    $st.Write($b, 0, $b.Length)
    $st.Dispose()
}
$zip.Dispose()
$fs.Dispose()

$check = [System.IO.Compression.ZipFile]::OpenRead($out)
$names = $check.Entries | ForEach-Object { $_.FullName }
$count = $names.Count
$bad   = $names | Where-Object { $_ -match ([regex]::Escape([char]92)) }
$check.Dispose()

if ($count -ne $files.Count) { throw "packed $count entries, expected $($files.Count)" }
if ($bad)                    { throw "backslash in entry name: $($bad -join ', ')" }
foreach ($l in $rootLumps) { if ($names -notcontains $l) { throw "verification failed: $l missing" } }
# Every frame letter QHND uses needs its own lump. The model replaces the
# sprite, but the LOOKUP is still (sprite, frame) -- a missing lump is a pose
# that silently draws nothing, which is how the hands vanished entirely.
$handFrames = @()   # BaseFrame keys on the class; no per-pose sprite lumps needed
# The Quake hands (hand.mdl, openhand.mdl) are out (owner, 2026-09-15). The WHOLE marine body
# (marine_whole.iqm + its 13 skins + the transparent one that hides your own head) is required;
# the part-rig marine pieces stay required while the part rig is still reachable from the menu.
foreach ($m in @('models/vrtorso.mdl','models/legholster.mdl','models/marine/doomslayer_legs_set3_skin_green.png','models/marine/doomslayer_torso_set3_skin_green.png','models/praetor/doomslayer_praetor_1003_green.png','models/praetor/doomslayer_praetor_1013_green.png','models/praetor/doomslayer_praetor_1003_blue.png','models/praetor/doomslayer_praetor_1003_red.png','models/praetor/praetor_body.iqm','models/praetor/praetor_hand_rt.iqm','models/praetor/praetor_hand_lf.iqm','models/praetor/doomslayer_praetor_1001.png','models/praetor/doomslayer_praetor_1013.png','models/praetor/doomslayer_praetor_1001_visor_solid.png','models/marine/marine_body.iqm','models/marine/marine_hand_rt.iqm','models/marine/marine_hand_lf.iqm','models/marine/invisible.png','models/marine/doomslayer_legs_set3_skin.png','models/marine/doomslayer_helmet_set3_skin.png','models/marine/doomslayer_helmet_visor_set3_hq_skin.png','models/marine/doomslayer_helmet_interior_set3_skin.png','models/marine/doomslayer_hair.png','models/marine/doomslayer_teeth.png','models/marine/doomslayer_eyes.png','models/marine/doomslayer_torso_set3_skin.png','models/marine/doomslayer_shoulders_set3_skin.png','models/marine/doomslayer_arm_left_set3_skin.png','models/marine/doomslayer_arm_right_set3_skin.png','models/marine/marine_torso.iqm','models/marine/marine_arm_rt_engine.iqm','models/marine/marine_arm_lf_engine.iqm','models/marine/marine_arm_rt_anatomical.iqm','models/marine/marine_arm_lf_anatomical.iqm','models/marine/hand_marine_main_engine.iqm','models/marine/hand_marine_off_engine.iqm','models/marine/hand_marine_main_anatomical.iqm','models/marine/hand_marine_off_anatomical.iqm','models/marine/hand_basecolor_marine.png','models/boot/Boot.md3','models/boot/Boot.png','sprites/TRSOA0.png','zscript/body_rig.zs','models/vest_green.kvx','models/vest_blue.kvx','models/vest_pal.png','models/vest_pal_red.png','models/slayer/slayer_arm_rt.iqm','models/slayer/slayer_arm_lf.iqm','models/slayer/slayer_forearm_rt.iqm','models/slayer/slayer_forearm_lf.iqm','models/slayer/doomslayer_arms_legs_1011.png','models/slayer/doomslayer_arms_legs_1012.png','models/slayer/doomslayer_torso_1006.png','models/slayer/doomslayer_skin_1021.png','models/helmet/helmet.obj','models/helmet/helmet.png','models/helmet/helmet_visor.obj','models/helmet/helmet_visor.png','models/helmet/helmet_interior.obj','models/helmet/helmet_interior.png') + $handFrames) {
    if ($names -notcontains $m) { throw "verification failed: $m missing" }
}

Write-Output "RS_VRBody.pk3  --  $count entries, verified"
Write-Output ("  size: {0:N0} bytes" -f (Get-Item $out).Length)
