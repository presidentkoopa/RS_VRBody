"""Per mesh of an IQM: vertex count, height range, and how many vertices ride hand/finger or head/helmet joints."""
import struct, sys, os

HAND_WORDS = ("hand", "thumb", "index", "middle", "ring", "pinky", "arm_end", "weapon_part")
HEAD_WORDS = ("head", "helmet", "neck", "jaw", "brow", "eye", "lip", "nose", "cheek", "ear", "teeth", "tongue")


def summarise(path):
    data = open(path, "rb").read()
    hdr = struct.unpack_from("<27I", data, 16)
    (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj,
     njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = hdr

    def text(o):
        end = data.index(b"\0", otext + o)
        return data[otext + o:end].decode("latin-1")

    names = [text(struct.unpack_from("<I", data, ojoint + i * 48)[0]) for i in range(njoint)]
    pos = idx = wts = None
    for a in range(nva):
        typ, fl, fmt, size, off = struct.unpack_from("<5I", data, ova + a * 20)
        if typ == 0 and fmt == 7 and size == 3:
            pos = struct.unpack_from("<%df" % (nvert * 3), data, off)
        elif typ == 4 and fmt == 1 and size == 4:
            idx = data[off:off + nvert * 4]
        elif typ == 5 and fmt == 1 and size == 4:
            wts = data[off:off + nvert * 4]
    print("==== %s" % os.path.basename(path))
    for m in range(nmesh):
        name, mat, fv, nv, ft, nt = struct.unpack_from("<6I", data, omesh + m * 24)
        zs = [pos[3 * v + 2] for v in range(fv, fv + nv)]
        xs = [pos[3 * v] for v in range(fv, fv + nv)]
        hand = head = 0
        top = {}
        for v in range(fv, fv + nv):
            rides_hand = rides_head = False
            for k in range(4):
                w = wts[4 * v + k]
                if w == 0:
                    continue
                jn = names[idx[4 * v + k]].lower()
                top[jn] = top.get(jn, 0) + w
                if any(s in jn for s in HAND_WORDS):
                    rides_hand = True
                if any(s in jn for s in HEAD_WORDS):
                    rides_head = True
            hand += rides_hand
            head += rides_head
        best = sorted(top.items(), key=lambda kv: -kv[1])[:4]
        print("  mesh %d  verts %5d  z %6.2f..%6.2f  x %6.2f..%6.2f  hand/finger %5d  head/helmet %5d  top joints %s"
              % (m, nv, min(zs), max(zs), min(xs), max(xs), hand, head, ", ".join(n for n, _ in best)))


for p in sys.argv[1:]:
    summarise(p)
