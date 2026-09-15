"""A compiled Source model (.mdl v48 + .vvd + .dx90.vtx) to one OBJ per bodypart, plus its bones. Read-only, scratch.

usage: source_mdl_to_obj.py MODEL_BASE OUT_DIR
  MODEL_BASE: the path without extension (…/Slayer_Classic_Skins)

VVD: the vertex pool (position, normal, uv, up to 3 bone weights). VTX: per bodypart / model / LOD 0 / mesh /
strip group, an index list into the strip group's vertex list, whose origMeshVertID offsets into that mesh's range
of the model's vertices (the MDL mesh's vertexoffset plus the model's vertexindex/48 base). MDL: bodypart, model and
mesh records (material index), bones (name, parent, bind position and quaternion).

Writes OUT_DIR/<bodypart>.obj (+ .mtl naming each material), bones.json (name, parent, position in model space),
summary.txt. Units and axes are the MDL's own (Source: inches-ish, +Z up, +X forward).
"""
import json, os, struct, sys

BASE, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
mdl = open(BASE + ".mdl", "rb").read()
vvd = open(BASE + ".vvd", "rb").read()
vtx = open(BASE + ".dx90.vtx", "rb").read()

def cstr(buf, off):
    return buf[off:buf.index(b"\0", off)].decode("latin-1")

# ---------------------------------------------------------------- MDL header (v48)
o = 76 + 4 + 72 + 4
numbones, boneindex = struct.unpack_from("<ii", mdl, o); o += 8
o += 8 * 5                      # bone controllers, hitboxsets, local anims, local seqs, activitylist/events
numtextures, textureindex = struct.unpack_from("<ii", mdl, o); o += 8
o += 8                          # cdtextures
numskinref, numskinfamilies, skinindex = struct.unpack_from("<iii", mdl, o); o += 12
numbodyparts, bodypartindex = struct.unpack_from("<ii", mdl, o); o += 8

materials = []
for i in range(numtextures):
    to = textureindex + i * 64
    materials.append(cstr(mdl, to + struct.unpack_from("<i", mdl, to)[0]))

bones = []
for i in range(numbones):
    bo = boneindex + i * 216
    nameoff, parent = struct.unpack_from("<ii", mdl, bo)
    pos = struct.unpack_from("<3f", mdl, bo + 32)
    quat = struct.unpack_from("<4f", mdl, bo + 44)
    bones.append(dict(name=cstr(mdl, bo + nameoff), parent=parent, pos=pos, quat=quat))

# ---------------------------------------------------------------- VVD
ident, version, checksum, numLODs = struct.unpack_from("<4siii", vvd, 0)
lodverts = struct.unpack_from("<8i", vvd, 16)
numFixups, fixupIdx, vertIdx, tangIdx = struct.unpack_from("<iiii", vvd, 48)
assert numFixups == 0, "fixups present: not handled"
NV = lodverts[0]
VERTS = []
for i in range(NV):
    vo = vertIdx + i * 48
    w = struct.unpack_from("<3f", vvd, vo)
    b = struct.unpack_from("<3B", vvd, vo + 12)
    nb = vvd[vo + 15]
    p = struct.unpack_from("<3f", vvd, vo + 16)
    n = struct.unpack_from("<3f", vvd, vo + 28)
    uv = struct.unpack_from("<2f", vvd, vo + 40)
    VERTS.append((p, n, uv, [(b[k], w[k]) for k in range(nb)]))

# ---------------------------------------------------------------- VTX (v7) header
vtx_version, vtx_cache, maxBonesPerStrip, maxBonesPerTri, maxBonesPerVert, vtx_checksum, vtx_numLODs, matRepIdx, vtx_numBodyParts, vtx_bpIdx = struct.unpack_from("<iiHHiiiiii", vtx, 0)

