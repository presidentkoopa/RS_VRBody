"""Every fitted gun-hand frame on our skeleton: dark = ours (frame 1494+f), orange = his hand.md3 frame f,
both palm at rest, side view. Same layout as pose_sheet.py. Writes out/ermac_gunhand_sheet.png."""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
sys.path.insert(0, HERE)
import gunhand_map as g
from hand_iqm import Hand

hand = Hand(os.path.join(HERE, "hand_ermac_poses2.iqm"))
g.set_palm(hand.index["HANDPALM_joint"])
index = json.load(open(os.path.join(HERE, "ermac_gunhand_index.json")))
errs = {e["hand"]: e["err_mean"] for e in index["frames"]}
base = index["base"]
nf = g.gun_md3.num_frames
cols = 15
rows = int(np.ceil(nf / cols))
fig, axes = plt.subplots(rows, cols, figsize=(cols * 1.6, rows * 1.8), dpi=90)
for f in range(rows * cols):
    ax = axes.flat[f]; ax.set_axis_off()
    if f >= nf:
        continue
    ours = g.skin(hand, base + f)
    his, _, _ = g.to_ours(f)
    for pts, col, alpha, z in ((his, "#e08a3c", 0.35, 1), (ours, "#23262e", 0.55, 2)):
        ax.add_collection(PolyCollection(pts[g.tris][:, :, [0, 2]], facecolors=col, edgecolors="none", alpha=alpha, zorder=z))
    ax.set_xlim(-16, 16); ax.set_ylim(-30, 14); ax.set_aspect("equal")
    ax.set_title("f%d  %.2f" % (f, errs[f]), fontsize=7, color=("#b00000" if errs[f] > 1.1 else "#303030"))
fig.suptitle("Ermac's GUN hand (hand.md3) on our 22-joint hand: dark = fitted (frame 1494+f), orange = his, wrist taken out. Number = mean fit error.", fontsize=10)
fig.tight_layout(rect=(0, 0, 1, 0.985))
fig.savefig(os.path.join(HERE, "out", "ermac_gunhand_sheet.png"))
print("wrote out/ermac_gunhand_sheet.png")
