"""Decode Source VTF (7.2, DXT5 / DXT1 / BGRA8888 / BGR888, largest mip) to PNG. usage: vtf2png.py OUT_DIR FILE.vtf ..."""
import struct, sys, os
import numpy as np
from PIL import Image

def rgb565(c):
    return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], -1).astype(np.float32)

def decode_bc(data, w, h, dxt5):
    bw, bh = (w + 3) // 4, (h + 3) // 4
    bs = 16 if dxt5 else 8
    blk = np.frombuffer(data, dtype=np.uint8, count=bw * bh * bs).reshape(bh * bw, bs)
    co = 8 if dxt5 else 0
    c0 = blk[:, co].astype(np.int32) | (blk[:, co + 1].astype(np.int32) << 8)
    c1 = blk[:, co + 2].astype(np.int32) | (blk[:, co + 3].astype(np.int32) << 8)
    cidx = blk[:, co + 4].astype(np.uint32) | (blk[:, co + 5].astype(np.uint32) << 8) | (blk[:, co + 6].astype(np.uint32) << 16) | (blk[:, co + 7].astype(np.uint32) << 24)
    p0, p1 = rgb565(c0), rgb565(c1)
    four = np.ones(len(blk), bool) if dxt5 else (c0 > c1)
    p2 = np.where(four[:, None], (2 * p0 + p1) / 3, (p0 + p1) / 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) / 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)
    out = np.zeros((bh * 4, bw * 4, 3), dtype=np.float32)
    ar = np.arange(len(blk))
    for py in range(4):
        for px in range(4):
            ci = ((cidx >> np.uint32(2 * (py * 4 + px))) & np.uint32(3)).astype(np.int64)
            out[py::4, px::4] = pal[ar, ci].reshape(bh, bw, 3)
    return out[:h, :w]

def read_vtf(path):
    d = open(path, "rb").read()
    w, h = struct.unpack_from("<HH", d, 16)
    fmt, = struct.unpack_from("<i", d, 52)
    if fmt in (13, 20):
        need = ((w + 3) // 4) * ((h + 3) // 4) * 8
        return decode_bc(d[len(d) - need:], w, h, False)
    if fmt == 15:
        need = ((w + 3) // 4) * ((h + 3) // 4) * 16
        return decode_bc(d[len(d) - need:], w, h, True)
    if fmt in (12, 16, 3):
        ch = 3 if fmt == 3 else 4
        need = w * h * ch
        a = np.frombuffer(d[len(d) - need:], dtype=np.uint8).reshape(h, w, ch).astype(np.float32)
        return a[..., [2, 1, 0]]
    raise SystemExit("%s: format %d not handled" % (path, fmt))

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
for f in sys.argv[2:]:
    img = read_vtf(f)
    name = os.path.splitext(os.path.basename(f))[0]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(os.path.join(OUT, name + ".png"))
    print("decoded", name, img.shape[1], "x", img.shape[0])
