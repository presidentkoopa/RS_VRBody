"""The Doom Eternal Classic Slayer (Source MDL v48 + VVD + VTX) as IQMs for RS_VRBody's optional marine body.

usage: marine_to_iqm.py MODEL_BASE OUT_DIR [--scale 0.872] [--cut -0.5]

Writes, all on the model's FULL 152-joint skeleton (joint indices unchanged, bind pose only, one frame):
  marine_torso.iqm    the "torso" bodypart (armour + neck skin) and "shoulders_protections"
  marine_arm_rt.iqm   the "arms" bodypart's right-arm material, HAND CUT OFF
  marine_arm_lf.iqm   the same for the left arm
and marine_iqm_report.txt.

THE HAND CUT. The palm is not skinned to bip_hand_*: it rides the forearm roll bone rollarmlower_pin3_*, and
the fingers ride their own bones. A vertex is the hand's if its dominant bone is in bip_hand_*'s subtree, or if
it sits past the cut plane: CUT (default -0.5) along the forearm (bip_lowerArm -> bip_hand) measured from
bip_hand. A triangle is kept only if none of its three vertices is the hand's.

FRAME AND UNITS. The Source file frame is +X left, -Y forward, +Z up -- the Slayer arm IQMs' own file frame -- so
positions only scale (SCALE, the marine shoulder-matched to the Slayer rig) and nothing is swapped. Joint
translations scale with them. UVs are Source's (top-left origin), which is IQM's. Materials name
models/marine/<texture>.png. Triangle winding is chosen to agree with the SLAYER arm IQM's convention (measured
here from slayer_arm_rt.iqm: geometric normal vs vertex normal), so the engine culls both the same way.
"""
import os, struct, sys
import numpy as np

BASE, OUT = sys.argv[1], sys.argv[2]
SCALE = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 0.872
CUT = float(sys.argv[sys.argv.index("--cut") + 1]) if "--cut" in sys.argv else -0.5
SLAYER_REF = "E:/DOOMWork/RS_VRBody/models/slayer/slayer_arm_rt.iqm"
os.makedirs(OUT, exist_ok=True)
mdl = open(BASE + ".mdl", "rb").read()
vvd = open(BASE + ".vvd", "rb").read()
vtx = open(BASE + ".dx90.vtx", "rb").read()
report = []

def cstr(buf, off):
    return buf[off:buf.index(b"\0", off)].decode("latin-1")

def qmat(x, y, z, w):
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])

# ---------------------------------------------------------------- MDL: bones, materials, bodyparts
o = 76 + 4 + 72 + 4
numbones, boneindex = struct.unpack_from("<ii", mdl, o); o += 8
o += 8 * 5
numtextures, textureindex = struct.unpack_from("<ii", mdl, o); o += 8
o += 8
o += 12
numbodyparts, bodypartindex = struct.unpack_from("<ii", mdl, o)
materials = [cstr(mdl, textureindex + i * 64 + struct.unpack_from("<i", mdl, textureindex + i * 64)[0]) for i in range(numtextures)]
bones = []
for i in range(numbones):
    bo = boneindex + i * 216
    nameoff, parent = struct.unpack_from("<ii", mdl, bo)
    bones.append(dict(name=cstr(mdl, bo + nameoff), parent=parent,
                      pos=np.array(struct.unpack_from("<3f", mdl, bo + 32)), quat=struct.unpack_from("<4f", mdl, bo + 44)))
BI = {b["name"]: i for i, b in enumerate(bones)}
G = []
for b in bones:
    L = np.eye(4); L[:3, :3] = qmat(*b["quat"]); L[:3, 3] = b["pos"]
    G.append(L if b["parent"] < 0 else G[b["parent"]] @ L)
children = {}
for i, b in enumerate(bones): children.setdefault(b["parent"], []).append(i)
def subtree(r):
    out, st = set(), [r]
    while st:
        j = st.pop(); out.add(j); st.extend(children.get(j, []))
    return out

# ---------------------------------------------------------------- VVD vertices
nv = struct.unpack_from("<8i", vvd, 16)[0]
vertIdx = struct.unpack_from("<i", vvd, 56)[0]
VP = np.zeros((nv, 3)); VN = np.zeros((nv, 3)); VT = np.zeros((nv, 2)); VB = np.zeros((nv, 3), int); VW = np.zeros((nv, 3))
for i in range(nv):
    vo = vertIdx + i * 48
    VW[i] = struct.unpack_from("<3f", vvd, vo); VB[i] = struct.unpack_from("<3B", vvd, vo + 12)
    n = vvd[vo + 15]; VW[i, n:] = 0.0
    VP[i] = struct.unpack_from("<3f", vvd, vo + 16); VN[i] = struct.unpack_from("<3f", vvd, vo + 28); VT[i] = struct.unpack_from("<2f", vvd, vo + 40)
