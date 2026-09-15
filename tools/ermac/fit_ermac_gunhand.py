"""Part B.2: Ermac's GUN hand (hand.md3, 211 frames) as more frames of our 22-joint hand.

hand.md3 is hand2.md3's mesh MIRRORED, with its vertices in another order (the UV sets are equal). So:
  1. a vertex map hand.md3 -> hand2 is recovered from the UVs, ties broken by position after mirroring
     hand.md3's open frame 0 onto hand2's open frame 150; checked by mapping the triangles across;
  2. each hand.md3 frame is mirrored (x -> -x), reordered into hand2's vertex order, and then goes through
     exactly fit_ermac_poses.py's steps (align_ermac.py's M / scale / R / t, palm taken out, per-joint
     Kabsch under the scale-aware chain);
  3. the frames are appended after hand_ermac_poses.iqm's 1494 and every frame is re-quantized again.

New frame number = 1494 + hand.md3 frame number. Frames 0..1493 are unchanged in meaning.
Writes hand_ermac_poses2.iqm and ermac_gunhand_index.json.

Credit: hand.md3 and hand2.md3 are Ermac's (iAmErmac), Doom: Force Unleashed / Rusted Legacy (MIT).
"""
import json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand, quat_to_mat

SRC_IQM = os.path.join(HERE, "hand_ermac_poses.iqm")
OUT_IQM = os.path.join(HERE, "hand_ermac_poses2.iqm")
HAND_DIR = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/"
MIN_VERTS = 6

# ---------------------------------------------------------------- 1. vertex map from the UVs
gun = MD3Model.load(HAND_DIR + "hand.md3").surfaces[0]
off = MD3Model.load(HAND_DIR + "hand2.md3").surfaces[0]
ua = np.round(np.array(gun.st), 4)
ub = np.round(np.array(off.st), 4)
nv = len(ua)
MIRROR = np.diag([-1.0, 1.0, 1.0])


def umeyama(A, B):
    ca, cb = A.mean(0), B.mean(0)
    X, Y = A - ca, B - cb
    U, S, Vt = np.linalg.svd(Y.T @ X)
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R_ = U @ D @ Vt
    s_ = (S * np.diag(D)).sum() / (X ** 2).sum()
    return s_, R_, cb - s_ * (R_ @ ca)


keys_b = {}
for i, k in enumerate(map(tuple, ub)):
    keys_b.setdefault(k, []).append(i)
perm = -np.ones(nv, dtype=int)
unique_a = []
for i, k in enumerate(map(tuple, ua)):
    cands = keys_b.get(k, [])
    if len(cands) == 1:
        perm[i] = cands[0]; unique_a.append(i)
print("vertex map: %d of %d vertices placed by a unique UV" % (len(unique_a), nv))

ga = np.array(gun.verts[0]) @ MIRROR.T
gb = np.array(off.verts[150])
ui = np.array(unique_a)
s0, R0, t0 = umeyama(ga[ui], gb[perm[ui]])
ga_on_b = (ga * s0) @ R0.T + t0
taken = set(perm[perm >= 0].tolist())
for i in np.where(perm < 0)[0]:
    cands = [c for c in keys_b[tuple(ua[i])] if c not in taken]
    c = min(cands, key=lambda c: np.linalg.norm(gb[c] - ga_on_b[i]))
    perm[i] = c; taken.add(c)
assert len(set(perm.tolist())) == nv, "vertex map is not one to one"
gap = np.linalg.norm(ga_on_b - gb[perm], axis=1)
print("open frames after the map: hand.md3 f0 (mirrored, similarity-fit) vs hand2 f150: mean %.3f, 95%% %.3f (scale %.4f)"
      % (gap.mean(), np.percentile(gap, 95), s0))

tri_a = {tuple(sorted(t)) for t in (perm[np.array(gun.triangles)]).tolist()}
tri_b = {tuple(sorted(t)) for t in np.array(off.triangles).tolist()}
print("triangles mapped across: %d of %d match" % (len(tri_a & tri_b), len(tri_b)))
assert len(tri_a & tri_b) >= 0.99 * len(tri_b), "the vertex map does not carry the triangles"

