"""Render a body's RIG for the README: untextured, flat-shaded, chains marked.

    python render_rig.py OUT.png

WHY UNTEXTURED. .gitignore keeps this repo's meshes and textures off a PUBLIC remote
because they are Doom Eternal assets, and a render of them is the same asset in image
form -- which is why `renders/` is ignored too. A flat-shaded rig is our own work: the
chains, the joints the solver drives, the proportions the seats are measured against.
Nothing of theirs survives the grey.

No Blender. This reads the IQM directly and rasterises with a z-buffer, because the
whole point is that it depends on nothing but the file we ship.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MARINE = r"E:\DOOMWork\RS_VRBody\models\marine\marine_whole.iqm"
PRAETOR = r"E:\DOOMWork\RS_VRBody\models\praetor\praetor_body.iqm"
OUT = sys.argv[1] if len(sys.argv) > 1 else "rig.png"

# The joints each reach chain drives, per rig family. These are the arms and legs the
# solver actually owns -- chains 0/1 and 2/3 -- so the picture shows what moves.
CHAINS = {
    "marine": [("bip_upperArm_R", "bip_lowerArm_R", "bip_hand_R"),
               ("bip_upperArm_L", "bip_lowerArm_L", "bip_hand_L"),
               ("bip_hip_R", "bip_knee_R", "bip_foot_R"),
               ("bip_hip_L", "bip_knee_L", "bip_foot_L")],
    "praetor": [("ValveBiped.Bip01_R_UpperArm", "ValveBiped.Bip01_R_Forearm", "ValveBiped.Bip01_R_Hand"),
                ("ValveBiped.Bip01_L_UpperArm", "ValveBiped.Bip01_L_Forearm", "ValveBiped.Bip01_L_Hand"),
                ("ValveBiped.Bip01_R_Thigh", "ValveBiped.Bip01_R_Calf", "ValveBiped.Bip01_R_Foot"),
                ("ValveBiped.Bip01_L_Thigh", "ValveBiped.Bip01_L_Calf", "ValveBiped.Bip01_L_Foot")],
}
SPINE = {
    "marine": ["bip_pelvis", "bip_spine_0", "bip_spine_1", "bip_spine_2", "bip_neck", "bip_head"],
    "praetor": ["ValveBiped.Bip01_Pelvis", "ValveBiped.Bip01_Spine", "ValveBiped.Bip01_Spine1",
                "ValveBiped.Bip01_Spine2", "ValveBiped.Bip01_Spine4", "ValveBiped.Bip01_Neck1",
                "ValveBiped.Bip01_Head1"],
}


def load(path):
    import struct
    b = open(path, "rb").read()
    h = struct.unpack_from("<27I", b, 16)
    (_v, _f, _fl, n_text, o_text, n_mesh, o_mesh, n_va, n_vert, o_va,
     n_tri, o_tri, _adj, n_joint, o_joint, *_rest) = h
    text = b[o_text:o_text + n_text]

    def s(off):
        return text[off:text.index(b"\0", off)].decode("utf8", "replace")

    P = N = None
    for i in range(n_va):
        typ, _fl2, fmt, size, off = struct.unpack_from("<5I", b, o_va + i * 20)
        if typ == 0 and fmt == 7:
            P = np.frombuffer(b, "<f4", n_vert * size, off).reshape(n_vert, size)[:, :3].astype(np.float64)
        if typ == 2 and fmt == 7:
            N = np.frombuffer(b, "<f4", n_vert * size, off).reshape(n_vert, size)[:, :3].astype(np.float64)
    T = np.frombuffer(b, "<u4", n_tri * 3, o_tri).reshape(n_tri, 3)

    names, parents, locals_ = [], [], []
    for i in range(n_joint):
        o = o_joint + i * 48
        names.append(s(struct.unpack_from("<I", b, o)[0]))
        parents.append(struct.unpack_from("<i", b, o + 4)[0])
        t = np.array(struct.unpack_from("<3f", b, o + 8))
        q = np.array(struct.unpack_from("<4f", b, o + 20))
        sc = np.array(struct.unpack_from("<3f", b, o + 36))
        x, y, z, w = q / max(np.linalg.norm(q), 1e-12)
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                      [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * sc
        M[:3, 3] = t
        locals_.append(M)
    G = []
    for i in range(n_joint):
        G.append(G[parents[i]] @ locals_[i] if parents[i] >= 0 else locals_[i])
    return P, N, T, names, [g[:3, 3] for g in G]


def render(path, style, W, H, pad=28):
    P, N, T, names, J = load(path)
    if N is None:
        N = np.zeros_like(P)
    idx = {n: i for i, n in enumerate(names)}

    # Straight on, from the front: x across, z up, y into the screen.
    lo, hi = P.min(0), P.max(0)
    sc = min((W - pad * 2) / (hi[0] - lo[0]), (H - pad * 2) / (hi[2] - lo[2]))
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2

    def px(p):
        return (W / 2 + (p[0] - cx) * sc, H / 2 - (p[2] - cz) * sc)

    img = np.zeros((H, W, 3), np.float64)
    zbuf = np.full((H, W), 1e18)
    light = np.array([-0.35, -0.8, 0.5])
    light /= np.linalg.norm(light)

    sx = W / 2 + (P[:, 0] - cx) * sc
    sy = H / 2 - (P[:, 2] - cz) * sc
    depth = P[:, 1]
    shade = np.clip(N @ light, 0, 1) * 0.72 + 0.20

    for a, bi, c in T:
        xs = (sx[a], sx[bi], sx[c])
        ys = (sy[a], sy[bi], sy[c])
        x0, x1 = int(max(0, min(xs))), int(min(W - 1, max(xs)) + 1)
        y0, y1 = int(max(0, min(ys))), int(min(H - 1, max(ys)) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        ax, ay = xs[0], ys[0]
        e0x, e0y = xs[1] - ax, ys[1] - ay
        e1x, e1y = xs[2] - ax, ys[2] - ay
        den = e0x * e1y - e1x * e0y
        if abs(den) < 1e-9:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        wx, wy = xx - ax, yy - ay
        u = (wx * e1y - e1x * wy) / den
        v = (e0x * wy - wx * e0y) / den
        m = (u >= 0) & (v >= 0) & (u + v <= 1)
        if not m.any():
            continue
        z = depth[a] + u * (depth[bi] - depth[a]) + v * (depth[c] - depth[a])
        g = shade[a] + u * (shade[bi] - shade[a]) + v * (shade[c] - shade[a])
        sub = zbuf[y0:y1, x0:x1]
        hit = m & (z < sub)
        sub[hit] = z[hit]
        tone = np.stack([g * 0.80, g * 0.83, g * 0.88], -1)
        img[y0:y1, x0:x1][hit] = tone[hit]

    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)

    # The chains the solver drives, over the top, so the picture shows the RIG.
    for a, b_, c in CHAINS[style]:
        if a not in idx:
            continue
        pts = [px(J[idx[a]]), px(J[idx[b_]]), px(J[idx[c]])]
        d.line(pts, fill=(255, 196, 0), width=3)
        for p in pts:
            d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=(255, 196, 0))
    sp = [px(J[idx[n]]) for n in SPINE[style] if n in idx]
    if len(sp) > 1:
        d.line(sp, fill=(90, 190, 255), width=2)
        for p in sp:
            d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=(90, 190, 255))
    return im


W, H = 620, 900
left = render(MARINE, "marine", W, H)
right = render(PRAETOR, "praetor", W, H)
out = Image.new("RGB", (W * 2, H + 44), (14, 14, 16))
out.paste(left, (0, 44))
out.paste(right, (W, 44))
d = ImageDraw.Draw(out)
d.text((16, 14), "Eternal marine -- 152 joints", fill=(228, 228, 232))
d.text((W + 16, 14), "Praetor / Dark Ages -- 83 joints", fill=(228, 228, 232))
d.text((W * 2 - 430, 14), "yellow: the four reach chains   blue: spine", fill=(150, 150, 158))
out.save(OUT)
print("wrote %s  (%dx%d)" % (OUT, out.width, out.height))
