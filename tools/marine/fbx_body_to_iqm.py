"""Re-import a rigged body FBX as ONE IQM -- hands attached, nothing cut.

    blender -b -noaudio --factory-startup -P fbx_body_to_iqm.py -- <in.fbx> <out.iqm> [scale]

WHY THIS EXISTS. The previous import of this body wrote THREE files -- a body and two
hands -- because the hands arrived as their own bodyparts in the source. Nothing was cut,
but the result is the same thing the owner banned: hands that are separate actors with no
place of their own on the body. Rendering the body alone drew it with no hands; rendering
the hand files beside it put them at its FEET, because each had been re-origined on its
own palm.

So this imports the WHOLE THING in one pass and writes one file, every mesh in the body's
own coordinates, one skeleton. What the engine gets is a body with hands on it.

Blender reads the FBX; the IQM is written here rather than exported, because GZDoom wants
IQM and Blender does not write one.
"""
import os
import struct
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC, OUT = argv[0], argv[1]
SCALE = float(argv[2]) if len(argv) > 2 else 1.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=SRC, use_anim=False, ignore_leaf_bones=False,
                         automatic_bone_orientation=False)

arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]
if not arms:
    raise SystemExit("no armature in %s -- this importer needs a rigged body" % SRC)
arm = max(arms, key=lambda a: len(a.data.bones))
print("armature '%s': %d bones, %d meshes" % (arm.name, len(arm.data.bones), len(meshes)))

# ---- the skeleton, in the armature's own space ------------------------------
bones = list(arm.data.bones)
bidx = {b.name: i for i, b in enumerate(bones)}
parents = [bidx[b.parent.name] if b.parent else -1 for b in bones]
# IQM wants each joint's LOCAL transform. matrix_local is the bone's rest in armature
# space, so a child's local is parent_inverse * child.
locals_ = []
for i, b in enumerate(bones):
    M = b.matrix_local
    if b.parent:
        M = b.parent.matrix_local.inverted() @ M
    locals_.append(M)

# ---- the meshes -------------------------------------------------------------
# One vertex per (vertex, uv) pair so a UV seam does not smear, and the four heaviest
# bone weights per vertex, which is what IQM carries.
VP, VN, VT, VB, VW, MESHES = [], [], [], [], [], []
for o in meshes:
    me = o.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data if me.uv_layers.active else None
    mw = o.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    gname = {vg.index: vg.name for vg in o.vertex_groups}
    vmap, tris = {}, []
    first = len(VP)
    for t in me.loop_triangles:
        tri = []
        for li, vi in zip(t.loops, t.vertices):
            u, v = (uv[li].uv[0], uv[li].uv[1]) if uv else (0.0, 0.0)
            key = (vi, round(u, 6), round(v, 6))
            if key not in vmap:
                vmap[key] = len(VP)
                w = mw @ me.vertices[vi].co
                VP.append((w.x * SCALE, w.y * SCALE, w.z * SCALE))
                n = (nm @ me.vertices[vi].normal).normalized()
                VN.append((n.x, n.y, n.z))
                VT.append((u, 1.0 - v))
                gw = sorted(((g.weight, gname.get(g.group, "")) for g in me.vertices[vi].groups),
                            reverse=True)[:4]
                gw = [(wt, bidx[nm2]) for wt, nm2 in gw if nm2 in bidx and wt > 0]
                tot = sum(wt for wt, _ in gw) or 1.0
                b4 = [bi for _, bi in gw] + [0] * (4 - len(gw))
                w4 = [int(round(255 * wt / tot)) for wt, _ in gw] + [0] * (4 - len(gw))
                d = 255 - sum(w4)
                w4[0] = max(0, min(255, w4[0] + d))
                VB.append(b4)
                VW.append(w4)
            tri.append(vmap[key])
        tris.append(tri)
    mat = me.materials[0].name if me.materials and me.materials[0] else "default"
    MESHES.append((o.name, mat, first, len(VP) - first, tris))
    print("   %-34s %6d verts  %6d tris  mat %s" % (o.name, len(VP) - first, len(tris), mat))

