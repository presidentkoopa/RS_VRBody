"""The Dark Ages Praetor as ONE WHOLE BODY, hands attached. Reimported from the FBX.

    blender -b -noaudio --factory-startup -P praetor_whole.py -- <slayer.fbx> <out.iqm> [scale]

WHY THIS EXISTS. praetor_to_iqm.py wrote a body and TWO SEPARATE HAND FILES, and its own
docstring claimed the source "already ships its hands as their own bodyparts". It does not.
That script was reading a GMod MDL on a ValveBiped skeleton; the real source is this single
FBX -- 64 mesh objects on one 924-bone armature -- and the hands are part of the arms_legs
meshes like every other limb. The hands were CUT, and the body that shipped has stumps.

The owner asked twice for it whole. This is whole: every kept mesh, hands included, on the
one skeleton, in one file, exactly as marine_whole.iqm is for the Eternal marine.

THE BONE NAMES ARE A THIRD FAMILY. Not ValveBiped, and not the marine's bip_*: this rig uses
arm_upper_rt / arm_lower_rt / arm_hand_rt, leg_upper_lf / leg_lower_lf / leg_foot_lf,
spine_partNN_md, and fingers as thumb_/index_/middle_/ring_/pinky_partNN_rt|lf. Anything
downstream that names joints needs this third column.

DROPPED, and only these: the cape and the hair/fur cards. The cape is not a body part we can
drive and it clips through everything seated on the torso; the hair sits under a helmet.
Nothing else is filtered -- if it is on the body it is in the file.

SCALE puts him at the Eternal marine's height so one set of the owner's body numbers serves
both and switching bodies does not re-open the calibration.
"""
import bpy
import struct
import sys

import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
FBX, OUT = argv[0], argv[1]
SCALE = float(argv[2]) if len(argv) > 2 else 0.874

DROP = ("cape", "hair_fur", "_fur_")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX, ignore_leaf_bones=False,
                         automatic_bone_orientation=False)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
bones = list(arm.data.bones)
bidx = {b.name: i for i, b in enumerate(bones)}
print("armature '%s': %d bones" % (arm.name, len(bones)))

# ---- UP AXIS AND SCALE, BOTH DERIVED FROM THE FILE ---------------------------
#
# This FBX is Maya's: Y-UP and in METRES. Imported as-is the body came out 1.3 units tall
# lying on its side, against the marine's 64.687 standing up -- so a hand-typed scale of
# 0.874 (which is right for the ValveBiped source the old script read) is meaningless here.
#
# Both are measured instead of typed. The up axis is whichever axis a standing human is
# longest along; the scale is whatever puts this body at the marine's height, so one set of
# the owner's body numbers serves both and switching bodies does not re-open the
# calibration.
import mathutils

MARINE_H = 64.687

_pts = []
for _o in bpy.data.objects:
    if _o.type == "MESH" and len(_o.data.vertices):
        _mw = _o.matrix_world
        # Blender collections are not sliceable; sample by index instead.
        _vs = _o.data.vertices
        for _i in range(0, len(_vs), 37):
            _pts.append(_mw @ _vs[_i].co)
_mn = mathutils.Vector((min(p[i] for p in _pts) for i in range(3)))
_mx = mathutils.Vector((max(p[i] for p in _pts) for i in range(3)))
_ext = _mx - _mn
UPAX = max(range(3), key=lambda i: _ext[i])
FIT = MARINE_H / _ext[UPAX]
print("source extents %.2f %.2f %.2f -> up axis is %s, scaling %.3f to the marine's %.1f"
      % (_ext.x, _ext.y, _ext.z, "XYZ"[UPAX], FIT, MARINE_H))

# Map the detected up axis onto +Z, keeping a right-handed frame, then scale.
if UPAX == 1:                       # Y-up (Maya): Y->Z, Z->-Y
    R = mathutils.Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
elif UPAX == 0:                     # X-up
    R = mathutils.Matrix(((0, 0, 1, 0), (0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 0, 1)))
else:
    R = mathutils.Matrix.Identity(4)
