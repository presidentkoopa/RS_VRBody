# models/helmet -- the Doom marine helmet worn on the head

Not in git (`.gitignore`: `models/helmet/*.obj`, `*.png`). This file is the record of where they came from.

| File | From |
|---|---|
| `helmet.obj`, `helmet_visor.obj`, `helmet_interior.obj` | the `helmet` bodypart of `Slayer_Classic_Skins.mdl` (Source engine, IDST v48) |
| `helmet.png`, `helmet_visor.png` | `doomslayer_helmet_set3_skin.vtf`, `doomslayer_helmet_visor_set3_hq_skin.vtf` (DXT5 2048x2048), decoded and scaled to 1024 |
| `helmet_interior.png` | `doomslayer_helmet_interior_set3_skin.vtf` (16x16, black) |

- **Source:** the owner's download, 2026-09-15: https://sketchfab.com/3d-models/doom-eternal-marine-9q2Vy1qVTYmbVYdxYXUbAMz3jnk4Rp41c1e19z8EnsTy, saved at `C:\Users\Command\Downloads\doom-eternal-marine`, containing `source/DOOM Eternal Slayer [Skinned Classic Version (Ragdoll)].rar`. A Doom Eternal rip: same rule as the Slayer arms, never pushed.
- **Tools:** `tools/marine/source_mdl_to_obj.py` (MDL + VVD + VTX to OBJ per bodypart) and `tools/marine/vtf2png.py`.
- **Transform:**
  - Source file frame (+X left, -Y forward, +Z up) moved so the marine's eye midpoint (0, -4.87, 67.85) is the origin.
  - Scaled 0.872 (the marine shoulder-matched to the Slayer arm rig).
  - Written as OBJ x = forward (-Y), y = up (Z), z = right (-X). The engine's OBJ loader negates z, so this matches an MD3's (forward, up, left) model space.
- **Size:** shell 10.9 deep x 10.8 tall x 10.4 wide map units. The front is 3.0 ahead of the eye, and the shell is under 8 from the eye everywhere.
