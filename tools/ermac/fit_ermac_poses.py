"""Part B: Ermac's hand2.md3 poses as frames of our 22-joint hand.

For every hand2 frame f:
  1. his vertices go through the same mirror and fit as the rest frame (align_ermac.py's M, scale, R, t);
  2. the PALM is taken out: a rigid fit of HANDPALM's vertices from rest to frame f, inverted and applied
     to the whole frame, so only the finger shape is left (the controller places the wrist);
  3. each finger joint's rotation is the rigid fit (Kabsch) of the vertices whose main weight is that
     joint, rest -> frame f, turned into a LOCAL rotation under its parent. Translations stay the bind's,
     so bone lengths are ours. Joints with too few vertices keep their bind rotation.
Then every frame, ours and his, is decoded to floats and the frame block is re-quantized per channel
(IQM packs each channel as uint16 against a per-joint offset/scale), so new rotations always fit.
Old frames move by at most one step of each channel's new range.

New frame number = 1298 + hand2 frame number. Nothing here changes which frame any pose uses.

Writes hand_ermac_poses.iqm, ermac_pose_index.json (frame -> hand2 frame, fit error) and prints a summary.
"""
import json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand, quat_to_mat

SRC_IQM = os.path.join(HERE, "hand_ermac.iqm")
OUT_IQM = os.path.join(HERE, "hand_ermac_poses.iqm")
MIN_VERTS = 6

al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t = al["M"], float(al["scale"]), al["R"], al["t"]
rest = al["verts"]
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
bidx, bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0
main_joint = bidx[:, 0]

hand = Hand(SRC_IQM)          # our skeleton and frames, carried in the Ermac IQM
nj = len(hand.names)
parents = hand.parents
bind_local = hand.base_local                     # (t, q, s) per joint
bind_global = hand.base_global
palm = hand.index["HANDPALM_joint"]


def kabsch(A, B):
    """Rotation and translation taking points A onto B (rigid, no scale)."""
    ca, cb = A.mean(axis=0), B.mean(axis=0)
    H = (A - ca).T @ (B - cb)
    U, _, Vt = np.linalg.svd(H)
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


def map_frame(v):
    return ((np.asarray(v) @ M.T) * scale) @ R.T + t


m = MD3Model.load("E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3")
surf = m.surfaces[0]
nf_his = m.num_frames

# rest palm vertices, for taking the wrist out
palm_mask = main_joint == palm
rest_palm = rest[palm_mask]

