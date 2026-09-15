"""Why does fit_ermac_poses.py report ~27 units of error even on the rest frame (150)?
Takes frame 150 through every step and prints where the numbers stop being ~zero."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand, quat_to_mat, trs

al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t = al["M"], float(al["scale"]), al["R"], al["t"]
rest = al["verts"]
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
bidx, bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0

hand = Hand(os.path.join(HERE, "hand_ermac.iqm"))
nj = len(hand.names)
print("hand.pos vs rest: max %.5f" % np.abs(hand.pos - rest).max())

m = MD3Model.load("E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3")
P = ((np.array(m.surfaces[0].verts[150]) @ M.T) * scale) @ R.T + t
print("mapped frame 150 vs rest: max %.5f" % np.abs(P - rest).max())

# 1) skin the rest mesh with the BIND locals: must return the rest mesh
Gb = hand.globals([trs(*b) for b in hand.base_local])
print("globals from base_local vs base_global: max %.6f" % max(np.abs(Gb[j] - hand.base_global[j]).max() for j in range(nj)))
skin = np.array([Gb[j] @ hand.base_inv[j] for j in range(nj)])
print("skin matrices vs identity: max %.6f" % np.abs(skin - np.eye(4)[None]).max())
hp = np.c_[rest, np.ones(len(rest))]
sk = np.zeros((len(rest), 3))
for k in range(4):
    sk += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", skin[bidx[:, k]], hp)[:, :3]
print("bind-skinned rest vs rest: mean %.5f max %.5f" % (np.linalg.norm(sk - rest, axis=1).mean(), np.linalg.norm(sk - rest, axis=1).max()))
print("weight sums: min %.4f max %.4f" % (bwts.sum(axis=1).min(), bwts.sum(axis=1).max()))

# 2) the way fit_ermac_poses.py builds a local matrix
def loc_mat(tt, q, s):
    return np.block([[quat_to_mat(q) * np.asarray(s)[None, :], np.asarray(tt)[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
Gf = hand.globals([loc_mat(*b) for b in hand.base_local])
print("np.block local vs trs local, globals: max %.6f" % max(np.abs(Gf[j] - Gb[j]).max() for j in range(nj)))
print("sample block matrix shape", loc_mat(*hand.base_local[1]).shape)
print(loc_mat(*hand.base_local[2]).round(3))
print(trs(*hand.base_local[2]).round(3))
