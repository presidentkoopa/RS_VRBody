# models/slayer -- the Slayer arms (stage one of the VR body IK)

Not packed (build.ps1 packs model and texture extensions only). The record of where these came from.

| File | From |
|---|---|
| `slayer_arm_rt.iqm` | `_old/RS_VRIK/tools/armcut_2026-09-14/out/slayer_arm_rt_v2.iqm` |
| `slayer_arm_lf.iqm` | `.../out/slayer_arm_lf_v2.iqm` |
| `slayer_forearm_rt.iqm` | `.../out/slayer_forearm_rt_v2.iqm` |
| `slayer_forearm_lf.iqm` | `.../out/slayer_forearm_lf_v2.iqm` |
| `doomslayer_arms_legs_1011.png`, `_1012.png`, `doomslayer_torso_1006.png`, `doomslayer_skin_1021.png` | `_old/RS_VRIK/models/slayer/` (2048x2048, as exported by `export_slayer.py`) |
| `doomslayer_arms_legs_101{1,2}_{green,blue}.png` | `.../out/tint/`, made by `tint_gauntlet.py` from the two gauntlet textures |

- **Source rig:** `_old/RS_VRIK/models/slayer/slayer.iqm`, cut from the DOOM Eternal Slayer rip by `export_slayer.py` (291 joints, 28 meshes). The source FBX is gone.
- **The cut:** `cut_arms.py --side rt|lf [--upper arm_lower] --hand-weight-max 0.35`. It is byte-level: joints, bind pose, poses and bounds are copied unchanged, and only the arm meshes are kept. It drops the hand, the shoulder armour, and the triangles only partly skinned to the hand (the cuff slivers).
- **Mesh order** (MODELDEF `SurfaceSkin` indices):
  - arm_rt: 0 CastMesh47 (1011), 1 CastMesh63 (torso_1006), 2 CastMesh55 (torso_1006), 3 CastMesh27 (skin_1021), 4 CastMesh28 (skin_1021);
  - arm_lf: the same, with 0 CastMesh13 (1012);
  - forearm_rt: 0 CastMesh47, 1 CastMesh27; forearm_lf: 0 CastMesh13, 1 CastMesh27.
- **Material names** are `models/slayer/<file>.png`, which is why these live at this path (`LoadSkin` falls back to the material name as a full path).
- **File frame:** +X left, -Y forward, +Z up, map units, feet at origin. The engine swaps y and z on load (`models_iqm.cpp:359-361`).
- **Design and tests:** `Engine docs/VR_BODY_IK_RETURN_PLAN.md` sections 3b-3g and 4b; the engine side is in `IK_STAGE1_IMPL_NOTES.md`.