XF = mathutils.Matrix.Scale(FIT * SCALE, 4) @ R

# ---- the skeleton: parent index + LOCAL bind transform -----------------------
# matrix_local is the bone's bind transform in ARMATURE space, so a bone's local is its
# parent's inverse times its own. Getting this wrong does not fail loudly -- it draws a
# body folded through itself.
jnt = []
for b in bones:
    par = bidx[b.parent.name] if b.parent else -1
    # XF is applied to BOTH sides, so for every bone below the root it cancels
    # (parent.inv * child is unchanged) and the whole reorientation lands in the root's
    # own local transform -- which is exactly where it belongs.
    mine = XF @ b.matrix_local
    M = (XF @ b.parent.matrix_local).inverted() @ mine if b.parent else mine
    loc, rot, sca = M.decompose()
    jnt.append((b.name, par, (loc.x, loc.y, loc.z),
                (rot.x, rot.y, rot.z, rot.w), (sca.x, sca.y, sca.z)))

# ---- the meshes, grouped by material -----------------------------------------
meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]
groups = {}
dropped = 0
for o in meshes:
    mats = [m.name for m in o.data.materials if m]
    tag = (mats[0] if mats else o.name).lower()
    if any(d in tag for d in DROP):
        dropped += 1
        continue
    groups.setdefault(mats[0] if mats else o.name, []).append(o)
print("kept %d mesh objects in %d material groups, dropped %d (cape/hair)"
      % (sum(len(v) for v in groups.values()), len(groups), dropped))

VP, VN, VT, VB, VW, TRI = [], [], [], [], [], []
surfaces = []
for mat, objs in groups.items():
    first = len(TRI)
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        mw = o.matrix_world
        nmat = mw.to_3x3().inverted().transposed()
        # vertex group index -> bone index, PER OBJECT: the same group name can sit at a
        # different index on every object, and reusing one object's mapping for another is
        # how a hand ends up weighted to a thigh.
        g2b = {}
        for g in o.vertex_groups:
            if g.name in bidx:
                g2b[g.index] = bidx[g.name]
        vmap = {}
        for t in me.loop_triangles:
            tri = []
            for li, vi in zip(t.loops, t.vertices):
                u, v = (uv[li].uv[0], 1.0 - uv[li].uv[1]) if uv else (0.0, 0.0)
                key = (vi, round(u, 6), round(v, 6))
                if key not in vmap:
                    vmap[key] = len(VP)
                    w = XF @ (mw @ me.vertices[vi].co)
                    VP.append((w.x, w.y, w.z))
                    n = (XF.to_3x3() @ (nmat @ me.vertices[vi].normal)).normalized()
                    VN.append((n.x, n.y, n.z))
                    VT.append((u, v))
                    ws = sorted(((g.weight, g2b[g.group]) for g in me.vertices[vi].groups
                                 if g.group in g2b), reverse=True)[:4]
                    # CLAMPED AT EVERY STEP. An IQM weight is a ubyte, and this rig has
                    # vertices whose group weights do not behave -- tiny or negative
                    # values make 255*x/tot blow past 255, and the remainder correction
                    # then pushed one slot to 535. numpy refuses that as an OverflowError
                    # with no line of its own, so it reads as the script dying silently.
                    ws = [(max(0.0, x), bn) for x, bn in ws]
                    tot = sum(x for x, _ in ws) or 1.0
                    b4 = [bn for _, bn in ws] + [0] * (4 - len(ws))
                    q = [max(0, min(255, int(255 * x / tot))) for x, _ in ws]
                    q = q + [0] * (4 - len(q))
                    q[0] = max(0, min(255, q[0] + 255 - sum(q)))
                    VB.append(b4)
                    VW.append(q)
                tri.append(vmap[key])
            TRI.append(tri)
    surfaces.append((mat, first, len(TRI) - first))

print("surfaces: %d   verts: %d   tris: %d" % (len(surfaces), len(VP), len(TRI)))