DOM = VB[np.arange(nv), VW.argmax(1)]

# ---------------------------------------------------------------- VTX triangles per bodypart / mesh (global vertex ids)
vtx_bpIdx = struct.unpack_from("<i", vtx, 32)[0]
def bodypart_meshes(want):
    out = []    # (material name, [(a, b, c) global ids])
    for bpi in range(numbodyparts):
        bp = bodypartindex + bpi * 16
        if cstr(mdl, bp + struct.unpack_from("<i", mdl, bp)[0]) != want:
            continue
        nummodels, base, modelindex = struct.unpack_from("<iii", mdl, bp + 4)
        vbp = vtx_bpIdx + bpi * 8
        vtx_nm, vtx_modelIdx = struct.unpack_from("<ii", vtx, vbp)
        for mi in range(nummodels):
            mo = bp + modelindex + mi * 148
            _, _, nummeshes, meshindex, _, vertexindex = struct.unpack_from("<ifiiii", mdl, mo + 64)
            if nummeshes == 0: continue
            vm = vbp + vtx_modelIdx + mi * 8
            _, lodIdx = struct.unpack_from("<ii", vtx, vm)
            lod = vm + lodIdx
            _, meshIdx, _ = struct.unpack_from("<iif", vtx, lod)
            for mei in range(nummeshes):
                me = mo + meshindex + mei * 116
                material, _, _, m_vertexoffset = struct.unpack_from("<iiii", mdl, me)
                vmesh = lod + meshIdx + mei * 9
                nsg, sgIdx, _ = struct.unpack_from("<iiB", vtx, vmesh)
                tris = []
                for sgi in range(nsg):
                    sg = vmesh + sgIdx + sgi * 25
                    sg_nv, sg_vIdx, sg_ni, sg_iIdx = struct.unpack_from("<iiii", vtx, sg)
                    vids = [vertexindex // 48 + m_vertexoffset + struct.unpack_from("<H", vtx, sg + sg_vIdx + k * 9 + 4)[0] for k in range(sg_nv)]
                    idx = struct.unpack_from("<%dH" % sg_ni, vtx, sg + sg_iIdx)
                    tris += [(vids[idx[t]], vids[idx[t + 1]], vids[idx[t + 2]]) for t in range(0, sg_ni, 3)]
                out.append((materials[material], tris))
    return out

# ---------------------------------------------------------------- winding convention of the Slayer arm IQM
def winding_agreement(pos, nrm, tris):
    a, b, c = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    gn = np.cross(b - a, c - a)
    vn = nrm[tris[:, 0]] + nrm[tris[:, 1]] + nrm[tris[:, 2]]
    return float(((gn * vn).sum(1) > 0).mean())
d = open(SLAYER_REF, "rb").read()
h = struct.unpack_from("<27I", d, 16)
arrs = {}
for i in range(h[7]):
    t, fl, fmt, size, off = struct.unpack_from("<5I", d, h[9] + i * 20)
    arrs[t] = (fmt, size, off)
sp = np.frombuffer(d, dtype="<f4", count=h[8] * 3, offset=arrs[0][2]).reshape(-1, 3)
sn = np.frombuffer(d, dtype="<f4", count=h[8] * 3, offset=arrs[2][2]).reshape(-1, 3)
st = np.frombuffer(d, dtype="<u4", count=h[10] * 3, offset=h[11]).reshape(-1, 3)
slayer_agree = winding_agreement(sp, sn, st)
report.append("Slayer arm IQM: %.0f%% of triangles have a geometric normal agreeing with the vertex normals" % (100 * slayer_agree))

# ---------------------------------------------------------------- IQM writer
def write_iqm(path, meshes):
    """meshes: list of (mesh name, material path, global triangle list). Writes the vertices those triangles use."""
    text = bytearray(b"\0")
    def add(s):
        off = len(text); text.extend(s.encode("latin-1") + b"\0"); return off
    used = sorted({v for _, _, tris in meshes for t in tris for v in t})
    remap = {g: i for i, g in enumerate(used)}
    # vertices ordered mesh by mesh: IQM meshes are first_vertex/num_vertexes ranges
    order, mesh_recs, tri_out = [], [], []
    ntri_before = 0
    for mname, mat, tris in meshes:
        mv = sorted({v for t in tris for v in t})
        first_v = len(order)
        local = {g: first_v + k for k, g in enumerate(mv)}
        order += mv
        # first_triangle counts TRIANGLES before this mesh. It once took len(tri_out) -- the number of MESHES --
        # which a whole-file check cannot see (every triangle is still there) but anything drawing mesh by mesh
        # (Blender, the engine) pairs with the wrong vertices: the first textured mockup was all giant planes.
        T = np.array([[local[a], local[b], local[c]] for a, b, c in tris], dtype=np.int64)
        tri_out.append(T)
        mesh_recs.append((add(mname), add(mat), first_v, len(mv), ntri_before, len(T)))
        ntri_before += len(T)
    order = np.array(order)
    pos = (VP[order] * SCALE).astype("<f4"); nrm = VN[order].astype("<f4"); uv = VT[order].astype("<f4")
    tris = np.concatenate(tri_out)
    for _, _, fv_, nv_, ft_, nt_ in mesh_recs:          # every mesh's triangles use only its own vertices
        sub = tris[ft_:ft_ + nt_]
        assert len(sub) == nt_ and sub.min() >= fv_ and sub.max() < fv_ + nv_, "mesh range check failed"
    # winding: match the Slayer IQM's convention
    agree = winding_agreement(pos.astype(float), nrm.astype(float), tris)
    if (agree > 0.5) != (slayer_agree > 0.5):
        tris = tris[:, [0, 2, 1]]
        agree = winding_agreement(pos.astype(float), nrm.astype(float), tris)
    # skin: 4 slots, ubyte weights summing to 255
    bidx = np.zeros((len(order), 4), np.uint8); bw = np.zeros((len(order), 4), np.uint8)
    for i, g in enumerate(order):
        w = VW[g]; b = VB[g]
        s = w.sum() or 1.0
        q = np.floor(w / s * 255.0).astype(int)
        q[int(np.argmax(w))] += 255 - q.sum()
        bidx[i, :3] = b; bw[i, :3] = np.clip(q, 0, 255)
    # joints: bind locals, translation scaled; poses: every channel constant (mask 0), one frame, no channels
    joints = bytearray(); poses = bytearray()
    for b in bones:
        t = b["pos"] * SCALE
        joints += struct.pack("<Ii3f4f3f", add(b["name"]), b["parent"], *t, *b["quat"], 1.0, 1.0, 1.0)
    for b in bones:
        t = b["pos"] * SCALE
        poses += struct.pack("<iI10f10f", b["parent"], 0, *t, *b["quat"], 1.0, 1.0, 1.0, *([0.0] * 10))
    anim_name = add("bind")
    while len(text) % 4: text.append(0)

    cur = 124; layout = []
    def place(blob):
        nonlocal cur
        while cur % 4: cur += 1
        off = cur; layout.append((off, bytes(blob))); cur += len(blob); return off
    o_text = place(text)
    o_mesh = place(b"".join(struct.pack("<6I", *m) for m in mesh_recs))
    o_va = place(bytes(5 * 20))
    offs = [place(pos.tobytes()), place(uv.tobytes()), place(nrm.tobytes()), place(bidx.tobytes()), place(bw.tobytes())]
    va = b"".join([struct.pack("<5I", 0, 0, 7, 3, offs[0]), struct.pack("<5I", 1, 0, 7, 2, offs[1]), struct.pack("<5I", 2, 0, 7, 3, offs[2]),
                   struct.pack("<5I", 4, 0, 1, 4, offs[3]), struct.pack("<5I", 5, 0, 1, 4, offs[4])])
    layout = [(o, va) if o == o_va else (o, bl) for o, bl in layout]
    o_tri = place(tris.astype("<u4").tobytes())
    o_joint = place(joints); o_pose = place(poses)
    o_anim = place(struct.pack("<IIIfI", anim_name, 0, 1, 30.0, 0))
    while cur % 4: cur += 1
    hdr = [2, cur, 0, len(text), o_text, len(mesh_recs), o_mesh, 5, len(order), o_va, len(tris), o_tri, 0,
           numbones, o_joint, numbones, o_pose, 1, o_anim, 1, 0, cur, 0, 0, 0, 0, 0]
    out = bytearray(cur); out[:16] = b"INTERQUAKEMODEL\0"; struct.pack_into("<27I", out, 16, *hdr)
    for off, bl in layout: out[off:off + len(bl)] = bl
    open(path, "wb").write(bytes(out))
    report.append("%s: %d meshes %s, %d verts, %d tris, winding agreement %.0f%%, %d bytes"
                  % (os.path.basename(path), len(mesh_recs), [m[0] for m in meshes], len(order), len(tris), 100 * agree, len(out)))

def matpath(name):
    return "models/marine/%s.png" % name.lower()

# ---------------------------------------------------------------- torso
torso = [("marine_" + m, matpath(m), t) for m, t in bodypart_meshes("torso")] + \
        [("marine_shoulders", matpath(m), t) for m, t in bodypart_meshes("shoulders_protections")]
write_iqm(os.path.join(OUT, "marine_torso.iqm"), torso)

# ---------------------------------------------------------------- arms, hands cut by a PLANE
# The first cut dropped whole triangles by vertex (dominant in the hand's subtree, or past -0.5): a ragged edge
# running ~1.9 map units along the forearm, the ring whole only from ~1.0-1.3 units back (wrist_contours.py,
# 2026-09-15). Now: a plane square to the forearm (lowerArm -> hand), --cut-map R,L map units behind bip_hand,
# and every triangle that crosses it CLIPPED on it -- new vertices blend position, normal, UV and bone weights,
# and a crossing edge shared by two triangles makes ONE new vertex, so the cut edge is a single closed ring.
CUT_MAP = [float(x) for x in sys.argv[sys.argv.index("--cut-map") + 1].split(",")] if "--cut-map" in sys.argv else [1.29, 1.03]


def add_vertex(i, j, t):
    global VP, VN, VT, VB, VW, DOM
    p = VP[i] + (VP[j] - VP[i]) * t
    n = VN[i] + (VN[j] - VN[i]) * t
    n = n / max(np.linalg.norm(n), 1e-9)
    uv = VT[i] + (VT[j] - VT[i]) * t
    acc = {}
    for b, w in zip(VB[i], VW[i]): acc[int(b)] = acc.get(int(b), 0.0) + float(w) * (1.0 - t)
    for b, w in zip(VB[j], VW[j]): acc[int(b)] = acc.get(int(b), 0.0) + float(w) * t
    top = sorted(((w, b) for b, w in acc.items() if w > 0), reverse=True)[:3]
    tot = sum(w for w, _ in top) or 1.0
    bb = [b for _, b in top] + [0] * (3 - len(top))
    ww = [w / tot for w, _ in top] + [0.0] * (3 - len(top))
    VP = np.vstack([VP, p]); VN = np.vstack([VN, n]); VT = np.vstack([VT, uv])
    VB = np.vstack([VB, bb]); VW = np.vstack([VW, ww]); DOM = np.append(DOM, bb[0])
    return len(VP) - 1


arms = bodypart_meshes("arms")
for side, S in (("R", "rt"), ("L", "lf")):
    hand = BI["bip_hand_" + side]
    hp = G[hand][:3, 3]; ep = G[BI["bip_lowerArm_" + side]][:3, 3]
    axis = (hp - ep) / np.linalg.norm(hp - ep)
    cut_src = CUT_MAP[0 if side == "R" else 1] / SCALE              # map units -> the file's units
    c = hp - axis * cut_src
    want_mat = "doomslayer_arm_right_set3_skin" if side == "R" else "doomslayer_arm_left_set3_skin"
    kept, clipped, dropped = [], 0, 0
    edge_vertex = {}
    for m, tris in arms:
        if m.lower() != want_mat: continue
        for t in tris:
            sd = [float((VP[v] - c) @ axis) for v in t]              # > 0: the hand's side of the plane
            if all(x <= 0 for x in sd):
                kept.append(t); continue
            if all(x > 0 for x in sd):
                dropped += 1; continue
            s_of = {t[k]: sd[k] for k in range(3)}
            poly = []
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                if s_of[a] <= 0:
                    poly.append(a)
                if (s_of[a] <= 0) != (s_of[b] <= 0):
                    lo, hi = min(a, b), max(a, b)
                    if (lo, hi) not in edge_vertex:
                        edge_vertex[(lo, hi)] = add_vertex(lo, hi, s_of[lo] / (s_of[lo] - s_of[hi]))
                    poly.append(edge_vertex[(lo, hi)])
            for k in range(1, len(poly) - 1):                         # fan, winding kept
                kept.append((poly[0], poly[k], poly[k + 1]))
            clipped += 1
    hand_set = subtree(hand)
    survivors = len({v for t in kept for v in t if v < len(DOM) and DOM[v] in hand_set})
    report.append("arm %s: plane %.2f map units behind bip_hand_%s -- kept %d triangles whole, clipped %d, dropped %d; "
                  "%d new ring vertices; %d kept vertices still ride the hand's bones"
                  % (side, CUT_MAP[0 if side == "R" else 1], side, len(kept) - 0, clipped, dropped, len(edge_vertex), survivors))
    write_iqm(os.path.join(OUT, "marine_arm_%s.iqm" % S), [("marine_arm_" + S, matpath(want_mat), kept)])

open(os.path.join(OUT, "marine_iqm_report.txt"), "w").write("\n".join(report) + "\n")
print("\n".join(report))
