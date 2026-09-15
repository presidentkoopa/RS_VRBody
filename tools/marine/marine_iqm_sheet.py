"""Check sheet for marine_to_iqm.py's output: torso + both cut arms in bind pose, CPU painter's renders (no GPU).

Views: front (from -y, forward), side (from -x, the right side), and a close-up of each wrist from the side of its
arm. The wrist joint (bip_hand_*) is a red dot, the elbow (bip_lowerArm_*) a blue one, so the cut can be judged
against the joints. Writes iqm/marine_iqm_sheet.png.
"""
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "iqm")
parts = [("torso", Hand(os.path.join(D, "marine_torso.iqm")), (0.55, 0.62, 0.45)),
         ("arm_rt", Hand(os.path.join(D, "marine_arm_rt.iqm")), (0.75, 0.55, 0.4)),
         ("arm_lf", Hand(os.path.join(D, "marine_arm_lf.iqm")), (0.45, 0.55, 0.78))]
J = parts[1][1]
def jpos(name):
    return J.base_global[J.index[name]][:3, 3]


def draw(ax, view, items, lim=None, dots=()):
    # view: (screen x axis, screen y axis, depth axis pointing TOWARD the camera)
    ex, ey, ez = (np.array(a, float) for a in view)
    polys, cols, depth = [], [], []
    L = ez * 0.8 + ey * 0.4 + ex * 0.2; L /= np.linalg.norm(L)
    for _, h, c in items:
        v = h.pos; t = h.tris.astype(int)
        a, b, cc = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
        fn = np.cross(b - a, cc - a); fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
        sh = 0.3 + 0.7 * np.abs(fn @ L)
        sx, sy, sz = v @ ex, v @ ey, v @ ez
        polys.append(np.stack([np.stack([sx[t[:, k]], sy[t[:, k]]], 1) for k in range(3)], 1))
        cols.append(np.clip(np.outer(sh, c), 0, 1)); depth.append(sz[t].mean(1))
    P, C, Z = np.concatenate(polys), np.concatenate(cols), np.concatenate(depth)
    o = np.argsort(Z)
    ax.add_collection(PolyCollection(P[o], facecolors=C[o], edgecolors="none"))
    for p, col in dots:
        ax.plot([p @ ex], [p @ ey], "o", color=col, ms=5, zorder=10)
    allv = np.concatenate([h.pos for _, h, _ in items])
    if lim is None:
        sx, sy = allv @ ex, allv @ ey
        lim = (sx.min() - 1, sx.max() + 1, sy.min() - 1, sy.max() + 1)
    ax.set_xlim(lim[0], lim[1]); ax.set_ylim(lim[2], lim[3])
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
NX, NY = (-1, 0, 0), (0, -1, 0)
joints = [(jpos("bip_hand_R"), "red"), (jpos("bip_hand_L"), "red"), (jpos("bip_lowerArm_R"), "blue"), (jpos("bip_lowerArm_L"), "blue")]
fig, axs = plt.subplots(2, 3, figsize=(15, 11))
# front: camera at -y looking +y; the marine's right (-x) shows on screen LEFT? viewer faces him, so his right is screen left.
draw(axs[0, 0], (X, Z, NY), parts, dots=joints); axs[0, 0].set_title("front (his right arm on screen left)")
draw(axs[0, 1], (Y, Z, NX), parts, dots=joints); axs[0, 1].set_title("right side (forward is screen left)")
draw(axs[0, 2], (X, Z, Y), parts, dots=joints); axs[0, 2].set_title("back")
for i, (nm, side, view) in enumerate([("arm_rt", "R", (Y, Z, NX)), ("arm_lf", "L", (NY, Z, X))]):
    w = jpos("bip_hand_" + side); s = 7.0
    lim = (w @ np.array(view[0], float) - s, w @ np.array(view[0], float) + s, w[2] - s, w[2] + s)
    draw(axs[1, i], view, [p for p in parts if p[0] == nm], lim=lim,
         dots=[(jpos("bip_hand_" + side), "red"), (jpos("bip_lowerArm_" + side), "blue")])
    axs[1, i].set_title("%s wrist close-up (red = bip_hand, blue = elbow)" % nm)
# arms only from above, to see both cut ends and any stray pieces
draw(axs[1, 2], (X, NY, Z), parts[1:], dots=joints); axs[1, 2].set_title("arms only, from above (forward is screen up)")
for (nm, h, _) in parts:
    print("%-7s verts %5d tris %5d  bounds %s .. %s" % (nm, len(h.pos), len(h.tris), h.pos.min(0).round(2), h.pos.max(0).round(2)))
print("bip_hand_R %s  bip_hand_L %s  lowerArm_R %s  lowerArm_L %s" % tuple(p.round(2) for p in (jpos("bip_hand_R"), jpos("bip_hand_L"), jpos("bip_lowerArm_R"), jpos("bip_lowerArm_L"))))
fig.tight_layout()
fig.savefig(os.path.join(D, "marine_iqm_sheet.png"), dpi=70)
print("sheet written")
