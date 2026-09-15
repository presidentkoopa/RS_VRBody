# VR Body lane: queue

Close-up state, 2026-09-15 (owner: "we're done for today, so close up shop"). Items are in order.

## 1. Owner headset check: wrist HUD on the gun hand's wrist
- **What changed:** RS_VRPanels `07862f7` (E:/DOOMWork repo, local only, no remote). It is installed: `RS_VRPanels.zip` and `RS_VRBody\RS_VRPanels.pk3`, both md5 `ED3659BD5B66F01238A41A9C465651BB`, compiled on exe 09-15 05:10.
- **What to look at:**
  - The face sits on the back of the MAIN hand's wrist, with its top toward the fingers.
  - It is readable in a dark room (the frame is Bright).
  - The fit sliders move it live (Wrist HUD, then Fit, then "On the hand you see").
- **Saved ini:** it keeps the old spot. Set Wrist HUD "Where" to "Main hand, top of wrist".
- **If it draws nowhere:** the console should show one `[VRPANELS] RS_PanelWristA spawned ok` line; then `vr_place_debug 1`.

## 2. Owner headset check: which arm goes with which hand
- **The setting:** VR Body, then Arms, then "Arms reaching the wrong hands" (`rs_body_arm_swap`). The owner's ini has it off.
- **What the code says:** every IQM is mirrored at load (IK plan §3e). With the setting off, each Slayer arm is probably a mirror-image arm on its hand, which fits "2 right arms?" and "rotating like cylinders".
- **The check:** turn a palm up and down with the setting off, then on. Keep whichever looks like real arms.
- **Why it matters:** it decides which wrist-seam fit is used, and maybe the default.

## 3. Marine optional body (desk only, off by default, nothing installed)
**Done so far** (scratch `marine2/`; tools in `tools/marine/`; renders in `renders/marine/`):
- **Parts:** torso, shoulder pads and arms as IQM files.
- **Armour colours:** green and blue are made from the red plating. Red is the original texture, used as the low-health breath.
- **Hand skin:** the RS hand is retoned to the marine's skin.
- **Mockup:** rendered for the owner, who asked for the hand skin match and a merged wrist.
- **The wrist seam, measured with the engine's own placement:**
  - `marine_to_iqm.py --cut-map`: a clean cut on a plane, square to the forearm.
  - `wrist_socket.py`: one landing offset per arm. Result files: `wrist_socket.json` (anatomical pairing) and `wrist_socket_engine_pairing.json`.
  - `stub_reshape.py`: the RS stub widened toward the arm, capped at 0.7 on the bare arm and 0.35 on the gauntlet. It writes one hand IQM per hand and per pairing.
  - `wrist_flex.py`: the seam through bends.
- **Result, 1.29 map-unit cut, stub aimed about the LANDING POINT:**
  - Bare right forearm: seam gap mean 0.10-0.19 and max 0.33 through ±40° flex and ±20° deviation; worst poke-through 0.11, deep inside the forearm.
  - Gauntlet: a cuff about 0.4 wide; worst poke-through 0.04.
  - With the pivot at the hand origin (as today), bends pushed the stub out 0.3-0.4.
  - **No engine weld is needed.**

**Done since close-up (2026-09-15, afternoon):**
- **Both pairings finished at the 1.29 cut:** sockets, reshaped hands, and the bend tests with the stub aimed about the landing point.
- **`arm_rim_tuck.py`:** each arm's cut ring is laid onto the reshaped RS wrist it meets.
  - Bare right arm: seam gap 0.01-0.02 straight, and within about 0.2 through the bends.
  - Gauntlet: a cuff.
  - There is one arm file per pairing.
- **Seam close-ups:** sent to the owner (`renders/marine`). The seam geometry is closed.
- **The remaining visible band is shading, not colour:** the strip and the forearm skin match in Lab (L 69.8 vs 69.5), so a tone pass changed nothing. It is the short flare collar plus smooth vs faceted shading. Judge it in the headset first.
- **Assets installed** in `models/marine/` (gitignored; PROVENANCE.md tracked).
- **WIRED, OFF BY DEFAULT**; menu_lint `--prefix rs_` shows no new problems:
  - **body_parts.zs:** marine torso x3, arms x12 (side / pairing / colour), hand wears x4.
  - **MODELDEF:** the matching blocks, pivots on the marine shoulder joints.
  - **body_rig.zs:**
    - the registry;
    - `torsoStyle` "marine": follows the suit, never a vest;
    - `armStyle` "marine": pairing and colour;
    - `syncBreath`: the marine red;
    - `placeMarineTorso` / `marineShoulderSeat`: the shoulder line;
    - `placeArm`: marine joints, twistRef, measured socket per pairing, aim pivot at the landing point;
    - `dressWorldHands`: the marine hand wear when a marine arm reaches that hand.
  - **CVARINFO:** `rs_bp_marinetorso`, `rs_bp_marinearmright/left`, `rs_arm_sock_marine`.
  - **MENUDEF:** "Doom marine (classic)" torso, "Doom marine arm", fit sliders, marine hand socket nudges.

