"""Part C: OUR JOINTS MOVED INTO ERMAC'S KNUCKLES, his skin re-weighted to bend where his hand bends.

Why (owner, 2026-09-15, in the headset): "bending odd angles, inflated fingers". The glove was fitted onto our
22-joint hand in one piece (align_ermac.py) and took our weights from the nearest point of our mesh
(build_ermac_iqm.py), so its creases sat wherever OUR hand's creases were, not where his are.

His hands are MD3 vertex animation -- no bones -- but the animation itself says where each knuckle is:

  1. PARTS. Every hand2.md3 frame and every hand.md3 (gun hand) frame is brought into our palm-at-rest space
     exactly as fit_ermac_poses.py / fit_ermac_gunhand.py did. Each vertex starts on its transferred main
     joint; each joint's rigid motion per frame is fitted (Kabsch) to its vertices; each vertex is then
     re-assigned to whichever of {its joint, the parent, the children} moves it best across ALL frames.
     Repeated, the parts settle on his real rigid pieces.
  2. KNUCKLES. A knuckle is the one point that the parent part and the child part carry to the same place in
     every frame: least squares on (R_rel - I) c = -t_rel over all frames. A hinge leaves the point free along
     its own axis, so that direction is held to the centre of the ring where the two parts meet.
  3. WEIGHTS. Each vertex takes the blend of one or two neighbouring joints that best reproduces its own
     trajectory through all his frames (closed form per joint pair) -- his creases, measured.
  4. SKELETON. New bind: every joint at its knuckle; orientations and scales unchanged (the chain carries
     scale 0.01, see fit_ermac_poses.py), so every RS pose frame keeps its joint turns and only the pivots
     move. Root and palm stay put, so the controller seat and every gun seat are unaffected.
  5. FRAMES. RS frames (0..1297): local rotations and scales kept, local translations = new bind + whatever
     the frame itself moved. Ermac frames (1298.., 1494..): refitted on the new skeleton from step 1's motions.
  6. SLIM. Each finger part's vertices are pulled toward its bone axis by (RS finger radius / glove finger
     radius) for that part, measured on both meshes, clamped 0.6..1.0, blended by the new weights.

Writes (next to this script, refit/):
  hand_ermac_refit.iqm        steps 1-5
  hand_ermac_refit_slim.iqm   steps 1-6
  refit_report.txt, refit_sheet_side.png, refit_sheet_palm.png
Nothing is installed.

Credit: hand.md3 / hand2.md3 mesh and skin are Ermac's (iAmErmac), Rusted Legacy (MIT).
"""
import json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
sys.path.insert(0, HERE)
from md3 import MD3Model
from hand_iqm import Hand, quat_to_mat
import gunhand_map as gm

OUT = os.path.join(HERE, "refit")
os.makedirs(OUT, exist_ok=True)
SRC_IQM = os.path.join(HERE, "hand_ermac_poses2.iqm")          # skeleton + all 1705 frames (glove's)
RS_IQM = os.path.join(HERE, "hand_left_poses.iqm")              # RS mesh, same skeleton + frames
HAND2 = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3"
BASE_H2, BASE_GUN = 1298, 1494
MIN_VERTS = 6
report = []
def say(s):
    print(s); report.append(s)

al = np.load(os.path.join(HERE, "ermac_aligned.npz"))
M, scale, R, t = al["M"], float(al["scale"]), al["R"], al["t"]
rest, uvs, tris = al["verts"], al["uvs"], al["tris"].astype(np.int64)
wt = np.load(os.path.join(HERE, "ermac_weights.npz"))
old_bidx, old_bwts = wt["bidx"].astype(int), wt["bwts"].astype(np.float64) / 255.0
V = len(rest)

hand = Hand(SRC_IQM)
nj, parents, names = len(hand.names), hand.parents, hand.names
children = {j: [k for k in range(nj) if parents[k] == j] for j in range(nj)}
ROOT, PALM = hand.index["Root_joint"], hand.index["HANDPALM_joint"]
FIXED = {ROOT, PALM}
bindG = hand.base_global


def kabsch(A, B):
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(Vt.T @ U.T))
    Rm = Vt.T @ D @ U.T
    return Rm, cb - Rm @ ca


def mat_to_quat(m):
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]])); j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(m[i, i] - m[j, j] - m[k, k] + 1.0) * 2
    q = np.zeros(4); q[i] = 0.25 * s; q[j] = (m[j, i] + m[i, j]) / s; q[k] = (m[k, i] + m[i, k]) / s; q[3] = (m[k, j] - m[j, k]) / s
    return q


