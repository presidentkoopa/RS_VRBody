"""Step A.2: put Ermac's hand2.md3 open frame onto our hand's bind pose.

His frame is a LEFT hand: fingers along +x, spread along z (thumb and index at +z), palm facing -y.
Ours (hand_left.iqm file) is a RIGHT hand: fingers along -z, spread along x (index +x), palm facing +y.
The fixed map  x -> -z,  y -> -y,  z -> +x  turns his into ours and is a reflection (det -1), which is
the mirror left to right. Triangle winding is reversed with it so faces keep facing out.

Then scale, a small rotation and a translation are fitted by ICP, matching the PALM AND FINGERS only:
his cuff and our long wrist stub are left out of the match.

Writes ermac_aligned.npz (verts, normals, uvs, tris) and ermac_aligned.obj, and a scene for an overlay.
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "E:/DOOMWork/tools")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from md3 import MD3Model
from hand_iqm import Hand

REST_FRAME = 150
M = np.array([[0.0, 0.0, 1.0],      # our x  <- his z
              [0.0, -1.0, 0.0],     # our y  <- -his y
              [-1.0, 0.0, 0.0]])    # our z  <- -his x
assert abs(np.linalg.det(M) + 1.0) < 1e-9

m = MD3Model.load("E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand2.md3")
s = m.surfaces[0]
ev = np.array(s.verts[REST_FRAME]) @ M.T
en = np.array(s.normals[REST_FRAME]) @ M.T
euv = np.array(s.st)
etri = np.array(s.triangles)[:, [0, 2, 1]]          # reflection: reverse winding

h = Hand()
ov = h.pos
# our palm + fingers: below the wrist crease (bind z < 2); his: drop the cuff end (largest z after mapping)
ours_match = ov[ov[:, 2] < 2.0]


def fingers_forward_extent(v):
    return v[:, 2].max() - v[:, 2].min()


# Initial scale from the length along the finger axis (z): ours from the wrist crease to the tips.
ours_len = 2.0 - ov[:, 2].min()
e_zmin, e_zmax = ev[:, 2].min(), ev[:, 2].max()
# his cuff is roughly the last 22% of his length; start with the part before it
his_len = (e_zmax - e_zmin) * 0.78
scale = ours_len / his_len
ev_s = ev * scale
# translate so the fingertip ends and the spread centres line up
t = np.array([ours_match[:, 0].mean() - ev_s[:, 0].mean(),
              ours_match[:, 1].mean() - ev_s[:, 1].mean(),
              ov[:, 2].min() - ev_s[:, 2].min()])
R = np.eye(3)
print("initial scale %.4f translate %s" % (scale, t.round(3)))


def nearest(a, b):
    """For each row of a, the nearest row of b (brute force in chunks)."""
    idx = np.empty(len(a), dtype=int); dist = np.empty(len(a))
    for i in range(0, len(a), 512):
        d = ((a[i:i + 512, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        j = d.argmin(axis=1)
        idx[i:i + 512] = j
        dist[i:i + 512] = np.sqrt(d[np.arange(len(j)), j])
    return idx, dist


def apply(v):
    return (v * scale) @ R.T + t


for it in range(40):
    cur = apply(ev)
    his_match_mask = cur[:, 2] < 2.0 + 0.5       # his palm and fingers, in our frame
    hm = cur[his_match_mask]
    # symmetric: ours -> his and his -> ours
    i1, d1 = nearest(ours_match, hm)
    i2, d2 = nearest(hm, ours_match)
    src = np.vstack([hm[i1], hm])                  # his points (current)
    dst = np.vstack([ours_match, ours_match[i2]])  # matched ours
    keep = np.concatenate([d1, d2]) < np.percentile(np.concatenate([d1, d2]), 90)
    src, dst = src[keep], dst[keep]
    # similarity fit src -> dst (Umeyama), composed onto the current transform
    cs, cd = src.mean(axis=0), dst.mean(axis=0)
    A, B = src - cs, dst - cd
    U, S, Vt = np.linalg.svd(B.T @ A)
    D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    Rs = U @ D @ Vt
    ss = (S * np.diag(D)).sum() / (A ** 2).sum()
    ts = cd - ss * (Rs @ cs)
    # compose: new(v) = ss*Rs*(scale*R*v + t) + ts
    R = Rs @ R
    scale = ss * scale
    t = ss * (Rs @ t) + ts
    err = float(np.concatenate([d1, d2]).mean())
    if it % 5 == 0 or it == 39:
        ang = np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
        print("  iter %2d  mean gap %.3f  scale %.4f  extra turn %.2f deg" % (it, err, scale, ang))

av = apply(ev)
an = en @ R.T
an /= np.linalg.norm(an, axis=1, keepdims=True)
np.savez(os.path.join(HERE, "ermac_aligned.npz"), verts=av, normals=an, uvs=euv, tris=etri,
         scale=scale, R=R, t=t, M=M, rest_frame=REST_FRAME)
with open(os.path.join(HERE, "ermac_aligned.obj"), "w") as fh:
    for v in av:
        fh.write("v %.5f %.5f %.5f\n" % tuple(v))
    for uv in euv:
        fh.write("vt %.5f %.5f\n" % (uv[0], 1.0 - uv[1]))
    for a, b, c in etri:
        fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
print("aligned: bounds %s .. %s  (ours %s .. %s)" % (av.min(axis=0).round(2), av.max(axis=0).round(2), ov.min(axis=0).round(2), ov.max(axis=0).round(2)))

OUT = os.path.join(HERE, "out").replace("\\", "/")
scene = {"objs": [{"path": os.path.join(HERE, "ermac_aligned.obj").replace("\\", "/"),
                   "texture": "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand_HD.png"},
                  {"path": os.path.join(HERE, "ours_bind.obj").replace("\\", "/"),
                   "texture": "E:/DOOMWork/RS_WorldHands/models/hands/hand_basecolor.png"}],
         "shots": [{"file": OUT + "/overlay_palm.png", "cam": [0.0, 70.0, -6.0], "look": [0.0, 0.0, -6.0], "lens": 50},
                   {"file": OUT + "/overlay_side.png", "cam": [70.0, 0.0, -6.0], "look": [0.0, 0.0, -6.0], "lens": 50}]}
json.dump(scene, open(os.path.join(HERE, "scene_overlay.json"), "w"), indent=1)
scene2 = {"objs": [scene["objs"][0]],
          "shots": [{"file": OUT + "/aligned_palm.png", "cam": [0.0, 70.0, -6.0], "look": [0.0, 0.0, -6.0], "lens": 50},
                    {"file": OUT + "/aligned_back.png", "cam": [0.0, -70.0, -6.0], "look": [0.0, 0.0, -6.0], "lens": 50}]}
json.dump(scene2, open(os.path.join(HERE, "scene_aligned.json"), "w"), indent=1)
