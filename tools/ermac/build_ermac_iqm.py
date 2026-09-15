"""Step A.3: Ermac's glove as an IQM on our hand's exact skeleton and animation.

- Weights: each of his vertices takes the bone weights of the nearest point on our already-weighted bind
  mesh (barycentric blend of that triangle's three vertices), top 4 joints kept, summing to 255.
- IQM: hand_left.iqm's text, joints, poses, anims, frames and bounds are copied byte for byte (his mesh
  and material names are appended to the text, so every existing name offset stays valid); meshes,
  vertex arrays and triangles are his. No adjacency.
- Checks: posed OBJs of frames 0 (open), 3 (fist), 8 (index on trigger), 1292 (hold slide) and 1289
  (hold round), skinned the way the engine does, plus the loader constraints verify_iqm.py checks.

Credit: the mesh and skin are Ermac's (iAmErmac), from Rusted Legacy (MIT).
"""
import json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from hand_iqm import Hand, HAND

OUT_IQM = os.path.join(HERE, "hand_ermac.iqm")
POSE_FRAMES = {"open": 0, "fist": 3, "trigger": 8, "holdslide": 1292, "holdround": 1289}

a = np.load(os.path.join(HERE, "ermac_aligned.npz"))
ev, en, euv, etri = a["verts"], a["normals"], a["uvs"], a["tris"].astype(np.int64)
h = Hand()
nj = len(h.names)


# ---------------------------------------------------------------- weight transfer
def closest_bary(p, A, B, C):
    """For points p (P x 3): index of the nearest triangle and barycentric weights on it."""
    best_d = np.full(len(p), np.inf); best_t = np.zeros(len(p), dtype=int); best_w = np.zeros((len(p), 3))
    ab, ac = B - A, C - A
    for i0 in range(0, len(p), 64):
        P = p[i0:i0 + 64][:, None, :]
        ap, bp, cp = P - A, P - B, P - C
        d1 = np.einsum("tk,ptk->pt", ab, ap); d2 = np.einsum("tk,ptk->pt", ac, ap)
        d3 = np.einsum("tk,ptk->pt", ab, bp); d4 = np.einsum("tk,ptk->pt", ac, bp)
        d5 = np.einsum("tk,ptk->pt", ab, cp); d6 = np.einsum("tk,ptk->pt", ac, cp)
        va = d3 * d6 - d5 * d4; vb = d5 * d2 - d1 * d6; vc = d1 * d4 - d3 * d2
        den = va + vb + vc; den = np.where(np.abs(den) < 1e-12, 1e-12, den)
        v = vb / den; w = vc / den; u = 1 - v - w
        W = np.stack([u, v, w], axis=-1)
        def setw(mask, uu, vv, ww):
            W[mask] = np.stack([uu, vv, ww], axis=-1)[mask]
        m = (d1 <= 0) & (d2 <= 0); setw(m, np.ones_like(u), np.zeros_like(u), np.zeros_like(u))
        m = (d3 >= 0) & (d4 <= d3); setw(m, np.zeros_like(u), np.ones_like(u), np.zeros_like(u))
        m = (d6 >= 0) & (d5 <= d6); setw(m, np.zeros_like(u), np.zeros_like(u), np.ones_like(u))
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        tt = d1 / np.where(np.abs(d1 - d3) < 1e-12, 1e-12, d1 - d3); setw(m, 1 - tt, tt, np.zeros_like(u))
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        tt = d2 / np.where(np.abs(d2 - d6) < 1e-12, 1e-12, d2 - d6); setw(m, 1 - tt, np.zeros_like(u), tt)
        m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
        tt = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-12, 1e-12, (d4 - d3) + (d5 - d6))
        setw(m, np.zeros_like(u), 1 - tt, tt)
        Q = W[..., 0:1] * A + W[..., 1:2] * B + W[..., 2:3] * C
        d = np.linalg.norm(P - Q, axis=2)
        j = d.argmin(axis=1)
        r = np.arange(len(j))
        sl = slice(i0, i0 + len(j))
        best_d[sl] = d[r, j]; best_t[sl] = j; best_w[sl] = W[r, j]
    return best_t, best_w, best_d


otri = h.tris.astype(np.int64)
A, B, C = h.pos[otri[:, 0]], h.pos[otri[:, 1]], h.pos[otri[:, 2]]
ti, bw, dist = closest_bary(ev, A, B, C)
print("weight transfer: nearest-surface gap mean %.2f, 90%% %.2f, max %.2f" % (dist.mean(), np.percentile(dist, 90), dist.max()))

acc = np.zeros((len(ev), nj))
for k in range(3):
    vid = otri[ti, k]
    for s in range(4):
        np.add.at(acc, (np.arange(len(ev)), h.bidx[vid, s]), bw[:, k] * h.bwt[vid, s])
order = np.argsort(-acc, axis=1)[:, :4]
top = np.take_along_axis(acc, order, axis=1)
top = top / np.maximum(top.sum(axis=1, keepdims=True), 1e-9)
w255 = np.floor(top * 255.0).astype(int)
rem = 255 - w255.sum(axis=1)
w255[np.arange(len(ev)), 0] += rem                     # the largest takes the rounding
bidx = order.astype(np.uint8)
bwts = w255.astype(np.uint8)
# Kept for the pose fit (fit_ermac_poses.py): the same bone assignments the IQM carries.
np.savez(os.path.join(HERE, "ermac_weights.npz"), bidx=bidx, bwts=bwts, acc=acc)
main_joint = np.array(h.names)[order[:, 0]]
names, counts = np.unique(main_joint, return_counts=True)
print("vertices by main joint: " + ", ".join("%s %d" % (n.replace("_joint", ""), c) for n, c in zip(names, counts)))

