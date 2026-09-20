"""Render a rig's HAND at each wrist roll, so the roll can be JUDGED instead of guessed.

    python render_wrist.py OUT_PREFIX [marine|praetor]

Writes OUT_PREFIX_000.png, _090.png, _180.png, _270.png -- forearm and hand only, close
up, lit identically so the four can be compared honestly.

WHY THIS EXISTS. rs_body_wrist_turn offers four quarter turns because a rig's idea of
"up" and a controller's need not agree, and which one is right cannot be measured from
outside a headset. That is a fine reason to give the owner a switch. It is NOT a reason
to have never looked: the SHAPE of a wrist at each quarter turn is decided entirely by
the file, and the file is right here.

UNLIKE render_rig.py, THIS SKINS. That one draws the bind pose straight out of the vertex
array, which is all a chain diagram needs. A wrist ROLL only exists once vertices follow
the bone, so this reads blendindexes and blendweights and does the linear blend itself:
v' = sum_i w_i * (G'_i * inverse(G_i) * v).

No Blender, no engine -- it depends on nothing but the file we ship. Untextured grey, so
no Doom Eternal texel ever lands in an image.
"""
import math
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

RIGS = {
    "marine": dict(
        path="E:/DOOMWork/RS_VRBody/models/marine/marine_whole.iqm",
        fore="bip_lowerArm_R", hand="bip_hand_R",
        axis=np.array([0.0, 0.0, -1.0]),   # measured: these bones run down local -Z
    ),
    "praetor": dict(
        path="E:/DOOMWork/RS_VRBody/models/praetor/praetor_hand_rt.iqm",
        fore="ValveBiped.Bip01_R_Forearm", hand="ValveBiped.Bip01_R_Hand",
        axis=np.array([1.0, 0.0, 0.0]),    # ValveBiped bones run down local +X
    ),
}

IQM_POSITION, IQM_NORMAL, IQM_BLENDINDEXES, IQM_BLENDWEIGHTS = 0, 2, 4, 5
FMT_UBYTE, FMT_USHORT, FMT_FLOAT = 1, 3, 7


def load(path):
    b = open(path, "rb").read()
    h = struct.unpack_from("<27I", b, 16)
    (_v, _f, _fl, n_text, o_text, _nm, _om, n_va, n_vert, o_va,
     n_tri, o_tri, _adj, n_joint, o_joint) = h[:15]
    text = b[o_text:o_text + n_text]

    def s(off):
        return text[off:text.index(b"\0", off)].decode("utf8", "replace")

    P = N = BI = BW = None
    for i in range(n_va):
        typ, _f2, fmt, size, off = struct.unpack_from("<5I", b, o_va + i * 20)
        if typ == IQM_POSITION and fmt == FMT_FLOAT:
            P = np.frombuffer(b, "<f4", n_vert * size, off).reshape(n_vert, size)[:, :3].astype(np.float64)
        elif typ == IQM_NORMAL and fmt == FMT_FLOAT:
            N = np.frombuffer(b, "<f4", n_vert * size, off).reshape(n_vert, size)[:, :3].astype(np.float64)
        elif typ == IQM_BLENDINDEXES:
            # UBYTE OR USHORT. Assuming a byte is wrong on any rig past 255 bones, and
            # that assumption cost two failed imports before it was believed.
            dt = {FMT_UBYTE: "<u1", FMT_USHORT: "<u2"}.get(fmt)
            if dt is None:
                raise SystemExit("blendindexes format %d not handled" % fmt)
            BI = np.frombuffer(b, dt, n_vert * size, off).reshape(n_vert, size).astype(np.int32)
        elif typ == IQM_BLENDWEIGHTS:
            if fmt == FMT_UBYTE:
                BW = np.frombuffer(b, "<u1", n_vert * size, off).reshape(n_vert, size).astype(np.float64) / 255.0
            elif fmt == FMT_FLOAT:
                BW = np.frombuffer(b, "<f4", n_vert * size, off).reshape(n_vert, size).astype(np.float64)
    T = np.frombuffer(b, "<u4", n_tri * 3, o_tri).reshape(n_tri, 3)

    names, parents, loc = [], [], []
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
        loc.append(M)
    return P, N, T, names, parents, loc, BI, BW


def globals_of(parents, loc):
    G = []
    for i in range(len(loc)):
        G.append(G[parents[i]] @ loc[i] if parents[i] >= 0 else loc[i].copy())
    return G


def axis_angle(axis, deg):
    a = axis / max(np.linalg.norm(axis), 1e-12)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    x, y, z = a
    R = np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                  [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                  [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])
    M = np.eye(4)
    M[:3, :3] = R
    return M


def skin(P, N, BI, BW, Gb, Gp):
    D = np.array([Gp[i] @ np.linalg.inv(Gb[i]) for i in range(len(Gb))])
    out = np.zeros_like(P)
    outn = np.zeros_like(N)
    for k in range(BI.shape[1]):
        w = BW[:, k]
        m = w > 0
        if not m.any():
            continue
        Mk = D[BI[m, k]]
        out[m] += w[m, None] * (np.einsum("nij,nj->ni", Mk[:, :3, :3], P[m]) + Mk[:, :3, 3])
        outn[m] += w[m, None] * np.einsum("nij,nj->ni", Mk[:, :3, :3], N[m])
    return out, outn