inv = np.empty(nv, dtype=int)
inv[perm] = np.arange(nv)          # hand2 vertex k is hand.md3 vertex inv[k]

# ---------------------------------------------------------------- 2. the fit, as fit_ermac_poses.py
al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t = al["M"], float(al["scale"]), al["R"], al["t"]
rest = al["verts"]
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
bidx, bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0
main_joint = bidx[:, 0]

hand = Hand(SRC_IQM)
nj = len(hand.names)
parents = hand.parents
bind_local = hand.base_local
bind_global = hand.base_global
palm = hand.index["HANDPALM_joint"]
palm_mask = main_joint == palm
rest_palm = rest[palm_mask]


def kabsch(A, B):
    ca, cb = A.mean(axis=0), B.mean(axis=0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(Vt.T @ U.T))
    Rm = Vt.T @ D @ U.T
    return Rm, cb - Rm @ ca


def mat_to_quat(m):
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(m[i, i] - m[j, j] - m[k, k] + 1.0) * 2
    q = np.zeros(4)
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return q


def local_mat(tt, q, s):
    return np.block([[quat_to_mat(q) * np.asarray(s)[None, :], np.asarray(tt)[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])


def skin(locs):
    G = hand.globals([local_mat(*l) for l in locs])
    sk_m = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    hp = np.c_[rest, np.ones(len(rest))]
    out = np.zeros((len(rest), 3))
    for k in range(4):
        out += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", sk_m[bidx[:, k]], hp)[:, :3]
    return out


def gun_frame_in_hand2_order(f):
    v = np.array(gun.verts[f]) @ MIRROR.T
    return v[inv]


new_locals, errors = [], []
nf_gun = MD3Model.load(HAND_DIR + "hand.md3").num_frames
for f in range(nf_gun):
    P = ((gun_frame_in_hand2_order(f) @ M.T) * scale) @ R.T + t
    Rp, tp = kabsch(P[palm_mask], rest_palm)
    Pn = P @ Rp.T + tp
    locs = []
    G_new = [None] * nj
    for j in range(nj):
        bt, bq, bs = bind_local[j]
        bt = np.array(bt, dtype=float); bs = np.array(bs, dtype=float)
        p = parents[j]
        sel = main_joint == j
        lq = np.array(bq, dtype=float)
        if j != palm and p >= 0 and sel.sum() >= MIN_VERTS:
            Rj, _ = kabsch(rest[sel], Pn[sel])
            target = Rj @ bind_global[j][:3, :3]
            Mloc = np.linalg.inv(G_new[p][:3, :3]) @ target @ np.diag(1.0 / bs)
            U, _, Vt = np.linalg.svd(Mloc)
            rot = U @ Vt
            if np.linalg.det(rot) < 0:
                U[:, -1] *= -1
                rot = U @ Vt
            lq = mat_to_quat(rot)
            if np.dot(lq, bq) < 0:
                lq = -lq
        lq = lq / np.linalg.norm(lq)
        L = np.eye(4); L[:3, :3] = quat_to_mat(lq) * bs[None, :]; L[:3, 3] = bt
        G_new[j] = L if p < 0 else G_new[p] @ L
        locs.append((bt, lq, bs))
    new_locals.append(locs)
    err = np.linalg.norm(skin(locs) - Pn, axis=1)
    errors.append((float(err.mean()), float(np.percentile(err, 95))))
print("fitted %d hand.md3 frames: median frame mean error %.3f, worst frame mean %.3f, worst 95%% %.3f"
      % (nf_gun, float(np.median([e[0] for e in errors])), max(e[0] for e in errors), max(e[1] for e in errors)))

# ---------------------------------------------------------------- 3. re-quantize and write
src = open(SRC_IQM, "rb").read()
H = list(struct.unpack_from("<27I", src, 16))
(ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj,
 njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = H
old_locals = hand.frame_local
all_locals = list(old_locals) + new_locals
NF = len(all_locals)
vals = np.zeros((NF, nj, 10))
for fi, locs in enumerate(all_locals):
    for j, (tt, q, s) in enumerate(locs):
        vals[fi, j, 0:3] = tt; vals[fi, j, 3:7] = q; vals[fi, j, 7:10] = s
lo = vals.min(axis=0); span = vals.max(axis=0) - lo
poses_b = bytearray(); masks = []
for j in range(nj):
    mask = 0; offs = []; scs = []
    for c in range(10):
        if span[j, c] > 1e-6:
            mask |= 1 << c; offs.append(lo[j, c]); scs.append(span[j, c] / 65535.0)
        else:
            offs.append(lo[j, c]); scs.append(0.0)
    masks.append(mask)
    poses_b += struct.pack("<iI10f10f", parents[j], mask, *offs, *scs)
frames = []
for fi in range(NF):
    for j in range(nj):
        for c in range(10):
            if masks[j] & (1 << c):
                frames.append(int(round((vals[fi, j, c] - lo[j, c]) / (span[j, c] / 65535.0))))
frames_arr = np.clip(np.array(frames), 0, 65535).astype("<u2")
nfch_new = sum(bin(mk).count("1") for mk in masks)
assert len(frames_arr) == NF * nfch_new

new_bounds = bytearray()
for locs in new_locals:
    sk = skin(locs)
    bmin, bmax = sk.min(axis=0), sk.max(axis=0)
    new_bounds += struct.pack("<8f", *bmin, *bmax, float(np.sqrt((sk[:, :2] ** 2).sum(1)).max()), float(np.sqrt((sk ** 2).sum(1)).max()))
anims = bytearray(src[oanim:oanim + nanim * 20])
name0, first0, num0, rate0, fl0 = struct.unpack_from("<IIIfI", anims, 0)
if first0 == 0 and num0 == nframe:
    struct.pack_into("<IIIfI", anims, 0, name0, first0, NF, rate0, fl0)

head_end = max(otext + ntext, omesh + nmesh * 24, ova + nva * 20, otri + ntri * 12)
for a in range(nva):
    typ, fl, fmt, size, o_ = struct.unpack_from("<5I", src, ova + a * 20)
    head_end = max(head_end, o_ + nvert * {1: 1, 7: 4}[fmt] * size)
out = bytearray(src[:head_end])
def place(blob):
    while len(out) % 4: out.append(0)
    o = len(out); out.extend(blob); return o
o_joint = place(src[ojoint:ojoint + njoint * 48])
o_pose = place(bytes(poses_b))
o_anim = place(bytes(anims))
o_frame = place(frames_arr.tobytes())
o_bounds = place(bytes(src[obounds:obounds + nframe * 32]) + bytes(new_bounds))
H[1] = len(out); H[14] = o_joint; H[16] = o_pose; H[18] = o_anim
H[19] = NF; H[20] = nfch_new; H[21] = o_frame; H[22] = o_bounds
struct.pack_into("<27I", out, 16, *H)
open(OUT_IQM, "wb").write(bytes(out))
print("wrote %s: %d frames (%d before + %d gun hand at %d..%d), %d channels, %d bytes"
      % (OUT_IQM, NF, nframe, nf_gun, nframe, NF - 1, nfch_new, len(out)))

chk = Hand(OUT_IQM)
worst = 0.0
for fi in (0, 3, 8, 1289, 1292, 1297, 1298 + 58, nframe - 1):
    for j in range(nj):
        qa = old_locals[fi][j][1] / np.linalg.norm(old_locals[fi][j][1])
        qb = chk.frame_local[fi][j][1] / np.linalg.norm(chk.frame_local[fi][j][1])
        worst = max(worst, np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qa, qb)))))))
print("earlier frames after re-quantizing: worst joint rotation change %.4f degrees" % worst)

index = {"base": nframe, "note": "frame = base + hand.md3 (gun hand) frame; mirrored to our hand, wrist taken out",
         "frames": [{"frame": nframe + f, "hand": f, "err_mean": round(e[0], 3), "err_95": round(e[1], 3)} for f, e in enumerate(errors)]}
json.dump(index, open(os.path.join(HERE, "ermac_gunhand_index.json"), "w"), indent=1)
bad = sorted(index["frames"], key=lambda x: -x["err_mean"])[:8]
print("worst fits: " + ", ".join("f%d %.2f" % (x["hand"], x["err_mean"]) for x in bad))