# ---------------------------------------------------------------- IQM write
src = open(HAND, "rb").read()
H = list(struct.unpack_from("<27I", src, 16))
(ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri_ofs, oadj,
 njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = H

text = bytearray(src[otext:otext + ntext])
def add_text(s_):
    off = len(text); text.extend(s_.encode("latin-1") + b"\0"); return off
mesh_name = add_text("ErmacGlove")
mat_name = add_text("hand_ermac.png")
while len(text) % 4: text.append(0)

joints_b = src[ojoint:ojoint + njoint * 48]
poses_b = src[opose:opose + npose * 88]
anims_b = src[oanim:oanim + nanim * 20]
frames_b = src[oframe:oframe + nframe * nfch * 2]
bounds_b = src[obounds:obounds + nframe * 32] if obounds else b""

V = len(ev)
pos_b = ev.astype("<f4").tobytes()
uv_b = euv.astype("<f4").tobytes()
nrm_b = en.astype("<f4").tobytes()
bi_b = bidx.tobytes()
bw_b = bwts.tobytes()
tri_b = etri.astype("<u4").tobytes()

HDR = 124
layout = []
cur = HDR
def place(blob, align=4):
    global cur
    while cur % align: cur += 1
    off = cur; layout.append((off, blob)); cur += len(blob); return off

o_text = place(bytes(text))
mesh_b = struct.pack("<6I", mesh_name, mat_name, 0, V, 0, len(etri))
o_mesh = place(mesh_b)
va_count = 5
o_va = cur; cur += va_count * 20
while cur % 4: cur += 1
o_pos = place(pos_b); o_uv = place(uv_b); o_nrm = place(nrm_b); o_bi = place(bi_b); o_bw = place(bw_b)
va_b = b"".join([struct.pack("<5I", 0, 0, 7, 3, o_pos), struct.pack("<5I", 1, 0, 7, 2, o_uv),
                 struct.pack("<5I", 2, 0, 7, 3, o_nrm), struct.pack("<5I", 4, 0, 1, 4, o_bi),
                 struct.pack("<5I", 5, 0, 1, 4, o_bw)])
layout.append((o_va, va_b))
o_tri = place(tri_b)
o_joint = place(joints_b); o_pose = place(poses_b); o_anim = place(anims_b); o_frame = place(frames_b)
o_bounds = place(bounds_b) if bounds_b else 0
total = cur

out = bytearray(total)
hdr = [2, total, 0, len(text), o_text, 1, o_mesh, va_count, V, o_va, len(etri), o_tri, 0,
       njoint, o_joint, npose, o_pose, nanim, o_anim, nframe, nfch, o_frame, o_bounds, 0, 0, 0, 0]
out[0:16] = b"INTERQUAKEMODEL\0"
struct.pack_into("<27I", out, 16, *hdr)
for off, blob in layout:
    out[off:off + len(blob)] = blob
open(OUT_IQM, "wb").write(bytes(out))
print("wrote %s  %d bytes  verts %d tris %d joints %d frames %d" % (OUT_IQM, total, V, len(etri), njoint, nframe))

# ---------------------------------------------------------------- loader checks (verify_iqm.py's)
d = open(OUT_IQM, "rb").read()
f = struct.unpack_from("<27I", d, 16)
assert d[:16] == b"INTERQUAKEMODEL\0" and f[0] == 2 and f[3] != 0 and f[1] == len(d)
for i in range(f[13]):
    parent = struct.unpack_from("<i", d, f[14] + i * 48 + 4)[0]
    assert parent < i
for i in range(f[17]):
    nofs, first, cnt, rate, fl = struct.unpack_from("<IIIfI", d, f[18] + i * 20)
    assert first + cnt <= f[19]
print("loader checks: OK")

# ---------------------------------------------------------------- posed exports for renders
hp = np.c_[ev, np.ones(V)]
tw = bwts.astype(np.float64) / 255.0
for tag, fr in POSE_FRAMES.items():
    g = h.globals(h.local_mats(h.frame_local[fr]))
    skinm = np.array([g[j] @ h.base_inv[j] for j in range(nj)])
    posed = np.zeros((V, 3))
    for k in range(4):
        posed += tw[:, k:k + 1] * np.einsum("vij,vj->vi", skinm[bidx[:, k]], hp)[:, :3]
    with open(os.path.join(HERE, "ermac_pose_%s.obj" % tag), "w") as fh:
        for v in posed:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for uv in euv:
            fh.write("vt %.5f %.5f\n" % (uv[0], 1.0 - uv[1]))
        for a_, b_, c_ in etri:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a_ + 1, a_ + 1, b_ + 1, b_ + 1, c_ + 1, c_ + 1))
OUT = os.path.join(HERE, "out").replace("\\", "/")
shots = []
objs = []
for i, tag in enumerate(POSE_FRAMES):
    objs.append({"path": os.path.join(HERE, "ermac_pose_%s.obj" % tag).replace("\\", "/"),
                 "texture": "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand_HD.png"})
for tag in POSE_FRAMES:
    sc = {"objs": [{"path": os.path.join(HERE, "ermac_pose_%s.obj" % tag).replace("\\", "/"),
                    "texture": "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand_HD.png"}],
          "shots": [{"file": OUT + "/pose_%s_side.png" % tag, "cam": [70.0, 10.0, -6.0], "look": [0.0, 0.0, -8.0], "lens": 50},
                    {"file": OUT + "/pose_%s_palm.png" % tag, "cam": [10.0, 70.0, -6.0], "look": [0.0, 0.0, -8.0], "lens": 50}]}
    json.dump(sc, open(os.path.join(HERE, "scene_pose_%s.json" % tag), "w"), indent=1)
print("posed exports and scenes written")
