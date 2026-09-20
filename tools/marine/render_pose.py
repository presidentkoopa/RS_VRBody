"""Render a FINGER CURL and a SPINE LEAN at both sign choices, so the sign can be seen.

    python render_pose.py OUT_PREFIX [marine|praetor]

Writes OUT_PREFIX_fingers_neg.png / _pos.png and OUT_PREFIX_lean_neg.png / _pos.png.

WHY. rs_body_finger_sign and the two rs_body_lean_sign_* are sliders because a hinge AXIS
is geometry and can be measured, while the DIRECTION it turns is a convention that cannot
be seen from outside a headset. That reasoning is sound for shipping a switch, and it is a
poor excuse for never looking: which way a finger folds is decided entirely by the file,
and the file is here. A render costs a minute and saves the owner a round trip in VR.

Reuses render_wrist.py's loader, skinner and rasteriser -- same linear blend, same grey, no
Blender, no engine, and no Doom Eternal texel in the output.

THE AXES ARE THE ONES THE MOD USES, deliberately. If this picture disagrees with the
headset, one of the two is reading the rig wrong and that is worth knowing; if they agree,
the default shipped is the right one.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_wrist import load, globals_of, axis_angle, skin, render   # noqa: E402

# Mirrors body_rig.zs exactly: marine fingers hinge on local X, Praetor's on local Z, and
# the spine bends about local Y (marine) / local Z (praetor) for forward and back.
RIGS = {
    "marine": dict(
        path="E:/DOOMWork/RS_VRBody/models/marine/marine_whole.iqm",
        fingers=[("bip_%s_0_R" % f, "bip_%s_1_R" % f, "bip_%s_2_R" % f)
                 for f in ("index", "middle", "ring", "pinky", "thumb")],
        finger_axis=np.array([1.0, 0.0, 0.0]),
        hand="bip_hand_R", fore="bip_lowerArm_R",
        spine=["bip_spine_0", "bip_spine_1", "bip_spine_2"],
        lean_axis=np.array([0.0, 1.0, 0.0]),
    ),
    "praetor": dict(
        path="E:/DOOMWork/RS_VRBody/models/praetor/praetor_hand_rt.iqm",
        fingers=[("ValveBiped.Bip01_R_Finger%d" % n,
                  "ValveBiped.Bip01_R_Finger%d1" % n,
                  "ValveBiped.Bip01_R_Finger%d2" % n) for n in (1, 2, 3, 4, 0)],
        finger_axis=np.array([0.0, 0.0, 1.0]),
        hand="ValveBiped.Bip01_R_Hand", fore="ValveBiped.Bip01_R_Forearm",
        spine=None,           # his body is a different file; lean is rendered on the marine
        lean_axis=None,
    ),
}

FING_A = (65.0, 75.0, 55.0)      # knuckle, middle, tip -- the constants in body_rig.zs


def subtree(names, parents, roots):
    """Every joint at or under any of `roots`, by name."""
    idx = {n: i for i, n in enumerate(names)}
    want = {idx[r] for r in roots if r in idx}
    out = set()
    for i in range(len(names)):
        j = i
        while j >= 0:
            if j in want:
                out.add(i)
                break
            j = parents[j]
    return out


def pose_and_render(rig, which, kind, sign, out):
    P, N, T, names, parents, loc, BI, BW = load(rig["path"])
    if N is None:
        N = np.zeros_like(P)
    idx = {n: i for i, n in enumerate(names)}
    Gb = globals_of(parents, loc)
    loc2 = [m.copy() for m in loc]

    if kind == "fingers":
        for joints in rig["fingers"]:
            thumb = joints[0].endswith("_0_R") and "thumb" in joints[0] or joints[0].endswith("Finger0")
            scale = 0.6 if thumb else 1.0
            for j, ang in zip(joints, FING_A):
                if j in idx:
                    loc2[idx[j]] = loc2[idx[j]] @ axis_angle(rig["finger_axis"], sign * ang * scale)
        keep_roots = [rig["hand"], rig["fore"]]
        label = "%s fingers, sign %+d" % (which, sign)
    else:
        for j in rig["spine"]:
            if j in idx:
                loc2[idx[j]] = loc2[idx[j]] @ axis_angle(rig["lean_axis"], sign * 26.0 / 3.0)
        keep_roots = ["bip_pelvis"]
        label = "%s lean forward, sign %+d" % (which, sign)

    under = subtree(names, parents, keep_roots)
    keep = np.isin(BI, list(under)).any(1) & (BW.sum(1) > 0)
    Gp = globals_of(parents, loc2)
    Pp, Np = skin(P, N, BI, BW, Gb, Gp)

    # A LEAN IS INVISIBLE FROM THE FRONT. render() projects x across and z up with y as
    # depth, which is right for a hand and useless for a forward/back bend -- the first
    # attempt at this rendered a dead-straight marine twice and proved nothing. Turning
    # the posed vertices a quarter turn about the up axis puts the camera at his side,
    # where a lean is the whole picture.
    if kind == "lean":
        Pp = np.column_stack([Pp[:, 1], -Pp[:, 0], Pp[:, 2]])
        Np = np.column_stack([Np[:, 1], -Np[:, 0], Np[:, 2]])
    render(Pp, Np, T, keep, 460, 460, label, out)


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "pose"
    which = sys.argv[2] if len(sys.argv) > 2 else "marine"
    rig = RIGS[which]
    for sign, tag in ((-1, "neg"), (1, "pos")):
        pose_and_render(rig, which, "fingers", sign, "%s_fingers_%s.png" % (prefix, tag))
    if rig["spine"]:
        for sign, tag in ((-1, "neg"), (1, "pos")):
            pose_and_render(rig, which, "lean", sign, "%s_lean_%s.png" % (prefix, tag))


main()