def local_mat(tt, q, s):
    L = np.eye(4); L[:3, :3] = quat_to_mat(q) * np.asarray(s)[None, :]; L[:3, 3] = tt
    return L


# ---------------------------------------------------------------- his frames, palm at rest
h2 = MD3Model.load(HAND2).surfaces[0]
palm_mask0 = old_bidx[:, 0] == PALM
FR, FR_TAG = [], []
for f in range(len(h2.verts)):
    P = ((np.array(h2.verts[f]) @ M.T) * scale) @ R.T + t
    Rp, tp = kabsch(P[palm_mask0], rest[palm_mask0])
    FR.append(P @ Rp.T + tp); FR_TAG.append(("h2", f))
n_h2 = len(FR)
n_gun = gm.gun_md3.num_frames
gm.set_palm(PALM)
for f in range(n_gun):
    FR.append(gm.to_ours(f)[0]); FR_TAG.append(("gun", f))
FR = np.array(FR)                                  # F x V x 3
F = len(FR)
say("his frames in our space: %d hand2 + %d gun hand = %d" % (n_h2, n_gun, F))


# ---------------------------------------------------------------- 1. parts from motion
def part_motions(label):
    Rs = np.tile(np.eye(3), (nj, F, 1, 1)); Ts = np.zeros((nj, F, 3))
    for j in range(nj):
        sel = label == j
        if j == ROOT:
            continue
        if sel.sum() < MIN_VERTS:
            p = parents[j]; Rs[j] = Rs[p]; Ts[j] = Ts[p]; continue
        for f in range(F):
            Rs[j, f], Ts[j, f] = kabsch(rest[sel], FR[f, sel])
    return Rs, Ts


def residual(Rs, Ts, j, idx):
    pred = np.einsum("fab,vb->fva", Rs[j], rest[idx]) + Ts[j][:, None, :]
    return ((pred - FR[:, idx]) ** 2).sum(axis=(0, 2))


# A vertex changes part only when another part moves it CLEARLY better (MARGIN). Where his animation
# keeps two pieces rigid together (a fingertip that never bends on its own), the motion cannot tell them
# apart, and a bare "best" would empty the tip part -- leaving our tip joint nothing to bend in RS poses.
MARGIN = 0.8
label = old_bidx[:, 0].copy()
for it in range(5):
    Rs, Ts = part_motions(label)
    own = np.array([residual(Rs, Ts, label[v], [v])[0] for v in range(V)])
    best = own * MARGIN; new = label.copy()
    for j in range(nj):
        cand_of = [v for v in range(V) if j != label[v] and (j == parents[label[v]] or label[v] == parents[j])]
        if j == ROOT or not cand_of:
            continue
        idx = np.array(cand_of)
        r = residual(Rs, Ts, j, idx)
        better = r < best[idx]
        best[idx[better]] = r[better]; new[idx[better]] = j
    best = np.where(new == label, own, best)         # each vertex's error in the part it ends up in
    moved = int((new != label).sum()); label = new
    say("parts pass %d: %d vertices changed part, mean trajectory error %.3f" % (it, moved, float(np.sqrt(best / F).mean())))
    if moved == 0:
        break
Rs, Ts = part_motions(label)
counts = np.bincount(label, minlength=nj)
say("vertices per part: " + ", ".join("%s %d" % (names[j].replace("_joint", ""), counts[j]) for j in range(nj) if counts[j]))

