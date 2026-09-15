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

$rootLumps = @('CVARINFO.txt', 'KEYCONF', 'MAPINFO.txt', 'MENUDEF.txt', 'MODELDEF.txt', 'zscript.txt')

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
foreach ($m in @('models/vrtorso.mdl','models/legholster.mdl','models/hand.mdl','models/openhand.mdl','models/boot/Boot.md3','models/boot/Boot.png','sprites/TRSOA0.png','zscript/body_rig.zs','models/vest_green.kvx','models/vest_blue.kvx','models/vest_pal.png','models/vest_pal_red.png','models/slayer/slayer_arm_rt.iqm','models/slayer/slayer_arm_lf.iqm','models/slayer/slayer_forearm_rt.iqm','models/slayer/slayer_forearm_lf.iqm','models/slayer/doomslayer_arms_legs_1011.png','models/slayer/doomslayer_arms_legs_1012.png','models/slayer/doomslayer_torso_1006.png','models/slayer/doomslayer_skin_1021.png','models/helmet/helmet.obj','models/helmet/helmet.png','models/helmet/helmet_visor.obj','models/helmet/helmet_visor.png','models/helmet/helmet_interior.obj','models/helmet/helmet_interior.png') + $handFrames) {
    if ($names -notcontains $m) { throw "verification failed: $m missing" }
}

Write-Output "RS_VRBody.pk3  --  $count entries, verified"
Write-Output ("  size: {0:N0} bytes" -f (Get-Item $out).Length)