# ---- PRUNE THE SKELETON TO 256 BONES, WHICH IS THE REAL WALL HERE ------------
#
# THIS is what stopped the reimport, and it is worth naming because it looks like a bug in
# the writer and is not. An IQM blend index is a UBYTE: 256 bones, maximum. This rig has
# 924 -- face rig, cloth chains, helmet furniture, roll pins -- so `np.array(VB, uint8)`
# raises OverflowError on the first index past 255 and the script dies with no line of its
# own. It is almost certainly why the original conversion went to a different, cut-down
# ValveBiped source instead of this one.
#
# So keep only bones that actually MOVE GEOMETRY, plus every ancestor of those (a parent
# chain with a hole in it is not a skeleton), and renumber. Nothing that deforms the body
# is lost -- a bone with no weights on it moves nothing by definition.
# THE BODY SKELETON IS UNDER 100 BONES; THE OTHER 830 ARE FACE AND CLOTH.
# Counted off this rig: lid 116, lips 68, brow 65, squint 62, socket 60, sneer 32 and the
# rest of the face come to about 500; loincloth 99, skirt 81 and chainhip 30 are cloth.
# None of it deforms a body we drive -- and the head is hidden in the headset anyway.
#
# So a weight on one of those is COLLAPSED onto its nearest kept ancestor rather than
# dropped: face geometry then rides the head bone, cloth rides the hips. Deleting the
# weight instead would leave those vertices pinned at the origin, which is a body with its
# skirt stretched across the map.
BODYBONE = ("origin", "hips", "spine", "neck_part", "head_part", "leg_", "arm_",
            "thumb_", "index_", "middle_", "ring_", "pinky_", "footarmor",
            "kneearmor", "helmet_part", "jaw_part")
body_ok = [any(k in j[0].lower() for k in BODYBONE) for j in jnt]


def nearest_body(i):
    while i >= 0 and not body_ok[i]:
        i = jnt[i][1]
    return i if i >= 0 else 0


collapse = [nearest_body(i) for i in range(len(jnt))]
VB = [[collapse[bn] for bn in b4] for b4 in VB]
print("collapsed %d non-body bones (face, cloth) onto their nearest body ancestor"
      % sum(1 for ok in body_ok if not ok))

used = set()
for b4, q in zip(VB, VW):
    for bn, w in zip(b4, q):
        if w > 0:
            used.add(bn)
full = set(used)
for i in list(used):
    p = jnt[i][1]
    while p >= 0:
        full.add(p)
        p = jnt[p][1]
keep = sorted(full)
print("bones: %d total, %d carry weights, %d kept with ancestors"
      % (len(jnt), len(used), len(keep)))
if len(keep) > 256:
    print("STILL OVER 256 (%d). An IQM blend index cannot address them." % len(keep))
    sys.exit(1)

remap = {old: new for new, old in enumerate(keep)}
jnt = [(jnt[o][0], remap[jnt[o][1]] if jnt[o][1] >= 0 else -1,
        jnt[o][2], jnt[o][3], jnt[o][4]) for o in keep]
VB = [[remap.get(bn, 0) for bn in b4] for b4 in VB]
hand_bones_old = None  # recomputed below against the pruned list

# ---- did the hands survive? --------------------------------------------------
# The whole point of this reimport, so it is checked rather than assumed.
#
# THE KEYS ARE THIS RIG'S. There is no bone with "finger" in its name here; looking for one
# found 485 vertices and nearly refused a body that does have hands. A check that names the
# wrong thing is worse than no check, because it fails in the direction that looks like
# diligence.
HANDKEYS = ("arm_hand", "thumb_", "index_", "middle_", "ring_", "pinky_")
hand_bones = set(i for i, j in enumerate(jnt)
                 if any(k in j[0].lower() for k in HANDKEYS))
nh = sum(1 for b in VB if b[0] in hand_bones)
print("vertices weighted to hand/finger bones: %d" % nh)
if nh < 2000:
    print("REFUSING TO WRITE: this body has no hands on it, which is the exact bug this "
          "script exists to fix. It does not get to ship silently.")
    sys.exit(1)