# ---------------------------------------------------------------- 2. knuckles
newpos = {j: bindG[j][:3, 3].copy() for j in range(nj)}
for j in range(nj):                                 # parents before children (IQM order)
    p = parents[j]
    if j in FIXED or p < 0:
        continue
    if counts[j] < MIN_VERTS:
        newpos[j] = newpos[p] + (bindG[j][:3, 3] - bindG[p][:3, 3]) if p not in FIXED else bindG[j][:3, 3].copy()
        # a part-less joint rides its parent's shift
        newpos[j] = bindG[j][:3, 3] + (newpos[p] - bindG[p][:3, 3])
        continue
    A = np.einsum("fba,fbc->fac", Rs[p], Rs[j]) - np.eye(3)       # R_p^T R_j - I
    b = -np.einsum("fba,fb->fa", Rs[p], Ts[j] - Ts[p])             # -(R_p^T (t_j - t_p))
    # ring centre where the two parts meet: part-j vertices nearest part p
    pj, pp = rest[label == j], rest[label == p] if (label == p).sum() >= 3 else rest[label == j]
    d = np.sqrt(((pj[:, None, :] - pp[None, :, :]) ** 2).sum(2)).min(1)
    ring = pj[d <= np.percentile(d, 20)].mean(0)
    lam = 0.02 * F
    AA = np.vstack([A.reshape(-1, 3), np.sqrt(lam) * np.eye(3)])
    bb = np.concatenate([b.reshape(-1), np.sqrt(lam) * ring])
    c, *_ = np.linalg.lstsq(AA, bb, rcond=None)
    moved_err = np.linalg.norm(np.einsum("fab,b->fa", A, c) - b, axis=1)
    newpos[j] = c
    say("knuckle %-22s moved %.2f (ring %.2f from old) -- parts disagree there by mean %.3f"
        % (names[j], np.linalg.norm(c - bindG[j][:3, 3]), np.linalg.norm(ring - bindG[j][:3, 3]), moved_err.mean()))

# ---------------------------------------------------------------- 3. weights from trajectories
def traj(j, idx):
    return np.einsum("fab,vb->fva", Rs[j], rest[idx]) + Ts[j][:, None, :]

bidx = np.zeros((V, 4), int); bw = np.zeros((V, 4))
fit_err = np.zeros(V)
for v in range(V):
    j = label[v]
    X = FR[:, v]
    Tj = traj(j, [v])[:, 0]
    best = (((Tj - X) ** 2).sum(), j, j, 1.0)
    for k in [parents[j]] + children[j]:
        if k < 0:
            continue
        Tk = traj(k, [v])[:, 0]
        a, bvec = Tj - Tk, X - Tk
        den = (a * a).sum()
        w = float(np.clip((a * bvec).sum() / den, 0.0, 1.0)) if den > 1e-12 else 1.0
        e = (((w * Tj + (1 - w) * Tk) - X) ** 2).sum()
        if e < best[0]:
            best = (e, j, k, w)
    e, j0, k0, w = best
    bidx[v, 0], bw[v, 0] = j0, w
    if k0 != j0:
        bidx[v, 1], bw[v, 1] = k0, 1.0 - w
    fit_err[v] = np.sqrt(e / F)
say("weights: %d vertices blend two joints; per-vertex trajectory error mean %.3f, 95%% %.3f"
    % (int((bw[:, 1] > 0.02).sum()), fit_err.mean(), np.percentile(fit_err, 95)))

# ---------------------------------------------------------------- 4. skeleton
newG = [None] * nj; new_bind_local = []
for j in range(nj):
    bt, bq, bs = hand.base_local[j]
    p = parents[j]
    if p < 0:
        nt = np.array(bt)
    else:
        Pg = newG[p]
        nt = np.linalg.inv(Pg[:3, :3]) @ (newpos[j] - Pg[:3, 3])
    new_bind_local.append((nt, np.array(bq), np.array(bs)))
    L = local_mat(nt, bq, bs)
    newG[j] = L if p < 0 else newG[p] @ L
    assert np.allclose(newG[j][:3, :3], bindG[j][:3, :3], atol=1e-6)
new_inv = [np.linalg.inv(g) for g in newG]

# ---------------------------------------------------------------- 5. frames
def refit_frame(fi):
    locs = []; G = [None] * nj
    for j in range(nj):
        nt, bq, bs = new_bind_local[j]
        p = parents[j]
        lq = np.array(bq, float)
        if j not in FIXED and p >= 0 and counts[j] >= MIN_VERTS:
            target = Rs[j, fi] @ newG[j][:3, :3]
            Ml = np.linalg.inv(G[p][:3, :3]) @ target @ np.diag(1.0 / bs)
            U, _, Vt = np.linalg.svd(Ml); rot = U @ Vt
            if np.linalg.det(rot) < 0:
                U[:, -1] *= -1; rot = U @ Vt
            lq = mat_to_quat(rot)
            if np.dot(lq, bq) < 0: lq = -lq
        elif j not in FIXED and p >= 0:
            lq = np.array(bq, float)                          # part-less: rides the parent
        lq /= np.linalg.norm(lq)
        L = local_mat(nt, lq, bs); G[j] = L if p < 0 else G[p] @ L
        locs.append((nt, lq, bs))
    return locs