# ---- CULL THE SKELETON TO WHAT ACTUALLY SKINS ANYTHING ----------------------
#
# This source carries 924 bones. Two problems: IQM blend indices are a BYTE, so anything
# past 255 cannot be addressed at all, and most of them are helpers, twist pins and hair
# that skin nothing we keep. So take the bones that real vertices are weighted to, add
# their ancestors (a parent chain with a hole in it is not a skeleton), and renumber.
used = set()
for b4, w4 in zip(VB, VW):
    for bi, wt in zip(b4, w4):
        if wt > 0:
            used.add(bi)
for bi in list(used):
    p = parents[bi]
    while p >= 0:
        used.add(p)
        p = parents[p]
keep = sorted(used)
remap = {old_i: new_i for new_i, old_i in enumerate(keep)}
print("skeleton: %d bones -> %d that skin geometry (with ancestors)" % (len(bones), len(keep)))
# USHORT indices, not ubyte. This rig skins with 845 bones even after culling -- armour
# plates and cloth, all of them real -- and a byte cannot address past 255. The loader
# takes IQM_USHORT at size 4 (models_iqm.cpp:422), so the limit was my assumption and not
# the format's. The cull still runs: 924 -> 845 drops the helpers that skin nothing.
IDX_FMT, IDX_PACK = (3, "<4H") if len(keep) > 255 else (1, "<4B")
print("blend indices: %s" % ("ushort" if IDX_FMT == 3 else "ubyte"))
bones = [bones[i] for i in keep]
locals_ = [locals_[i] for i in keep]
parents = [remap[parents[i]] if parents[i] >= 0 else -1 for i in keep]
VB = [[remap.get(bi, 0) for bi in b4] for b4 in VB]

# ---- write the IQM ----------------------------------------------------------
text = bytearray(b"\0")
strings = {}


def S(s):
    if s in strings:
        return strings[s]
    strings[s] = len(text)
    text.extend(s.encode("utf8") + b"\0")
    return strings[s]


mesh_recs, tri_flat = [], []
for name, mat, first, nv, tris in MESHES:
    mesh_recs.append((S(name), S(mat), first, nv, len(tri_flat), len(tris)))
    for t in tris:
        tri_flat.extend(t)
joint_recs = []
for i, b in enumerate(bones):
    M = locals_[i]
    t = M.to_translation() * SCALE
    q = M.to_quaternion()
    sc = M.to_scale()
    joint_recs.append((S(b.name), parents[i], (t.x, t.y, t.z),
                       (q.x, q.y, q.z, q.w), (sc.x, sc.y, sc.z)))

HDR = 124
blobs, offs = [], {}


def put(key, data, align=4):
    while (HDR + sum(len(b) for b in blobs)) % align:
        blobs.append(b"\0")
    offs[key] = HDR + sum(len(b) for b in blobs)
    blobs.append(data)


put("text", bytes(text), 1)
put("mesh", b"".join(struct.pack("<6I", *m) for m in mesh_recs))
va = []
put("vp", b"".join(struct.pack("<3f", *p) for p in VP))
put("vt", b"".join(struct.pack("<2f", *p) for p in VT))
put("vn", b"".join(struct.pack("<3f", *p) for p in VN))
put("vb", b"".join(struct.pack(IDX_PACK, *p) for p in VB))
put("vw", b"".join(struct.pack("<4B", *p) for p in VW))
put("tri", b"".join(struct.pack("<I", i) for i in tri_flat))
put("joint", b"".join(struct.pack("<Ii3f4f3f", j[0], j[1], *j[2], *j[3], *j[4]) for j in joint_recs))
va_recs = [(0, 0, 7, 3, offs["vp"]), (1, 0, 7, 2, offs["vt"]), (2, 0, 7, 3, offs["vn"]),
           (4, 0, IDX_FMT, 4, offs["vb"]), (5, 0, 1, 4, offs["vw"])]
put("va", b"".join(struct.pack("<5I", *v) for v in va_recs))

body = b"".join(blobs)
size = HDR + len(body)
hdr = struct.pack("<16s27I", b"INTERQUAKEMODEL\0", 2, size, 0,
                  len(text), offs["text"], len(mesh_recs), offs["mesh"],
                  len(va_recs), len(VP), offs["va"],
                  len(tri_flat) // 3, offs["tri"], 0,
                  len(joint_recs), offs["joint"], 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
open(OUT, "wb").write(hdr + body)
print("\nwrote %s -- %d meshes, %d verts, %d tris, %d joints"
      % (OUT, len(mesh_recs), len(VP), len(tri_flat) // 3, len(joint_recs)))
