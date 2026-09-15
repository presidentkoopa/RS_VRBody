"""Step A.1: Ermac's hand2.md3 open frames and our hand's bind mesh, side by side, for choosing a rest shape.

Writes (next to this script):
  ermac_fNNN.obj      hand2 frame NNN, as authored (a LEFT hand), with UVs
  ours_bind.obj       hand_left.iqm's bind mesh, with UVs
  ours_joints.json    our 22 joints' bind positions and parents
Prints per frame: bounds, the three principal extents (the smallest is how flat the hand is), and
where the fingertip-most vertices are, so the flattest, most open frame can be picked as the rest.
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand

ERMAC = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3"
FRAMES = [150, 151, 152, 153]


def write_obj(path, verts, uvs, tris, flip_v=True):
    with open(path, "w") as fh:
        for v in verts:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for uv in uvs:
            fh.write("vt %.5f %.5f\n" % (uv[0], (1.0 - uv[1]) if flip_v else uv[1]))
        for a, b, c in tris:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))


def principal(verts):
    c = verts.mean(axis=0)
    _, s, vt = np.linalg.svd(verts - c, full_matrices=False)
    proj = (verts - c) @ vt.T
    ext = proj.max(axis=0) - proj.min(axis=0)
    return c, vt, ext


m = MD3Model.load(ERMAC)
surf = m.surfaces[0]
print("hand2.md3: %d frames, surface '%s', %d verts, %d tris" % (m.num_frames, surf.name, surf.num_verts, surf.num_triangles))
tris = np.array(surf.triangles)
uvs = np.array(surf.st)
for f in FRAMES:
    v = np.array(surf.verts[f])
    c, axes, ext = principal(v)
    write_obj(os.path.join(HERE, "ermac_f%03d.obj" % f), v, uvs, tris)
    print("  f%03d  bounds %s .. %s  principal extents %s (smallest = thickness)"
          % (f, v.min(axis=0).round(2), v.max(axis=0).round(2), ext.round(2)))

h = Hand()
write_obj(os.path.join(HERE, "ours_bind.obj"), h.pos, h.uv, h.tris)
c, axes, ext = principal(h.pos)
print("ours bind: %d verts, bounds %s .. %s, principal extents %s" % (len(h.pos), h.pos.min(axis=0).round(2), h.pos.max(axis=0).round(2), ext.round(2)))
joints = []
for i, n in enumerate(h.names):
    joints.append({"name": n, "parent": h.parents[i], "pos": h.base_global[i][:3, 3].tolist()})
json.dump({"joints": joints}, open(os.path.join(HERE, "ours_joints.json"), "w"), indent=1)
for j in joints:
    print("  %-22s parent %3d  %s" % (j["name"], j["parent"], np.round(j["pos"], 2)))