all_locals = []
for fi in range(hand.nframe):
    if fi >= BASE_GUN:
        all_locals.append(refit_frame(n_h2 + (fi - BASE_GUN)))
    elif fi >= BASE_H2:
        all_locals.append(refit_frame(fi - BASE_H2))
    else:
        locs = []
        for j in range(nj):
            ft, fq, fs = hand.frame_local[fi][j]
            ot = hand.base_local[j][0]
            locs.append((new_bind_local[j][0] + (np.array(ft) - np.array(ot)), np.array(fq), np.array(fs)))
        all_locals.append(locs)


def skin_with(locs, verts, bidx_, bw_, inv):
    G = [None] * nj
    for j, l in enumerate(locs):
        L = local_mat(*l); G[j] = L if parents[j] < 0 else G[parents[j]] @ L
    S = np.array([G[j] @ inv[j] for j in range(nj)])
    hp = np.c_[verts, np.ones(len(verts))]
    out = np.zeros((len(verts), 3))
    for k in range(bidx_.shape[1]):
        out += bw_[:, k:k + 1] * np.einsum("vij,vj->vi", S[bidx_[:, k]], hp)[:, :3]
    return out

old_e, new_e = [], []
for fi, tag in [(BASE_H2 + f, ("h2", f)) for f in range(0, n_h2, 3)] + [(BASE_GUN + f, ("gun", f)) for f in range(0, n_gun, 3)]:
    X = FR[FR_TAG.index(tag)]
    old_e.append(np.linalg.norm(skin_with(hand.frame_local[fi], rest, old_bidx, old_bwts, hand.base_inv) - X, axis=1).mean())
    new_e.append(np.linalg.norm(skin_with(all_locals[fi], rest, bidx, bw, new_inv) - X, axis=1).mean())
say("glove vs his own frames (every 3rd): OLD fit mean error %.3f (worst %.3f); REFIT %.3f (worst %.3f)"
    % (np.mean(old_e), np.max(old_e), np.mean(new_e), np.max(new_e)))

# ---------------------------------------------------------------- 6. slim
rs = Hand(RS_IQM)
rs_main = rs.bidx[np.arange(len(rs.pos)), rs.bwt.argmax(1)]
FINGER_J = [j for j in range(nj) if j not in FIXED]


def axis_of(j, G, pos_of):
    kids = [k for k in children[j]]
    c = pos_of(j)
    if kids:
        d = pos_of(kids[0]) - c
    else:
        d = pos_of(j) - pos_of(parents[j])
    return c, d / np.linalg.norm(d)


def radius(verts, c, d):
    r = verts - c; r = r - np.outer(r @ d, d)
    return np.linalg.norm(r, axis=1)

slim_k = {}
for j in FINGER_J:
    gsel, rsel = label == j, rs_main == j
    if gsel.sum() < MIN_VERTS or rsel.sum() < MIN_VERTS:
        continue
    cg, dg = axis_of(j, newG, lambda k: newG[k][:3, 3])
    cr, dr = axis_of(j, rs.base_global, lambda k: rs.base_global[k][:3, 3])
    rg, rr = np.median(radius(rest[gsel], cg, dg)), np.median(radius(rs.pos[rsel], cr, dr))
    slim_k[j] = float(np.clip(rr / rg, 0.7, 1.0))
say("slim factors (RS radius / glove radius): " + ", ".join("%s %.2f" % (names[j].replace("_joint", ""), k) for j, k in slim_k.items()))
disp = np.zeros((V, 3))
for v in range(V):
    for s in range(2):
        j, w = bidx[v, s], bw[v, s]
        if w <= 0 or j not in slim_k:
            continue
        c, d = axis_of(j, newG, lambda k: newG[k][:3, 3])
        r = rest[v] - c; r = r - (r @ d) * d
        disp[v] += w * (slim_k[j] - 1.0) * r
slim = rest + disp


# ---------------------------------------------------------------- IQM write
def normals(verts):
    n = np.zeros_like(verts)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    # keep the authored normals' side
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    if (n * al["normals"]).sum() < 0:
        n = -n
    return n


src = open(SRC_IQM, "rb").read()
H = struct.unpack_from("<27I", src, 16)
ntext_, otext_, nanim_, oanim_ = H[3], H[4], H[17], H[18]
src_text = src[otext_:otext_ + ntext_]
def src_str(o): return src_text[o:src_text.index(b"\0", o)].decode("latin-1")