def render(P, N, T, keep, W, H, label, out):
    lo, hi = P[keep].min(0), P[keep].max(0)
    pad = 26
    sc = min((W - pad * 2) / max(hi[0] - lo[0], 1e-6),
             (H - pad * 2) / max(hi[2] - lo[2], 1e-6))
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    img = np.zeros((H, W, 3))
    zb = np.full((H, W), 1e18)
    light = np.array([-0.35, -0.8, 0.5])
    light /= np.linalg.norm(light)
    sx = W / 2 + (P[:, 0] - cx) * sc
    sy = H / 2 - (P[:, 2] - cz) * sc
    nn = np.linalg.norm(N, axis=1, keepdims=True)
    nn[nn == 0] = 1
    shade = np.clip((N / nn) @ light, 0, 1) * 0.72 + 0.20
    vis = keep[T].all(1)
    for tri in T[vis]:
        a, b, c = tri
        ax, ay = sx[a], sy[a]
        bx, by = sx[b], sy[b]
        cx2, cy = sx[c], sy[c]
        x0 = int(max(0, math.floor(min(ax, bx, cx2))))
        x1 = int(min(W - 1, math.ceil(max(ax, bx, cx2))))
        y0 = int(max(0, math.floor(min(ay, by, cy))))
        y1 = int(min(H - 1, math.ceil(max(ay, by, cy))))
        if x1 < x0 or y1 < y0:
            continue
        den = (by - cy) * (ax - cx2) + (cx2 - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        xs = xs + 0.5
        ys = ys + 0.5
        l1 = ((by - cy) * (xs - cx2) + (cx2 - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx2) + (ax - cx2) * (ys - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inside.any():
            continue
        z = l1 * P[a, 1] + l2 * P[b, 1] + l3 * P[c, 1]
        g = l1 * shade[a] + l2 * shade[b] + l3 * shade[c]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        win = inside & (z < sub)
        sub[win] = z[win]
        img[y0:y1 + 1, x0:x1 + 1][win] = np.stack([g, g, g], -1)[win]
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    ImageDraw.Draw(im).text((10, 8), label, fill=(255, 220, 90))
    im.save(out)
    print("wrote", out)


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "wrist"
    which = sys.argv[2] if len(sys.argv) > 2 else "marine"
    rig = RIGS[which]
    P, N, T, names, parents, loc, BI, BW = load(rig["path"])
    if BI is None or BW is None:
        raise SystemExit("no blend data in %s -- cannot skin" % rig["path"])
    if N is None:
        N = np.zeros_like(P)
    idx = {n: i for i, n in enumerate(names)}
    jh, jf = idx[rig["hand"]], idx[rig["fore"]]

    under = set()
    for i in range(len(names)):
        j = i
        while j >= 0:
            if j in (jh, jf):
                under.add(i)
                break
            j = parents[j]
    keep = np.isin(BI, list(under)).any(1) & (BW.sum(1) > 0)
    print("%s: %d of %d verts ride the hand/forearm" % (which, keep.sum(), len(P)))

    Gb = globals_of(parents, loc)
    for deg in (0, 90, 180, 270):
        loc2 = [m.copy() for m in loc]
        loc2[jh] = loc2[jh] @ axis_angle(rig["axis"], deg)
        Gp = globals_of(parents, loc2)
        Pp, Np = skin(P, N, BI, BW, Gb, Gp)
        render(Pp, Np, T, keep, 460, 460, "%s wrist %d" % (which, deg),
               "%s_%03d.png" % (prefix, deg))

    # THE SPLIT TEST. This rig has NO forearm twist bone -- bip_lowerArm_R parents
    # bip_hand_R directly -- so every degree of roll is taken by one joint and the skin
    # between them shears into the classic candy-wrapper pinch. A real forearm pronates
    # along its whole length. So: give the FOREARM a share of the roll and the hand the
    # remainder, and see whether the pinch goes away. If it does, the fix is distribution,
    # not a smaller angle and not a new bone.
    for share in (0.0, 0.5, 0.7, 1.0):
        deg = 180.0
        loc2 = [m.copy() for m in loc]
        loc2[jf] = loc2[jf] @ axis_angle(rig["axis"], deg * share)
        loc2[jh] = loc2[jh] @ axis_angle(rig["axis"], deg * (1.0 - share))
        Gp = globals_of(parents, loc2)
        Pp, Np = skin(P, N, BI, BW, Gb, Gp)
        render(Pp, Np, T, keep, 460, 460,
               "%s 180 deg, forearm takes %d%%" % (which, int(share * 100)),
               "%s_split%02d.png" % (prefix, int(share * 100)))



if __name__ == "__main__":
    main()