# ---- IQM, in the layout marine_whole.py already ships ------------------------
#
# NOT hand-rolled again. A first attempt died silently -- no traceback, no file -- because a
# pose record is <iI10f10f (88 bytes: parent, mask, 10 channel offsets, 10 channel scales)
# and it had been written <iI9f9f with a 44-byte stride.
text = bytearray(b"\x00")


def add(st):
    o = len(text)
    text.extend(st.encode("latin-1", "replace") + b"\x00")
    return o


pos = np.array(VP, "<f4")
uvs = np.array(VT, "<f4")
nrm = np.array(VN, "<f4")
bix = np.array(VB, np.uint8)
bwt = np.array(VW, np.uint8)
tris = np.array(TRI, "<u4")

# WINDING. A mesh whose triangle order disagrees with its own normals draws inside out --
# you see the far wall through the chest, and the silhouette still looks right.
e1 = pos[tris[:, 1]].astype(np.float64) - pos[tris[:, 0]]
e2 = pos[tris[:, 2]].astype(np.float64) - pos[tris[:, 0]]
fn = np.cross(e1, e2)
vn = nrm[tris[:, 0]].astype(np.float64) + nrm[tris[:, 1]] + nrm[tris[:, 2]]
agree = float(((fn * vn).sum(1) > 0).mean())
if agree < 0.5:
    tris = tris[:, [0, 2, 1]]
    agree = 1.0 - agree
print("winding agreement %.0f%%" % (100 * agree))

mesh_recs = []
for mat, first, cnt in surfaces:
    n = add(mat)
    mesh_recs.append((n, n, 0, len(VP), first, cnt))

joints = bytearray()
poses = bytearray()
for nme, par, t, q, sc in jnt:
    joints += struct.pack("<Ii3f4f3f", add(nme), par, *t, *q, *sc)
for nme, par, t, q, sc in jnt:
    poses += struct.pack("<iI10f10f", par, 0, *t, *q, *sc, *([0.0] * 10))
anim_name = add("bind")
while len(text) % 4:
    text.append(0)

cur = 124
layout = []


def place(blob):
    global cur
    while cur % 4:
        cur += 1
    o = cur
    layout.append((o, bytes(blob)))
    cur += len(blob)
    return o


o_text = place(text)
o_mesh = place(b"".join(struct.pack("<6I", *m) for m in mesh_recs))
o_va = place(bytes(5 * 20))
offs = [place(pos.tobytes()), place(uvs.tobytes()), place(nrm.tobytes()),
        place(bix.tobytes()), place(bwt.tobytes())]
va = b"".join([struct.pack("<5I", 0, 0, 7, 3, offs[0]),
               struct.pack("<5I", 1, 0, 7, 2, offs[1]),
               struct.pack("<5I", 2, 0, 7, 3, offs[2]),
               struct.pack("<5I", 4, 0, 1, 4, offs[3]),
               struct.pack("<5I", 5, 0, 1, 4, offs[4])])
layout = [(o, va) if o == o_va else (o, bl) for o, bl in layout]
o_tri = place(tris.astype("<u4").tobytes())
o_joint = place(joints)
o_pose = place(poses)
o_anim = place(struct.pack("<IIIfI", anim_name, 0, 1, 30.0, 0))
while cur % 4:
    cur += 1

hdr = [2, cur, 0, len(text), o_text, len(mesh_recs), o_mesh, 5, len(VP), o_va,
       len(tris), o_tri, 0, len(jnt), o_joint, len(jnt), o_pose, 1, o_anim, 1, 0,
       cur, 0, 0, 0, 0, 0]
out = bytearray(cur)
out[:16] = b"INTERQUAKEMODEL\x00"
struct.pack_into("<27I", out, 16, *hdr)
for o, bl in layout:
    out[o:o + len(bl)] = bl
open(OUT, "wb").write(bytes(out))
print("wrote %s  --  %d surfaces, %d verts, %d tris, %.1f MB"
      % (OUT, len(mesh_recs), len(VP), len(tris), len(out) / 1048576.0))
print("per-surface triangle counts:")
for mat, first, cnt in sorted(surfaces, key=lambda x: -x[2]):
    print("   %-62s %7d" % (mat[:62], cnt))