def write_iqm(path, verts):
    text = bytearray(b"\0")
    def add(s):
        raw = s.encode("latin-1") + b"\0"; o = len(text); text.extend(raw); return o
    joint_names = [add(n) for n in names]
    anims = []
    for a in range(nanim_):
        nm, first, num, rate, fl = struct.unpack_from("<IIIfI", src, oanim_ + a * 20)
        anims.append((add(src_str(nm)), first, num, rate, fl))
    mesh_name, mat_name = add("ErmacGlove"), add("hand_ermac.png")
    while len(text) % 4: text.append(0)
    NF = len(all_locals)
    vals = np.zeros((NF, nj, 10))
    for fi, locs in enumerate(all_locals):
        for j, (tt, q, s) in enumerate(locs):
            vals[fi, j, :3] = tt; vals[fi, j, 3:7] = q; vals[fi, j, 7:] = s
    lo = vals.min(0); span = vals.max(0) - lo
    poses_b = bytearray(); masks = []
    for j in range(nj):
        mask = 0; offs = []; scs = []
        for c in range(10):
            offs.append(lo[j, c])
            if span[j, c] > 1e-6:
                mask |= 1 << c; scs.append(span[j, c] / 65535.0)
            else:
                scs.append(0.0)
        masks.append(mask)
        poses_b += struct.pack("<iI10f10f", parents[j], mask, *offs, *scs)
    ch = [(j, c) for j in range(nj) for c in range(10) if masks[j] & (1 << c)]
    frames = np.zeros((NF, len(ch)), np.int64)
    for i, (j, c) in enumerate(ch):
        frames[:, i] = np.round((vals[:, j, c] - lo[j, c]) / (span[j, c] / 65535.0))
    frames_b = np.clip(frames, 0, 65535).astype("<u2").tobytes()
    joints_b = b"".join(struct.pack("<Ii3f4f3f", joint_names[j], parents[j], *new_bind_local[j][0], *new_bind_local[j][1], *new_bind_local[j][2]) for j in range(nj))
    bidx8 = bidx.astype(np.uint8)
    w = np.floor(bw * 255.0).astype(int); w[:, 0] += 255 - w.sum(1)
    bounds_b = bytearray()
    for fi in range(NF):
        sk = skin_with(all_locals[fi], verts, bidx, bw, new_inv)
        bmin, bmax = sk.min(0), sk.max(0)
        bounds_b += struct.pack("<8f", *bmin, *bmax, float(np.sqrt((sk[:, :2] ** 2).sum(1)).max()), float(np.sqrt((sk ** 2).sum(1)).max()))

    cur = 124; layout = []
    def place(blob):
        nonlocal cur
        while cur % 4: cur += 1
        o = cur; layout.append([o, bytes(blob)]); cur += len(blob); return o
    o_text = place(text)
    o_mesh = place(struct.pack("<6I", mesh_name, mat_name, 0, V, 0, len(tris)))
    va_slot = place(bytes(100))
    op = place(verts.astype("<f4").tobytes()); ou = place(uvs.astype("<f4").tobytes())
    on = place(normals(verts).astype("<f4").tobytes()); oi = place(bidx8.tobytes()); ow = place(w.astype(np.uint8).tobytes())
    for L_ in layout:
        if L_[0] == va_slot:
            L_[1] = b"".join([struct.pack("<5I", 0, 0, 7, 3, op), struct.pack("<5I", 1, 0, 7, 2, ou), struct.pack("<5I", 2, 0, 7, 3, on),
                              struct.pack("<5I", 4, 0, 1, 4, oi), struct.pack("<5I", 5, 0, 1, 4, ow)])
    o_tri = place(tris.astype("<u4").tobytes())
    o_joint = place(joints_b); o_pose = place(poses_b)
    o_anim = place(b"".join(struct.pack("<IIIfI", *a) for a in anims))
    o_frame = place(frames_b); o_bounds = place(bounds_b)
    while cur % 4: cur += 1
    hdr = [2, cur, 0, len(text), o_text, 1, o_mesh, 5, V, va_slot, len(tris), o_tri, 0,
           nj, o_joint, nj, o_pose, len(anims), o_anim, NF, len(ch), o_frame, o_bounds, 0, 0, 0, 0]
    out = bytearray(cur); out[:16] = b"INTERQUAKEMODEL\0"; struct.pack_into("<27I", out, 16, *hdr)
    for o, blob in layout: out[o:o + len(blob)] = blob
    open(path, "wb").write(bytes(out))
    # round trip through the reader the other tools use
    chk = Hand(path)
    assert chk.nframe == NF and chk.names == names and len(chk.pos) == V
    worst = 0.0
    for fi in (0, 3, 8, 1289, 1292, BASE_H2 + 58, BASE_GUN + 6, NF - 1):
        a = skin_with(all_locals[fi], verts, bidx, bw, new_inv)
        b = chk.skin(chk.globals(chk.local_mats(chk.frame_local[fi])))
        worst = max(worst, float(np.abs(a - b).max()))
    for i in range(nj):
        assert struct.unpack_from("<i", out, o_joint + i * 48 + 4)[0] < i
    say("wrote %s: %d bytes, %d frames, %d channels; re-read skin matches to %.4f" % (os.path.basename(path), len(out), NF, len(ch), worst))