summary = ["model %s: %d bones, %d materials, %d skin families, %d bodyparts, %d vertices" % (os.path.basename(BASE), numbones, numtextures, numskinfamilies, numbodyparts, NV)]
for bpi in range(numbodyparts):
    bp = bodypartindex + bpi * 16
    bp_name = cstr(mdl, bp + struct.unpack_from("<i", mdl, bp)[0])
    nummodels, base, modelindex = struct.unpack_from("<iii", mdl, bp + 4)
    vbp = vtx_bpIdx + bpi * 8
    vtx_nummodels, vtx_modelIdx = struct.unpack_from("<ii", vtx, vbp)
    for mi in range(nummodels):
        mo = bp + modelindex + mi * 148
        mname = mdl[mo:mo + 64].split(b"\0")[0].decode("latin-1")
        mtype, radius, nummeshes, meshindex, numvertices, vertexindex = struct.unpack_from("<ifiiii", mdl, mo + 64)
        if nummeshes == 0:
            continue
        model_vbase = vertexindex // 48
        vm = vbp + vtx_modelIdx + mi * 8
        vtx_numLODs_m, vtx_lodIdx = struct.unpack_from("<ii", vtx, vm)
        lod = vm + vtx_lodIdx                           # LOD 0
        vtx_nummeshes, vtx_meshIdx, switchPoint = struct.unpack_from("<iif", vtx, lod)
        obj_v, obj_vt, obj_vn, faces, used = [], [], [], [], {}
        tricount = 0
        for mei in range(nummeshes):
            me = mo + meshindex + mei * 116
            material, modelindex_m, m_numvertices, m_vertexoffset = struct.unpack_from("<iiii", mdl, me)
            vmesh = lod + vtx_meshIdx + mei * 9
            numStripGroups, sgIdx, mflags = struct.unpack_from("<iiB", vtx, vmesh)
            mat = materials[material] if material < len(materials) else "mat%d" % material
            faces.append("usemtl %s" % mat)
            for sgi in range(numStripGroups):
                sg = vmesh + sgIdx + sgi * 25
                sg_numVerts, sg_vertIdx, sg_numIdx, sg_idxIdx, sg_numStrips, sg_stripIdx, sg_flags = struct.unpack_from("<iiiiiiB", vtx, sg)
                vids = []
                for k in range(sg_numVerts):
                    vv = sg + sg_vertIdx + k * 9
                    origMeshVertID, = struct.unpack_from("<H", vtx, vv + 4)
                    vids.append(model_vbase + m_vertexoffset + origMeshVertID)
                idx = struct.unpack_from("<%dH" % sg_numIdx, vtx, sg + sg_idxIdx)
                for t in range(0, sg_numIdx, 3):
                    tri = []
                    for k in (idx[t], idx[t + 1], idx[t + 2]):
                        g = vids[k]
                        if g not in used:
                            used[g] = len(used) + 1
                            p, n, uv, bw = VERTS[g]
                            obj_v.append("v %.5f %.5f %.5f" % p)
                            obj_vt.append("vt %.5f %.5f" % (uv[0], 1.0 - uv[1]))
                            obj_vn.append("vn %.5f %.5f %.5f" % n)
                        tri.append(used[g])
                    faces.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (tri[0], tri[0], tri[0], tri[2], tri[2], tri[2], tri[1], tri[1], tri[1]))
                    tricount += 1
        path = os.path.join(OUT, "%s.obj" % bp_name)
        with open(path, "w") as fh:
            fh.write("mtllib %s.mtl\n" % bp_name)
            fh.write("\n".join(obj_v + obj_vt + obj_vn + faces) + "\n")
        mats_used = sorted({f.split(" ", 1)[1] for f in faces if f.startswith("usemtl")})
        with open(os.path.join(OUT, "%s.mtl" % bp_name), "w") as fh:
            for m_ in mats_used:
                fh.write("newmtl %s\nmap_Kd %s.vtf.png\n" % (m_, m_))
        summary.append("  bodypart %-24s model %-50s meshes %d verts %d tris %d materials %s" % (bp_name, mname, nummeshes, len(used), tricount, mats_used))

json.dump(bones, open(os.path.join(OUT, "bones.json"), "w"), indent=1)
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(summary) + "\n")
print("\n".join(summary))