**Next:**
1. Scratch pack and compile check (a folder turn was asked for), then commit locally.
2. **Owner:** install it for a headset look? It is off by default and adds about 45 MB of assets to RS_VRBody.pk3.
3. **In the headset:** the seam band, the shoulder line (the marine anchors on the Quake torso's shoulder point), facing (yaw 0, like the Slayer arms), and arm size (calibrate writes only the Slayer arm scale today).

## 4. Section 8 agreement on `Engine docs/MODEL_JOINT_DRIVE_PLAN.md`
**Verdict: AGREE, with 8 conditions.** From a read-only review. Its order and generation claims were checked against `model_reach.cpp` 960-1075, where the order is ApplyPoses → chains → aims → cache → test channel, and `Changed()` bumps `generation`, which `ResolveChain` treats as a re-resolve and wipes the history.
1. **Order** in `ModelDrawPose_ApplyOpen`: draw poses → joint offsets (B) → joint drives (C) → reach chains → target-joint aims → test channel. A chain overwrites B/C on its root, mid and end joints; an aim turns on top of a drive.
2. **Generation:** B/C VALUE updates must not bump `FDrawPoseEntry::generation`; only adding or removing a joint does. Otherwise chains re-resolve every tic (smoothing wiped, log spam) and aims return no-solve.
3. **Registration:** the B/C setters create the actor's `FDrawPoseEntry`, and `HasContent()` counts live offsets and drives. `ApplyOpen` returns early for an actor with no entry.
4. **Composition:** `G' = D_anc · T · G_orig`, written parents first with `SetGlobal`.
   - A model-space T enters joint space as `S·T·S`: the offset is `SwapYZ(ofs)` and the quaternion `(x,y,z,w)` becomes `(-x,-z,-y,w)`.
   - S is a reflection; a plain component swap turns the part the wrong way. The same applies to C's axis and pivot.
5. **Once per frame:** `HandDrive_OwnerStep` keeps its own FrameCount stamp. A pose-cache miss re-runs the uncached branch, per eye.
6. **Scope:** B/C apply to world models only (RenderModel's window), and on decoupled or attachment actors only to the first model index evaluated. Never to the base-pose fallback or HUD psprite models.
7. **Reach targets:** a chain's target point stays on the target's model origin frame; it does not ride a driven joint.
8. **Piece E:**
   - It must use Option 2: `ApplyOpen` publishes the final palette per actor, model index and frame, after aims. Option 1 would seat a wrist panel on the unsolved arm.
   - A child drawn before its parent either solves on demand (like `AimOne`) or is documented as one frame late.
   - It is read only inside a render window, never from `GetBonePosition` / `GetBoneEulerAngles` / `GetObjectToWorldMatrix` (netplay).

## 5. Head-frame engine idea
The owner is undecided; nothing is built. It waits for the owner.

## 6. Flat-shading engine proposal (owner: "write the flat shading thing")
- **State:** researched, not written.
- **Design:** a per-model switch plumbed like SetEyeFade. The face normal comes from dFdx/dFdy of the pixel position, plus a studio key light, because sector light ignores normals.
- **Rule:** propose only; the build lane builds.

## 7. Arm "cylinder" rotation
- Bake the owner's `_align` / `_twist` slider values as defaults once reported.
- Item 2 may be the real cause.

## 8. Quake mutt wrist seam
Quake torso + Slayer arms + RS hands, the owner's other torso-up body. Apply the item 3 method: socket, cut if needed, stub reshape, aim pivot.

## Parked
- **Ermac glove refit:** `tools/ermac/refit_ermac_joints.py`. It is closer on his own poses but tangles in the RS poses. RS hands stay the default.
- **Legs:** rejected; try another model later.
- **Dark Ages marine:** later.

## Notes for the build lane
- **Unpushed RS_VRBody commits:** `49593c9` (marine tools) and this close-up commit.
- **`RS_VRBody/RS_VRPanels.pk3`:** it is TRACKED in RS_VRBody (GitHub remote) and was replaced by today's install. It is left uncommitted on purpose: the pk3 carries Ermac's watch-face art, and Ermac binaries stay off GitHub. Decide whether the pk3 should be untracked there.