write_iqm(os.path.join(OUT, "hand_ermac_refit.iqm"), rest)
write_iqm(os.path.join(OUT, "hand_ermac_refit_slim.iqm"), slim)
np.savez(os.path.join(OUT, "refit.npz"), rest=rest, slim=slim, bidx=bidx, bw=bw, label=label,
         newpos=np.array([newpos[j] for j in range(nj)]))

# ---------------------------------------------------------------- sheet (CPU painter's renders, no GPU)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROWS = [("open", 0, None), ("trigger", 2, None), ("fist", 3, None), ("pinch", 4, None), ("grip (ready)", 8, None),
        ("hold round", 1289, None), ("hold slide", 1292, None),
        ("his fist h2#58", BASE_H2 + 58, ("h2", 58)), ("his pinch h2#28", BASE_H2 + 28, ("h2", 28)),
        ("his pistol grip gun#6", BASE_GUN + 6, ("gun", 6)), ("his chaingun grip gun#84", BASE_GUN + 84, ("gun", 84))]
COLS = ["glove today", "refit", "refit + slim", "RS hand", "Ermac's own frame"]
rs_tris = rs.tris.astype(np.int64)


def draw(ax, verts, tri, view, colour):
    if view == "side":
        sx, sy, depth = verts[:, 1], verts[:, 2], verts[:, 0]
    else:
        sx, sy, depth = verts[:, 0], verts[:, 2], verts[:, 1]
    a, b, c = verts[tri[:, 0]], verts[tri[:, 1]], verts[tri[:, 2]]
    fn = np.cross(b - a, c - a); fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
    light = np.array([0.5, 0.6, 0.62]) if view == "side" else np.array([0.35, 0.8, 0.5])
    shade = 0.3 + 0.7 * np.abs(fn @ (light / np.linalg.norm(light)))
    order = np.argsort(depth[tri].mean(1))
    polys = np.stack([np.stack([sx[tri[:, k]], sy[tri[:, k]]], 1) for k in range(3)], 1)[order]
    cols = np.clip(np.outer(shade[order], colour), 0, 1)
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="none"))


for view in ("side", "palm"):
    fig, axs = plt.subplots(len(ROWS), len(COLS), figsize=(len(COLS) * 2.6, len(ROWS) * 2.6))
    for r, (nm, fi, his) in enumerate(ROWS):
        items = [(skin_with(hand.frame_local[fi], rest, old_bidx, old_bwts, hand.base_inv), tris, (0.85, 0.55, 0.45)),
                 (skin_with(all_locals[fi], rest, bidx, bw, new_inv), tris, (0.45, 0.75, 0.5)),
                 (skin_with(all_locals[fi], slim, bidx, bw, new_inv), tris, (0.4, 0.65, 0.85)),
                 (rs.skin(rs.globals(rs.local_mats(rs.frame_local[fi]))), rs_tris, (0.8, 0.75, 0.6)),
                 ((FR[FR_TAG.index(his)], tris, (0.9, 0.8, 0.35)) if his else None)]
        for cidx, it in enumerate(items):
            ax = axs[r, cidx]; ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            ax.set_xlim(-12, 12) if view == "palm" else ax.set_xlim(-10, 14)
            ax.set_ylim(-26, 4)
            if it is None:
                ax.axis("off"); continue
            draw(ax, it[0], it[1], view, it[2])
            if r == 0: ax.set_title(COLS[cidx], fontsize=9)
            if cidx == 0: ax.set_ylabel("%s\n#%d" % (nm, fi), fontsize=8)
    fig.suptitle("Ermac glove refit -- %s view (fingers point down)" % view, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "refit_sheet_%s.png" % view), dpi=80)
    plt.close(fig)

open(os.path.join(OUT, "refit_report.txt"), "w").write("\n".join(report) + "\n")
print("sheets written")
