"""The RS hand (hand_left.iqm): joints, baked frames, skinning. Read-only.

Frames of its one clip are the poses: 0 open, 3 fist, 8 index resting on the trigger.
Everything is in the IQM FILE's own space and units.
"""
import struct
import numpy as np

HAND = "E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm"
FINGERS = {
    "index":  ["INDEX_BASE_joint", "INDEX_MID_joint", "INDEX_TOP_joint", "INDEX_UP_TOP_joint"],
    "middle": ["MIDDLE_F_BASE_joint", "MIDDLE_F_MID_joint", "MIDDLE_F_TOP_joint", "MIDDLE_F_UP_TOP_joint"],
    "ring":   ["RING_BASE_joint", "RING_MID_joint", "RING_TOP_joint", "RING_UP_TOP_joint"],
    "pinky":  ["PINK_BASE_joint", "PINK_MID_joint", "PINK_TOP_joint", "PINK_UP_TOP_joint"],
    "thumb":  ["THUMB_BASE_joint", "THUMB_MID_joint", "THUMB_TOP_joint", "THUMB_UP_TOP_joint"],
}


def quat_to_mat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    s = 2.0 / n if n > 0 else 0.0
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ])


def trs(t, q, s):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(q) * np.asarray(s)[None, :]
    m[:3, 3] = t
    return m


class Hand:
    def __init__(self, path=HAND):
        d = open(path, "rb").read()
        assert d[:16] == b"INTERQUAKEMODEL\0"
        h = struct.unpack_from("<27I", d, 16)
        (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj,
         njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = h

        def text(o):
            e = d.index(b"\0", otext + o)
            return d[otext + o:e].decode("latin-1")

        self.names, self.parents, base_local = [], [], []
        for i in range(njoint):
            v = struct.unpack_from("<Ii3f4f3f", d, ojoint + i * 48)
            self.names.append(text(v[0]))
            self.parents.append(v[1])
            base_local.append((np.array(v[2:5]), np.array(v[5:9]), np.array(v[9:12])))
        self.index = {n: i for i, n in enumerate(self.names)}
        self.base_local = base_local
        self.base_global = self.globals([trs(*b) for b in base_local])
        self.base_inv = [np.linalg.inv(g) for g in self.base_global]

        # Frames: poses carry per-channel offset/scale; frames are uint16 channel values.
        poses = [struct.unpack_from("<iI10f10f", d, opose + i * 88) for i in range(npose)]
        raw = np.frombuffer(d, dtype="<u2", count=nframe * nfch, offset=oframe)
        self.nframe = nframe
        self.frame_local = []   # frame -> list of (t, q, s) local
        p = 0
        for f in range(nframe):
            locs = []
            for j in range(npose):
                parent, mask = poses[j][0], poses[j][1]
                off, sc = poses[j][2:12], poses[j][12:22]
                ch = []
                for c in range(10):
                    val = off[c]
                    if mask & (1 << c):
                        val += raw[p] * sc[c]
                        p += 1
                    ch.append(val)
                locs.append((np.array(ch[0:3]), np.array(ch[3:7]), np.array(ch[7:10])))
            self.frame_local.append(locs)

        # Mesh arrays.
        arrays = {}
        for a in range(nva):
            typ, fl, fmt, size, off = struct.unpack_from("<5I", d, ova + a * 20)
            if fmt == 7:
                arrays[typ] = np.frombuffer(d, dtype="<f4", count=nvert * size, offset=off).reshape(nvert, size).astype(np.float64)
            elif fmt == 1:
                arrays[typ] = np.frombuffer(d, dtype="u1", count=nvert * size, offset=off).reshape(nvert, size)
        self.pos = arrays[0]
        self.uv = arrays.get(1)
        self.bidx = arrays[4].astype(int)
        self.bwt = arrays[5].astype(np.float64) / 255.0
        self.tris = np.frombuffer(d, dtype="<u4", count=ntri * 3, offset=otri).reshape(ntri, 3)

    def globals(self, local_mats):
        g = [None] * len(local_mats)
        for i, m in enumerate(local_mats):
            p = self.parents[i]
            g[i] = m if p < 0 else g[p] @ m
        return g

    def local_mats(self, locs):
        return [trs(*l) for l in locs]

    def skin(self, global_mats):
        skinm = np.array([global_mats[j] @ self.base_inv[j] for j in range(len(global_mats))])   # J x 4 x 4
        hp = np.c_[self.pos, np.ones(len(self.pos))]
        out = np.zeros((len(self.pos), 3))
        for k in range(4):
            m = skinm[self.bidx[:, k]]                                   # V x 4 x 4
            out += self.bwt[:, k:k + 1] * np.einsum("vij,vj->vi", m, hp)[:, :3]
        tw = self.bwt.sum(axis=1, keepdims=True)
        return out / np.where(tw > 0, tw, 1.0)


if __name__ == "__main__":
    h = Hand()
    print("joints %d  frames %d  verts %d  tris %d" % (len(h.names), h.nframe, len(h.pos), len(h.tris)))
    print("mesh bounds", h.pos.min(axis=0).round(2), h.pos.max(axis=0).round(2))
    for f in (0, 3, 8):
        g = h.globals(h.local_mats(h.frame_local[f]))
        print("---- frame %d" % f)
        palm = g[h.index["HANDPALM_joint"]][:3, 3]
        print("  palm %s" % palm.round(2))
        for name, chain in FINGERS.items():
            pts = [g[h.index[j]][:3, 3] for j in chain]
            print("  %-6s base %s  tip %s  base->tip %s" % (name, pts[0].round(2), pts[-1].round(2), (pts[-1] - pts[0]).round(2)))
