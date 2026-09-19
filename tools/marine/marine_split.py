"""The Doom Eternal Classic Slayer, SPLIT AT THE WRISTS -- body, and two hands.

usage: marine_split.py MODEL_BASE OUT_DIR [--scale 0.872] [--cut-map 1.29,1.03]

WHY A SPLIT AT ALL, when the point of a whole body was not cutting anything:
because A HAND MUST BE PINNED TO THE CONTROLLER, and the engine pins an ACTOR.
Absorbed into the body mesh, the hand goes wherever the arm's IK solve puts it --
which is near the controller when the arm can reach and nowhere near it when it
cannot. Weeks of engine work exist to make the hand exact, and the whole-body
model threw that away.

So the hands come out as their own actors again. The difference from the part
rig, and it is the whole difference: THIS IS HIS HAND MEETING HIS OWN ARM. Same
mesh, same skeleton, same skin, cut on one plane. There is no socket to measure,
no stub to reshape, no pairing to choose and no seam to hide -- the two sides of
the cut are the same surface.

Writes:
  marine_body.iqm     every bodypart, with the arms clipped AT the wrist plane
  marine_hand_rt.iqm  what was on the other side of that plane, right
  marine_hand_lf.iqm  the same, left
all on the full 152-joint skeleton with joint indices unchanged, so one skeleton
drives all three and a pose written for one reads on the others.
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
    # RE-ORIGINED AT THE WRIST, when ORIGIN is set.
    #
    # A cut-out hand still carries the BODY'S coordinates: its vertices sit where the
    # hand sits on a standing marine, about 20 units out from the model origin. The
    # engine pins an actor by its ORIGIN, so pinned to a controller the geometry drew
    # twenty units away and at the body's scale -- tiny, and off in the distance.
    #
    # Subtracting the wrist from the vertices AND from the ROOT joint's translation
    # moves the whole rig together, so the skinning is untouched and the hand's own
    # wrist lands on (0,0,0) -- which is the point the controller holds.
    pos = ((VP[order] - ORIGIN) * SCALE).astype("<f4"); nrm = VN[order].astype("<f4"); uv = VT[order].astype("<f4")
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
        t = (b["pos"] - (ORIGIN if b["parent"] < 0 else 0.0)) * SCALE
        joints += struct.pack("<Ii3f4f3f", add(b["name"]), b["parent"], *t, *b["quat"], 1.0, 1.0, 1.0)
    for b in bones:
        t = (b["pos"] - (ORIGIN if b["parent"] < 0 else 0.0)) * SCALE
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

ORIGIN = np.zeros(3)


def matpath(name):
    return "models/marine/%s.png" % name.lower()



# ---------------------------------------------------------------- the wrist plane
#
# One plane per side, square to the forearm (bip_lowerArm -> bip_hand), CUT_MAP map
# units behind bip_hand. Every triangle that crosses it is CLIPPED on it, and a
# crossing edge shared by two triangles makes ONE new vertex -- so both sides of the
# cut end in the same closed ring, vertex for vertex. That is what makes the seam
# invisible here and did not in the part rig: the ring is shared, not fitted.
CUT_MAP = [float(x) for x in sys.argv[sys.argv.index("--cut-map") + 1].split(",")] if "--cut-map" in sys.argv else [1.29, 1.03]

KEEP = ["torso", "shoulders_protections", "arms", "legs", "pouches", "shells",
        "helmet", "main"]
DROP = ["hair", "arm_left_blade", "torso_grenadelauncher", "nothing"]


def add_vertex(i, j, t):
    """A vertex on the cut, blending position, normal, UV and bone weights."""
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


def plane(side):
    hp = G[BI["bip_hand_" + side]][:3, 3]
    ep = G[BI["bip_lowerArm_" + side]][:3, 3]
    axis = (hp - ep) / np.linalg.norm(hp - ep)
    cut = CUT_MAP[0 if side == "R" else 1] / SCALE
    return hp - axis * cut, axis


def split(tris, c, axis, want_hand):
    """Triangles on one side of the plane, the crossing ones clipped onto it.

    want_hand False keeps sd <= 0 (the arm); True keeps sd > 0 (the hand). The SAME
    edge_vertex table serves both calls for a side, so the two rings are identical.
    """
    kept, clipped, dropped = [], 0, 0
    for t in tris:
        sd = [float((VP[v] - c) @ axis) for v in t]
        inside = [(x > 0) == want_hand for x in sd]
        if all(inside):
            kept.append(tuple(t)); continue
        if not any(inside):
            dropped += 1; continue
        s_of = {t[k]: sd[k] for k in range(3)}
        poly = []
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            ain = (s_of[a] > 0) == want_hand
            bin_ = (s_of[b] > 0) == want_hand
            if ain:
                poly.append(a)
            if ain != bin_:
                lo, hi = min(a, b), max(a, b)
                if (lo, hi) not in EDGE:
                    EDGE[(lo, hi)] = add_vertex(lo, hi, s_of[lo] / (s_of[lo] - s_of[hi]))
                poly.append(EDGE[(lo, hi)])
        for k in range(1, len(poly) - 1):
            kept.append((poly[0], poly[k], poly[k + 1]))
        clipped += 1
    return kept, clipped, dropped


EDGE = {}
ARM_MAT = {"R": "doomslayer_arm_right_set3_skin", "L": "doomslayer_arm_left_set3_skin"}
PLANE = {s: plane(s) for s in ("R", "L")}

# ---- the hands ----------------------------------------------------------
arms = bodypart_meshes("arms")
for side, S in (("R", "rt"), ("L", "lf")):
    c, axis = PLANE[side]
    want = ARM_MAT[side]
    got = []
    for m, tris in arms:
        if m.lower() != want.lower():
            continue
        k, cl, dr = split(tris, c, axis, True)
        got += k
        report.append("hand %s: kept %d triangles, clipped %d, dropped %d (the arm's side)"
                      % (side, len(k), cl, dr))
    # ORIGINED AT THE PALM, BECAUSE THAT IS WHERE THE RS HAND'S ORIGIN IS.
    #
    # The RS hand that has been landing correctly for months has HANDPALM_joint at
    # (0, 0, 0.01) -- its origin IS its palm, and that is the point the controller
    # holds. Putting the marine's origin at bip_hand_* (the WRIST) instead left his
    # hand 1.93 units past the grip: close enough to look deliberate and wrong
    # everywhere it mattered.
    #
    # No palm joint exists on this skeleton, so the palm is the midpoint between the
    # wrist and the centroid of the four finger bases -- the middle of the hand a
    # grip closes around.
    _w = G[BI["bip_hand_" + side]][:3, 3]
    _bases = [G[BI["bip_%s_0_%s" % (f, side)]][:3, 3]
              for f in ("index", "middle", "ring", "pinky") if ("bip_%s_0_%s" % (f, side)) in BI]
    ORIGIN = ((_w + np.mean(_bases, axis=0)) / 2.0).copy() if _bases else _w.copy()
    write_iqm(os.path.join(OUT, "marine_hand_%s.iqm" % S),
              [("marine_hand_" + S, matpath(want), got)])
    report.append("hand %s re-origined at the PALM (%.2f %.2f %.2f file units), matching the RS hand"
                  % (side, ORIGIN[0], ORIGIN[1], ORIGIN[2]))
    ORIGIN = np.zeros(3)

# ---- the body, arms clipped at the same plane ---------------------------
whole = []
for bp in KEEP:
    for m, tris in bodypart_meshes(bp):
        if bp == "arms":
            side = "R" if m.lower() == ARM_MAT["R"].lower() else "L"
            c, axis = PLANE[side]
            tris, cl, dr = split(tris, c, axis, False)
            report.append("arm %s: kept %d triangles, clipped %d, dropped %d (the hand's side)"
                          % (side, len(tris), cl, dr))
        whole.append(("marine_%s_%s" % (bp, m.lower()), matpath(m), tris))
write_iqm(os.path.join(OUT, "marine_body.iqm"), whole)

report.append("cut planes: R %.2f, L %.2f map units behind bip_hand" % (CUT_MAP[0], CUT_MAP[1]))
report.append("shared ring vertices: %d -- both sides of every cut end on these exact vertices" % len(EDGE))
report.append("kept bodyparts: %s" % ", ".join(KEEP))
report.append("dropped: %s" % ", ".join(DROP))
open(os.path.join(OUT, "marine_split_report.txt"), "w").write(chr(10).join(report) + chr(10))
print(chr(10).join(report))
