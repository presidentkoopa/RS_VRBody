"""Cut chosen MESHES out of an IQM into a new IQM, skeleton and skinning intact.

    python iqm_submesh.py IN.iqm OUT.iqm 8 9 10 11 12 13 14
    python iqm_submesh.py IN.iqm OUT.iqm --list

WHY. To show the player's head to OTHER viewpoints but not to him, the head has to be its
own actor. It was done by spawning a SECOND COPY OF THE WHOLE BODY and hiding every surface
that was not the head -- which is a spare marine that has to suppress itself every tic, and
the first time that suppression failed he got four hands and a pair of arms hanging in the
rest pose out at his sides. The owner's answer was the right one: make a head model.

WHAT IT DOES. Keeps every vertex, every triangle, the whole skeleton and all animation data,
and rewrites only the MESH TABLE to the meshes asked for. Unreferenced vertices and triangles
simply stop being drawn -- nothing indexes them -- so no index remapping is needed and no
skinning can be broken by a renumbering mistake. The file is a little larger than a perfectly
tight cut and exactly as correct, which is the right trade for a tool that must not silently
corrupt a rig.

The skeleton is kept WHOLE on purpose: the head's bones are meaningless without their parents
up the spine, and a reach chain or a bone driver naming a joint has to find it.
"""
import struct
import sys

HDR = "<16s27I"
FMT_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 2, 7: 4, 8: 8}


def read(path):
    b = open(path, "rb").read()
    f = struct.unpack_from(HDR, b, 0)
    magic = f[0]
    if not magic.startswith(b"INTERQUAKEMODEL"):
        raise SystemExit("%s is not an IQM" % path)
    keys = ("version filesize flags num_text ofs_text num_meshes ofs_meshes "
            "num_vertexarrays num_vertexes ofs_vertexarrays num_triangles ofs_triangles "
            "ofs_adjacency num_joints ofs_joints num_poses ofs_poses num_anims ofs_anims "
            "num_frames num_framechannels ofs_frames ofs_bounds num_comment ofs_comment "
            "num_extensions ofs_extensions").split()
    h = dict(zip(keys, f[1:]))
    return b, h


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    b, h = read(src)

    text = b[h["ofs_text"]:h["ofs_text"] + h["num_text"]]

    def name(off):
        e = text.index(b"\0", off)
        return text[off:e].decode("utf8", "replace")

    meshes = []
    for i in range(h["num_meshes"]):
        o = h["ofs_meshes"] + i * 24
        meshes.append(list(struct.unpack_from("<6I", b, o)))

    if "--list" in sys.argv:
        for i, m in enumerate(meshes):
            print("%2d  %-52s  %6d verts %6d tris" % (i, name(m[0]), m[3], m[5]))
        return

    want = [int(a) for a in sys.argv[3:] if a.isdigit()]
    if not want:
        raise SystemExit("name at least one mesh index (or --list)")
    bad = [i for i in want if i < 0 or i >= len(meshes)]
    if bad:
        raise SystemExit("no such mesh index: %s (file has 0..%d)" % (bad, len(meshes) - 1))

    # Vertex arrays, copied whole. Each array's payload is num_vertexes * size * format width.
    vas = []
    for i in range(h["num_vertexarrays"]):
        o = h["ofs_vertexarrays"] + i * 20
        typ, flags, fmt, size, off = struct.unpack_from("<5I", b, o)
        width = FMT_SIZE.get(fmt)
        if width is None:
            raise SystemExit("vertex array format %d not handled" % fmt)
        nbytes = h["num_vertexes"] * size * width
        vas.append(dict(typ=typ, flags=flags, fmt=fmt, size=size,
                        data=b[off:off + nbytes]))

    tris = b[h["ofs_triangles"]:h["ofs_triangles"] + h["num_triangles"] * 12]
    joints = b[h["ofs_joints"]:h["ofs_joints"] + h["num_joints"] * 48]
    poses = b[h["ofs_poses"]:h["ofs_poses"] + h["num_poses"] * 88]
    anims = b[h["ofs_anims"]:h["ofs_anims"] + h["num_anims"] * 20]
    frames = b[h["ofs_frames"]:h["ofs_frames"] + h["num_frames"] * h["num_framechannels"] * 2]

    # ---- lay the new file out, recomputing every offset ----
    out = bytearray(16 + 27 * 4)
    def put(blob):
        while len(out) % 4:
            out.append(0)
        at = len(out)
        out.extend(blob)
        return at

    ofs_text = put(text)
    ofs_meshes = put(b"".join(struct.pack("<6I", *meshes[i]) for i in want))
    ofs_tris = put(tris)
    ofs_joints = put(joints) if h["num_joints"] else 0
    ofs_poses = put(poses) if h["num_poses"] else 0
    ofs_anims = put(anims) if h["num_anims"] else 0
    ofs_frames = put(frames) if h["num_frames"] else 0

    va_records = []
    for va in vas:
        va["ofs"] = put(va["data"])
    ofs_vas = put(b"".join(struct.pack("<5I", v["typ"], v["flags"], v["fmt"], v["size"], v["ofs"])
                           for v in vas))

    hdr = [1, 0, h["flags"], len(text), ofs_text,
           len(want), ofs_meshes,
           len(vas), h["num_vertexes"], ofs_vas,
           h["num_triangles"], ofs_tris, 0,
           h["num_joints"], ofs_joints,
           h["num_poses"], ofs_poses,
           h["num_anims"], ofs_anims,
           h["num_frames"], h["num_framechannels"], ofs_frames, 0,
           0, 0, 0, 0]
    hdr[1] = len(out)
    struct.pack_into(HDR, out, 0, b"INTERQUAKEMODEL\0", *hdr)
    open(dst, "wb").write(bytes(out))

    kept = sum(meshes[i][5] for i in want)
    print("%s -> %s" % (src, dst))
    for i in want:
        print("   kept mesh %2d  %s" % (i, name(meshes[i][0])))
    print("   %d triangles drawn, %d joints kept, %d bytes" % (kept, h["num_joints"], len(out)))


main()