new_locals = []
errors = []
for f in range(nf_his):
    P = map_frame(surf.verts[f])
    Rp, tp = kabsch(P[palm_mask], rest_palm)         # frame -> rest, on the palm
    Pn = P @ Rp.T + tp                                # the whole frame, palm put back at rest

    # THE JOINTS CARRY SCALE (INDEX_BASE's local offset is ~1064 against a parent scale of ~0.01, from
    # the source rig's export), so a joint's global 3x3 is rotation TIMES scale, not a rotation. The first
    # version took it as a rotation and every fitted pose came out ~27 units wrong. So the chain is
    # composed with the scale in it: the target global linear part is the fitted rotation applied to the
    # bind's (scale kept), and the local rotation is the nearest rotation to
    #   inverse(new parent linear) * target * inverse(this joint's own scale).
    # Local translations and scales stay the bind's, so bone lengths and proportions are ours.
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
            A = G_new[p][:3, :3]
            Mloc = np.linalg.inv(A) @ target @ np.diag(1.0 / bs)
            U, _, Vt = np.linalg.svd(Mloc)
            rot = U @ Vt
            if np.linalg.det(rot) < 0:
                U[:, -1] *= -1
                rot = U @ Vt
            lq = mat_to_quat(rot)
            if np.dot(lq, bq) < 0:
                lq = -lq
        lq = lq / np.linalg.norm(lq)
        L = np.eye(4)
        L[:3, :3] = quat_to_mat(lq) * bs[None, :]
        L[:3, 3] = bt
        G_new[j] = L if p < 0 else G_new[p] @ L
        locs.append((bt, lq, bs))
    new_locals.append(locs)

    # fit error: skin the rest mesh with these locals, compare to the palm-neutral frame
    G = hand.globals([np.block([[quat_to_mat(q) * s[None, :], tt[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]]) for tt, q, s in locs])
    skin = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    hp = np.c_[rest, np.ones(len(rest))]
    sk = np.zeros((len(rest), 3))
    for k in range(4):
        sk += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", skin[bidx[:, k]], hp)[:, :3]
    err = np.linalg.norm(sk - Pn, axis=1)
    errors.append((float(err.mean()), float(np.percentile(err, 95))))

print("fitted %d hand2 frames: mean vertex error %.3f (median of frames), worst frame mean %.3f, worst 95%% %.3f"
      % (nf_his, float(np.median([e[0] for e in errors])), max(e[0] for e in errors), max(e[1] for e in errors)))

# ---------------------------------------------------------------- re-quantize and write
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
lo = vals.min(axis=0); hi = vals.max(axis=0)
span = hi - lo
poses_b = bytearray()
masks = []
for j in range(nj):
    mask = 0; off = []; sc = []
    for c in range(10):
        if span[j, c] > 1e-6:
            mask |= 1 << c; off.append(lo[j, c]); sc.append(span[j, c] / 65535.0)
        else:
            off.append(lo[j, c]); sc.append(0.0)
    masks.append(mask)
    poses_b += struct.pack("<iI10f10f", parents[j], mask, *off, *sc)
frames = []
for fi in range(NF):
    for j in range(nj):
        for c in range(10):
            if masks[j] & (1 << c):
                frames.append(int(round((vals[fi, j, c] - lo[j, c]) / (span[j, c] / 65535.0))))
frames_arr = np.clip(np.array(frames), 0, 65535).astype("<u2")
nfch_new = sum(bin(mk).count("1") for mk in masks)
assert len(frames_arr) == NF * nfch_new

# bounds: old ones for the old frames; new ones from the skinned rest mesh
old_bounds = src[obounds:obounds + nframe * 32]
new_bounds = bytearray()
hp = np.c_[rest, np.ones(len(rest))]
for locs in new_locals:
    G = hand.globals([np.block([[quat_to_mat(q) * s[None, :], tt[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]]) for tt, q, s in locs])
    skin = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    sk = np.zeros((len(rest), 3))
    for k in range(4):
        sk += bwts[:, k:k + 1] * np.einsum("vij,vj->vi", skin[bidx[:, k]], hp)[:, :3]
    bmin, bmax = sk.min(axis=0), sk.max(axis=0)
    new_bounds += struct.pack("<8f", *bmin, *bmax, float(np.sqrt((sk[:, :2] ** 2).sum(1)).max()), float(np.sqrt((sk ** 2).sum(1)).max()))

anims = bytearray(src[oanim:oanim + nanim * 20])
name0, first0, num0, rate0, fl0 = struct.unpack_from("<IIIfI", anims, 0)
if first0 == 0 and num0 == nframe:
    struct.pack_into("<IIIfI", anims, 0, name0, first0, NF, rate0, fl0)

# layout: header | text .. triangles (copied as-is, same offsets) | joints | poses | anims | frames | bounds
head_end = max(otext + ntext, omesh + nmesh * 24, ova + nva * 20, otri + ntri * 12)
for a in range(nva):
    typ, fl, fmt, size, off = struct.unpack_from("<5I", src, ova + a * 20)
    elem = {1: 1, 7: 4}[fmt] * size
    head_end = max(head_end, off + nvert * elem)
out = bytearray(src[:head_end])
def place(blob):
    while len(out) % 4: out.append(0)
    off = len(out); out.extend(blob); return off
o_joint = place(src[ojoint:ojoint + njoint * 48])
o_pose = place(bytes(poses_b))
o_anim = place(bytes(anims))
o_frame = place(frames_arr.tobytes())
o_bounds = place(bytes(old_bounds) + bytes(new_bounds))
H[1] = len(out); H[13] = njoint; H[14] = o_joint; H[15] = nj; H[16] = o_pose; H[18] = o_anim
H[19] = NF; H[20] = nfch_new; H[21] = o_frame; H[22] = o_bounds
struct.pack_into("<27I", out, 16, *H)
open(OUT_IQM, "wb").write(bytes(out))
print("wrote %s: %d frames (%d ours + %d Ermac at %d..%d), %d channels, %d bytes"
      % (OUT_IQM, NF, nframe, nf_his, nframe, NF - 1, nfch_new, len(out)))

# re-read check: decode through the same reader, compare old frames before/after
chk = Hand(OUT_IQM)
worst = 0.0
for fi in (0, 3, 8, 1289, 1292, nframe - 1):
    for j in range(nj):
        a_, b_ = old_locals[fi][j], chk.frame_local[fi][j]
        qa, qb = a_[1] / np.linalg.norm(a_[1]), b_[1] / np.linalg.norm(b_[1])
        ang = np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qa, qb))))))
        worst = max(worst, ang)
print("old frames after re-quantizing: worst joint rotation change %.4f degrees" % worst)

index = {"base": nframe, "note": "frame = base + hand2 frame; wrist taken out (palm at rest)",
         "frames": [{"frame": nframe + f, "hand2": f, "err_mean": round(e[0], 3), "err_95": round(e[1], 3)} for f, e in enumerate(errors)]}
json.dump(index, open(os.path.join(HERE, "ermac_pose_index.json"), "w"), indent=1)
bad = sorted(index["frames"], key=lambda x: -x["err_mean"])[:8]
print("worst fits: " + ", ".join("f%d %.2f" % (x["hand2"], x["err_mean"]) for x in bad))
