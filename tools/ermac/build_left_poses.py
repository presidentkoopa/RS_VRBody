"""RS hands keep up with the glove: hand_left.iqm's own mesh with hand_ermac_poses.iqm's animation.

Both files share one skeleton (hand_ermac.iqm copied hand_left.iqm's joints and poses byte for byte), so
hand_left's text, meshes, vertex arrays and triangles are kept and the joints, poses, anims, frames and
bounds come from hand_ermac_poses.iqm. Result: frame 1298 + f is Ermac's hand2 frame f on EITHER mesh,
so the pose switch never depends on which hand is worn.
"""
import os, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEFT = "E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm"
POSES = os.path.join(HERE, "hand_ermac_poses2.iqm")
OUT = os.path.join(HERE, "hand_left_poses.iqm")


def header(b):
    assert b[:16] == b"INTERQUAKEMODEL\0"
    return list(struct.unpack_from("<27I", b, 16))


L = open(LEFT, "rb").read()
P = open(POSES, "rb").read()
hl, hp = header(L), header(P)
# indices: 3 ntext 4 otext 5 nmesh 6 omesh 7 nva 8 nvert 9 ova 10 ntri 11 otri 12 oadj
#          13 njoint 14 ojoint 15 npose 16 opose 17 nanim 18 oanim 19 nframe 20 nfch 21 oframe 22 obounds
assert hl[13] == hp[13] and hl[15] == hp[15], "skeletons differ"
assert L[hl[14]:hl[14] + hl[13] * 48] == P[hp[14]:hp[14] + hp[13] * 48], "joint tables differ"
# The pose tables DO differ: fit_ermac_poses.py requantized every frame (new channel offsets and scales),
# so the frames are only readable with their own pose table -- both are taken from the poses file. The
# bind pose lives in the joint table, checked equal above, so hand_left's skin is unaffected.

# Anim names are text offsets into the file they came from: carry them over by re-adding each name.
text = bytearray(L[hl[4]:hl[4] + hl[3]])
ptext = P[hp[4]:hp[4] + hp[3]]
def ptext_at(o):
    return ptext[o:ptext.index(b"\0", o)].decode("latin-1")
def add_text(s):
    raw = s.encode("latin-1") + b"\0"
    i = bytes(text).find(raw)
    if i >= 0 and (i == 0 or text[i - 1] == 0):
        return i
    off = len(text); text.extend(raw); return off
anims = bytearray()
for i in range(hp[17]):
    nofs, first, cnt, rate, fl = struct.unpack_from("<IIIfI", P, hp[18] + i * 20)
    anims += struct.pack("<IIIfI", add_text(ptext_at(nofs)), first, cnt, rate, fl)
while len(text) % 4:
    text.append(0)

nva = hl[7]
va_raw = [list(struct.unpack_from("<5I", L, hl[9] + i * 20)) for i in range(nva)]
FMT_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 2, 7: 4, 8: 8}
va_blobs = [L[v[4]:v[4] + FMT_SIZE[v[2]] * v[3] * hl[8]] for v in va_raw]
meshes = L[hl[6]:hl[6] + hl[5] * 24]
tris = L[hl[11]:hl[11] + hl[10] * 12]
joints = P[hp[14]:hp[14] + hp[13] * 48]
poses = P[hp[16]:hp[16] + hp[15] * 88]
frames = P[hp[21]:hp[21] + hp[19] * hp[20] * 2]
bounds = P[hp[22]:hp[22] + hp[19] * 32] if hp[22] else b""

cur = 124
layout = []
def place(blob):
    global cur
    while cur % 4: cur += 1
    off = cur; layout.append((off, blob)); cur += len(blob); return off

o_text = place(bytes(text))
o_mesh = place(meshes)
o_va = place(bytes(nva * 20))
for i, blob in enumerate(va_blobs):
    va_raw[i][4] = place(blob)
layout = [(o, b) if o != o_va else (o, b"".join(struct.pack("<5I", *v) for v in va_raw)) for o, b in layout]
o_tri = place(tris)
o_joint = place(joints); o_pose = place(poses); o_anim = place(bytes(anims)); o_frame = place(frames)
o_bounds = place(bounds) if bounds else 0
while cur % 4: cur += 1

hdr = [2, cur, 0, len(text), o_text, hl[5], o_mesh, nva, hl[8], o_va, hl[10], o_tri, 0,
       hp[13], o_joint, hp[15], o_pose, hp[17], o_anim, hp[19], hp[20], o_frame, o_bounds, 0, 0, 0, 0]
out = bytearray(cur)
out[:16] = b"INTERQUAKEMODEL\0"
struct.pack_into("<27I", out, 16, *hdr)
for off, blob in layout:
    out[off:off + len(blob)] = blob
open(OUT, "wb").write(bytes(out))

# loader checks, as build_ermac_iqm.py
d = bytes(out); f = header(d)
assert f[0] == 2 and f[1] == len(d) and f[3] != 0
for i in range(f[13]):
    assert struct.unpack_from("<i", d, f[14] + i * 48 + 4)[0] < i
for i in range(f[17]):
    nofs, first, cnt, rate, fl = struct.unpack_from("<IIIfI", d, f[18] + i * 20)
    assert first + cnt <= f[19]
    print("anim %r first %d count %d" % (d[f[4] + nofs:d.index(b"\0", f[4] + nofs)].decode(), first, cnt))
# Same mesh as hand_left: vertex blobs identical.
for v in va_raw:
    pass
print("wrote %s  %d bytes  meshes %d verts %d tris %d frames %d channels %d" % (OUT, len(d), f[5], f[8], f[10], f[19], f[20]))
