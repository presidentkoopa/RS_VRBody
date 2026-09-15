"""The engine's follow-hand placement, shared by the seat solver and the in-game grip renders.

models.cpp FSpriteModelFrame::ObjectToWorldMatrix, steps 3-5, after the controller frame and the 0.01 unit
scale that every follow-hand model shares (so they cancel between a hand and a gun on the same controller).
VSMatrix post-multiplies, so in written order:
    S(xs, zs, ys) . T((xo+px)/xs, (zo+pz)/zs, (yo+py)/ys) . Ry(-yaw) Rz(pitch) Rx(-roll) . Ry(-ao) Rz(po) Rx(-ro)
The model-space vertex is file (x, z, y) for both MD3 and IQM. Worked out: world = S.R.v + (xo+px, zo+pz, yo+py),
so a placement offset moves the model by exactly its own amount, unscaled and unturned, in engine axes
(x, y up, z) = placement (ofs_x, ofs_z, ofs_y).
"""
import os
import numpy as np

INI = os.path.join(os.environ["USERPROFILE"], "Documents", "My Games", "DoomXR", "doomxr.ini")


def read_ini(path=INI):
    vals = {}
    for line in open(path, encoding="latin-1"):
        if "=" in line and (line.startswith("wm_") or line.startswith("rs_hw_")):
            k, v = line.strip().split("=", 1)
            try:
                vals.setdefault(k, float(v))
            except ValueError:
                pass
    return vals


def placement(prefix, ini, override=None):
    """A placement set: the ini's values (or the given defaults), then any override dict on top."""
    g = lambda s, d: ini.get(prefix + s, d)
    pl = dict(ofs=[g("_ofs_x", 0.0), g("_ofs_y", 0.0), g("_ofs_z", 0.0)],
              yaw=g("_yaw", 0.0), pitch=g("_pitch", 0.0), roll=g("_roll", 0.0),
              scale=g("_scale", 1.0) if g("_scale", 1.0) > 0 else 1.0,
              axis=[g(s, 1.0) if g(s, 1.0) > 0 else 1.0 for s in ("_scale_x", "_scale_y", "_scale_z")])
    if override:
        for k, v in override.items():
            pl[k] = v
    return pl


def rot(deg, axis):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s, 0],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s, 0],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c), 0],
                     [0, 0, 0, 1]])


def chain(scale, offset, ao, po, ro, pl):
    xs, ys, zs = scale
    xo, yo, zo = offset
    px, py, pz = pl["ofs"]
    S = np.diag([xs * pl["scale"] * pl["axis"][0], zs * pl["scale"] * pl["axis"][2], ys * pl["scale"] * pl["axis"][1], 1.0])
    T = np.eye(4); T[:3, 3] = [(xo + px) / xs, (zo + pz) / zs, (yo + py) / ys]
    M = S @ T
    M = M @ rot(-pl["yaw"], (0, 1, 0)) @ rot(pl["pitch"], (0, 0, 1)) @ rot(-pl["roll"], (1, 0, 0))
    M = M @ rot(-ao, (0, 1, 0)) @ rot(po, (0, 0, 1)) @ rot(-ro, (1, 0, 0))
    return M


def to_engine(file_verts, M):
    """File-space vertices -> engine space (x, y up, z) after the chain."""
    e = np.c_[file_verts[:, 0], file_verts[:, 2], file_verts[:, 1], np.ones(len(file_verts))]
    return (e @ M.T)[:, :3]


def engine_to_filelike(p):
    """Engine (x, y up, z) back to file-like axes (z up) for Blender; the same swap for every model."""
    return p[:, [0, 2, 1]]


HAND_DEF = {  # RS_WorldHands MODELDEF RS_HandWorldMain / Off
    "main": dict(scale=(-1.0, 1.0, 1.0), offset=(0.0, 0.1, -0.05), ao=0.0, po=90.0, ro=-90.0, prefix="rs_hw_main"),
    "off": dict(scale=(1.0, 1.0, 1.0), offset=(0.0, 0.1, -0.05), ao=0.0, po=90.0, ro=-90.0, prefix="rs_hw_off"),
}

W = "E:/DOOMWork/RS_VR_Weapons/"

# BASE ORIENTATION FIXES, proposed and not yet in any MODELDEF: (AngleOffset, PitchOffset, RollOffset) that stand a
# crookedly authored mesh straight (barrel along file +x, up along file +z) so its seat can work like any other gun's.
# Rifle.md3 lies along (0.489, 0.493, -0.719) with its sight up (0.516, 0.501, 0.695): solved in seat_solve notes.
BASE_FIX = {"WM_PropRifle": (-55.18, 31.04, 35.82)}


def read_props():
    """Every WM_Prop* MODELDEF block: hand, md3 path, skin, Scale, Offset, placement prefix."""
    import re
    md = open(W + "MODELDEF.txt", encoding="latin-1").read()
    props = {}
    for blk in re.finditer(r"Model\s+(WM_Prop\w+)\s*\{(.*?)\}", md, re.S):
        name, body = blk.group(1), blk.group(2)
        g = lambda pat: re.search(pat, body)
        path, mdl, skin = g(r'Path\s+"([^"]+)"'), g(r'Model\s+0\s+"([^"]+)"'), g(r'Skin\s+0\s+"([^"]+)"')
        sc, of, pc = g(r'\n\s*Scale\s+([-\d. ]+)'), g(r'\n\s*Offset\s+([-\d. ]+)'), g(r'PlacementCVars\s+(\w+)')
        if not (path and mdl and sc and pc):
            continue
        props[name] = dict(
            hand="main" if "FollowMainHand" in body else "off",
            md3=W + path.group(1) + "/" + mdl.group(1),
            skin=W + path.group(1) + "/" + skin.group(1) if skin else None,
            scale=tuple(float(x) for x in sc.group(1).split()),
            offset=tuple(float(x) for x in of.group(1).split()) if of else (0.0, 0.0, 0.0),
            base=BASE_FIX.get(name, tuple(float(g(r'%sOffset\s+([-\d.]+)' % k).group(1)) if g(r'%sOffset\s+([-\d.]+)' % k) else 0.0
                                          for k in ("Angle", "Pitch", "Roll"))),
            prefix=pc.group(1))
    return props
