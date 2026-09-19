"""The Dark Ages Praetor suit (GMod, Source MDL v48) as a body and two hands.

usage: praetor_to_iqm.py MODEL_BASE OUT_DIR [--scale 0.874]

NOTHING IS CUT. Unlike the Eternal marine -- whose arms and hands are one mesh, so
pinning the hands meant splitting them -- this model already ships its hands as their
own bodyparts (praetor_hand_left.smd / praetor_hand_right.smd, ~15k verts each), and
they are hands: the mesh reaches only 10.6 units from the wrist joint, with 61 percent
of it inside 6. So the hands come out whole, as they were authored.

Writes, all on the full 83-joint ValveBiped skeleton with indices unchanged:
  praetor_body.iqm      armor, helmet, lower, torso and the visor
  praetor_hand_rt.iqm   the right hand, ORIGINED AT ITS PALM
  praetor_hand_lf.iqm   the left hand, the same

ORIGINED AT THE PALM, because that is where the RS hand -- the one that has always
landed correctly -- carries its origin, and the origin is the point the engine pins to
your controller. The wrist is 1.9 units off from that and it shows.

SCALE 0.874 puts him at the Eternal marine's height, so one set of the owner's body
numbers serves both and switching bodies does not re-open the calibration.
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
    out = []    # (model file name, material name, [(a, b, c) global ids])
    for bpi in range(numbodyparts):
        bp = bodypartindex + bpi * 16
        if cstr(mdl, bp + struct.unpack_from("<i", mdl, bp)[0]) != want:
            continue
        nummodels, base, modelindex = struct.unpack_from("<iii", mdl, bp + 4)
        vbp = vtx_bpIdx + bpi * 8
        vtx_nm, vtx_modelIdx = struct.unpack_from("<ii", vtx, vbp)
        for mi in range(nummodels):
            mo = bp + modelindex + mi * 148
            mo_name = cstr(mdl, mo).strip(chr(0)).replace(chr(92), "/").split("/")[-1]
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
                out.append((mo_name, materials[material], tris))
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




ORIGIN = np.zeros(3)

# The body is everything but the hands -- and the hands are already their own
# bodyparts here, which is the whole reason nothing gets cut.
BODY_PARTS  = ["armor", "helmet", "lower", "torso", "visor"]
VISOR_MODEL = "praetor_visor_solid.smd"
HANDS = {"praetor_hand_right.smd": ("rt", "R"), "praetor_hand_left.smd": ("lf", "L")}


def matpath(name):
    return "models/praetor/%s.png" % name.lower()


def palm_of(side):
    """The point the controller holds: midway between the wrist and the knuckles.

    The RS hand carries its origin AT its palm, and the origin is what the engine
    pins. Using the wrist instead leaves the hand about 1.9 units past your grip --
    close enough to look intended, wrong everywhere it matters.
    """
    w = G[BI["ValveBiped.Bip01_%s_Hand" % side]][:3, 3]
    bases = []
    for f in ("1", "2", "3", "4"):                 # index, middle, ring, pinky
        n = "ValveBiped.Bip01_%s_Finger%s" % (side, f)
        if n in BI:
            bases.append(G[BI[n]][:3, 3])
    return (w + np.mean(bases, axis=0)) / 2.0 if bases else w.copy()


# ---- the hands, WHOLE, each at its own palm ------------------------------
for want_model in HANDS:
    S, side = HANDS[want_model]
    got = []
    for mo_name, mat, tris in bodypart_meshes("hand"):
        if mo_name.lower() != want_model:
            continue
        got.append(("praetor_hand_%s_%s" % (S, mat.lower()), matpath(mat), tris))
    if not got:
        report.append("WARNING: %s produced no mesh" % want_model)
        continue
    ORIGIN = palm_of(side)
    write_iqm(os.path.join(OUT, "praetor_hand_%s.iqm" % S), got)
    report.append("hand %s: %d mesh(es), WHOLE and uncut, origined at the palm (%.2f %.2f %.2f)"
                  % (S, len(got), ORIGIN[0], ORIGIN[1], ORIGIN[2]))
    ORIGIN = np.zeros(3)

# ---- the body -----------------------------------------------------------
whole = []
for bp in BODY_PARTS:
    for mo_name, mat, tris in bodypart_meshes(bp):
        if bp == "visor" and mo_name.lower() != VISOR_MODEL:
            continue                               # one of the two visor variants only
        whole.append(("praetor_%s_%s" % (bp, mat.lower()), matpath(mat), tris))
write_iqm(os.path.join(OUT, "praetor_body.iqm"), whole)
report.append("body: %d meshes from %s" % (len(whole), ", ".join(BODY_PARTS)))
report.append("NOTHING WAS CUT -- the hands were already their own bodyparts")
open(os.path.join(OUT, "praetor_report.txt"), "w").write(chr(10).join(report) + chr(10))
print(chr(10).join(report))
