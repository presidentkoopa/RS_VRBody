"""Shared by the gun-hand scripts: Ermac's hand.md3 frames in our hand's space and back.

Same vertex map and steps as fit_ermac_gunhand.py (hand.md3 is hand2.md3 mirrored and reordered):
  to_ours(f)      -> (Pn, Rp, tp): the frame mirrored, reordered to hand2's vertex order, put through
                     align_ermac.py's M / scale / R / t, palm taken out (Pn = P @ Rp.T + tp)
  to_his(X, Rp, tp): points in our palm-at-rest space back into hand.md3's own space (the gun's space
                     in his MODELDEF blocks), i.e. the inverse of every step above
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
from md3 import MD3Model

HAND_DIR = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/"
MIRROR = np.diag([-1.0, 1.0, 1.0])

gun_md3 = MD3Model.load(HAND_DIR + "hand.md3")
gun = gun_md3.surfaces[0]
off = MD3Model.load(HAND_DIR + "hand2.md3").surfaces[0]

al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t = al["M"], float(al["scale"]), al["R"], al["t"]
rest, tris, uvs = al["verts"], al["tris"], al["uvs"]
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
bidx, bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0


def _umeyama(A, B):
    ca, cb = A.mean(0), B.mean(0)
    X, Y = A - ca, B - cb
    U, S, Vt = np.linalg.svd(Y.T @ X)
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R_ = U @ D @ Vt
    s_ = (S * np.diag(D)).sum() / (X ** 2).sum()
    return s_, R_, cb - s_ * (R_ @ ca)


def _vertex_map():
    ua = np.round(np.array(gun.st), 4); ub = np.round(np.array(off.st), 4)
    keys_b = {}
    for i, k in enumerate(map(tuple, ub)):
        keys_b.setdefault(k, []).append(i)
    perm = -np.ones(len(ua), dtype=int)
    uniq = []
    for i, k in enumerate(map(tuple, ua)):
        c = keys_b.get(k, [])
        if len(c) == 1:
            perm[i] = c[0]; uniq.append(i)
    ga = np.array(gun.verts[0]) @ MIRROR.T
    gb = np.array(off.verts[150])
    ui = np.array(uniq)
    s0, R0, t0 = _umeyama(ga[ui], gb[perm[ui]])
    gab = (ga * s0) @ R0.T + t0
    taken = set(perm[perm >= 0].tolist())
    for i in np.where(perm < 0)[0]:
        c = min((c for c in keys_b[tuple(ua[i])] if c not in taken), key=lambda c: np.linalg.norm(gb[c] - gab[i]))
        perm[i] = c; taken.add(c)
    inv = np.empty(len(ua), dtype=int); inv[perm] = np.arange(len(ua))
    return inv


INV = _vertex_map()
PALM_MASK = None


def kabsch(A, B):
    ca, cb = A.mean(axis=0), B.mean(axis=0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(Vt.T @ U.T))
    Rm = Vt.T @ D @ U.T
    return Rm, cb - Rm @ ca


def set_palm(palm_joint):
    global PALM_MASK
    PALM_MASK = bidx[:, 0] == palm_joint


def to_ours(f):
    P = (((np.array(gun.verts[f]) @ MIRROR.T)[INV] @ M.T) * scale) @ R.T + t
    Rp, tp = kabsch(P[PALM_MASK], rest[PALM_MASK])
    return P @ Rp.T + tp, Rp, tp


def to_his(X, Rp, tp):
    P = (X - tp) @ Rp                   # undo the palm fit
    V = (((P - t) @ R) / scale) @ M     # undo align (R, M orthogonal)
    return V @ MIRROR.T                 # undo the mirror (its own inverse)


def skin(hand, frame):
    nj = len(hand.names)
    G = hand.globals(hand.local_mats(hand.frame_local[frame]))
    sk = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    hp = np.c_[rest, np.ones(len(rest))]
    out = np.zeros((len(rest), 3))
    for k in range(4):
        out += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", sk[bidx[:, k]], hp)[:, :3]
    return out


def write_obj(path, verts, uv, faces):
    with open(path, "w") as fh:
        for v in verts:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for u in uv:
            fh.write("vt %.5f %.5f\n" % (u[0], 1.0 - u[1]))
        for a, b, c in faces:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
