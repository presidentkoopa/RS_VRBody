# models/marine: the Doom marine optional body (torso up)

Not in git (`.gitignore`: `models/marine/*.iqm`, `*.png`). This file records where they came from.

| File | From |
|---|---|
| `marine_torso.iqm` | the `torso` and `shoulders_protections` bodyparts of `Slayer_Classic_Skins.mdl` (Source engine, IDST v48), on its full 152-joint skeleton, bind pose |
| `marine_arm_rt.iqm`, `marine_arm_lf.iqm` | the `arms` bodypart's right and left arm materials, with the hands CUT on a plane 1.29 map units behind `bip_hand_*`, square to the forearm; crossing triangles are clipped |
| `doomslayer_torso_set3_skin_{green,blue,red}.png`, `doomslayer_shoulders_set3_skin_*`, `doomslayer_arm_{left,right}_set3_skin_*` | the `.vtf` skins (DXT5 2048x2048), decoded. `red` is the original; `green`/`blue` have only the red plating turned to the Quake torso skins' hue (skin, metal and buckles kept) |
| `doomslayer_head.png` | the neck skin, decoded |
| `hand_marine_{main,off}_{anatomical,engine}.iqm` | RS_WorldHands' `hand_left_poses.iqm` (same skeleton, all frames) with its wrist stub reshaped to the marine arm it meets, one per hand and per arm pairing (`rs_body_arm_swap` 1 = anatomical, 0 = engine) |
| `hand_basecolor_marine.png` | RS_WorldHands' `hand_basecolor.png`, skin tone moved to the marine arm's skin (Lab mean and spread, spread change capped at 1.3) |

**Source:** the owner's download, 2026-09-15: https://sketchfab.com/3d-models/doom-eternal-marine-9q2Vy1qVTYmbVYdxYXUbAMz3jnk4Rp41c1e19z8EnsTy, saved at `C:\Users\Command\Downloads\doom-eternal-marine` (`source/DOOM Eternal Slayer [Skinned Classic Version (Ragdoll)].rar`). It is a Doom Eternal rip, under the same rule as the Slayer arms: never pushed.

**Tools** (`tools/marine/`):
- `marine_to_iqm.py`: MDL + VVD + VTX to IQM; `--cut-map` sets the plane cut.
- `vtf2png.py`
- `tint_marine.py`
- `retone_hand.py`
- `wrist_socket.py`: the landing offset per arm and pairing.
- `stub_reshape.py`
- `wrist_flex.py`: the seam through bends.

**Frame:** the Source file frame is +X left, -Y forward, +Z up, the same as the Slayer arm IQMs, scaled 0.872 (shoulder-matched to the Slayer rig). Joint translations are scaled with the vertices.

**Measured wrist seam** (bare right arm, 1.29 cut, stub aimed about the landing point):
- The gap averages 0.10-0.20 map units through ±40° flex and ±20° deviation.
- The worst poke-through is 0.12.
- The gauntlet side is a cuff about 0.4 wide.
