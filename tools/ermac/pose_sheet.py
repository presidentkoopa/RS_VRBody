"""Part B check: every fitted Ermac pose on our skeleton, one contact sheet, plus six posed OBJs for Blender.

Each cell: the glove skinned with frame 1298+f of hand_ermac_poses.iqm (dark), over his own hand2 frame f
with the wrist taken out the same way (faint orange). Side view (our x right, z up), all cells the same
scale, so a pose that fits badly shows as the two not lining up. The number is the mean fit error.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand

PICKS = {28: "pinch", 51: "claw", 58: "fist", 87: "splay", 144: "point", 186: "flat"}

al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t, rest = al["M"], float(al["scale"]), al["R"], al["t"], al["verts"]
uvs, tris = al["uvs"], al["tris"]
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
bidx, bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0
index = json.load(open(os.path.join(HERE, "ermac_pose_index.json")))
errs = {e["hand2"]: e["err_mean"] for e in index["frames"]}

hand = Hand(os.path.join(HERE, "hand_ermac_poses.iqm"))
nj = len(hand.names)
base = index["base"]
palm = hand.index["HANDPALM_joint"]
palm_mask = bidx[:, 0] == palm

m = MD3Model.load("E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3")
surf = m.surfaces[0]


def kabsch(A, B):
    ca, cb = A.mean(axis=0), B.mean(axis=0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(Vt.T @ U.T))
    Rm = Vt.T @ D @ U.T
    return Rm, cb - Rm @ ca


def skinned(frame):
    G = hand.globals(hand.local_mats(hand.frame_local[frame]))
    sk = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    hp = np.c_[rest, np.ones(len(rest))]
    out = np.zeros((len(rest), 3))
    for k in range(4):
        out += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", sk[bidx[:, k]], hp)[:, :3]
    return out


def his_neutral(f):
    P = ((np.array(surf.verts[f]) @ M.T) * scale) @ R.T + t
    Rp, tp = kabsch(P[palm_mask], rest[palm_mask])
    return P @ Rp.T + tp


nf = m.num_frames
cols = 14
rows = int(np.ceil(nf / cols))
fig, axes = plt.subplots(rows, cols, figsize=(cols * 1.6, rows * 1.8), dpi=90)
lim_x = (-16, 16); lim_z = (-30, 14)
for f in range(rows * cols):
    ax = axes.flat[f]
    ax.set_axis_off()
    if f >= nf:
        continue
    ours = skinned(base + f)
    his = his_neutral(f)
    for pts, col, alpha, z in ((his, "#e08a3c", 0.35, 1), (ours, "#23262e", 0.55, 2)):
        poly = pts[tris][:, :, [0, 2]]
        ax.add_collection(PolyCollection(poly, facecolors=col, edgecolors="none", alpha=alpha, zorder=z))
    ax.set_xlim(*lim_x); ax.set_ylim(*lim_z); ax.set_aspect("equal")
    ax.set_title("f%d  %.2f" % (f, errs[f]), fontsize=7, color=("#b00000" if errs[f] > 0.85 else "#303030"))
fig.suptitle("Ermac hand2 poses on our 22-joint hand: dark = fitted (frame 1298+f), orange = his original, wrist taken out. Number = mean fit error.", fontsize=10)
fig.tight_layout(rect=(0, 0, 1, 0.985))
sheet = os.path.join(HERE, "out", "ermac_pose_sheet.png")
fig.savefig(sheet)
print("wrote", sheet)

OUT = os.path.join(HERE, "out").replace("\\", "/")
for f, tag in PICKS.items():
    ours = skinned(base + f)
    obj = os.path.join(HERE, "ermac_fit_%s.obj" % tag)
    with open(obj, "w") as fh:
        for v in ours:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for uv in uvs:
            fh.write("vt %.5f %.5f\n" % (uv[0], 1.0 - uv[1]))
        for a, b, c in tris:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
    sc = {"objs": [{"path": obj.replace("\\", "/"), "texture": "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand_HD.png"}],
          "shots": [{"file": OUT + "/fit_%s.png" % tag, "cam": [55.0, 45.0, 4.0], "look": [0.0, 0.0, -8.0], "lens": 50}]}
    json.dump(sc, open(os.path.join(HERE, "scene_fit_%s.json" % tag), "w"), indent=1)
print("posed OBJs and scenes for", ", ".join("f%d %s" % kv for kv in PICKS.items()))
