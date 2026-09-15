# LEG MOCKUP: the Slayer legs under the VR torso, each leg a two-bone solve from the hip to a foot planted on the
# floor. Headless Blender, scratch only.
#   blender -b --factory-startup -P leg_mockup.py -- OUT_PREFIX LEG_RT_IQM LEG_LF_IQM TEX_DIR TORSO_MDL TORSO_TEX
#
# Frame: the Slayer FILE frame (+X left, -Y forward, +Z up, map units, feet at origin), as ik_mockup.py.
# The torso is placed exactly as ik_mockup.py build_torso (the owner's fit 0.75 / tall 1.4, its shoulder point on the
# Slayer shoulder), so the hip check below is against the same body the arm mockups show.
#
# Per leg: hip = the Slayer leg_upper joint moved with the body (crouch lowers it, a turn yaws it about the body
# centre); ankle target = a planted foot on the floor (z = ankle height), which does NOT move with the body; knee
# = the arms' solve_free (soft reach, capped stretch, pole projection) with the pole forward and a little out.
# Upper leg swings from its bind direction to hip->knee, lower leg to knee->ankle; the foot subtree stays level
# with its own planted yaw (so it sits flat on the floor however the knee bends).
import bpy, sys, os, struct, math
from mathutils import Vector, Quaternion, Matrix

A = sys.argv[sys.argv.index('--') + 1:]
OUT, LEG_RT, LEG_LF, TEX_DIR, TORSO, TORSO_TEX = A[:6]

STRETCH_MAX = 1.05          # legs barely stretch: a straight standing leg should stay straight, not grow
SOFT_START = 0.96
POLE_FWD, POLE_OUT = 1.0, 0.25
UP = Vector((0, 0, 1)); FWD = Vector((0, -1, 0))
SIDE_X = {'rt': -1.0, 'lf': 1.0}

def clamp(x, lo, hi): return lo if x < lo else hi if x > hi else x

# ------------------------------------------------------------------ readers (as ik_mockup.py)
def read_iqm(path):
    d = open(path, 'rb').read()
    h = struct.unpack_from('<27I', d, 16)
    (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj, njoint, ojoint,
     npose, opose, nanim, oanim, nframe, nfc, oframe, obounds, ncom, ocom, next_, oext) = h
    text = d[otext:otext + ntext]
    def s(o): return text[o:text.index(b'\0', o)].decode('latin-1')
    arr = {}
    for i in range(nva):
        t, fl, f, sz, off = struct.unpack_from('<5I', d, ova + i * 20)
        arr[t] = (f, sz, off)
    def get(t, n, ch):
        f, sz, off = arr[t]
        return [struct.unpack_from('<' + ch * sz, d, off + v * sz * struct.calcsize(ch)) for v in range(n)]
    pos = get(0, nvert, 'f')
    uv = get(1, nvert, 'f') if 1 in arr else None
    bidx = get(4, nvert, 'H' if arr[4][0] == 3 else 'B')
    bwt = get(5, nvert, 'B' if arr[5][0] == 1 else 'f')
    tris = [struct.unpack_from('<3I', d, otri + i * 12) for i in range(ntri)]
    meshes = []
    for i in range(nmesh):
        n, m, fv, nv, ft, nt = struct.unpack_from('<6I', d, omesh + i * 24)
        meshes.append((s(n), s(m), fv, nv, ft, nt))
    joints = []
    for i in range(njoint):
        v = struct.unpack_from('<Ii3f4f3f', d, ojoint + i * 48)
        joints.append((s(v[0]), v[1], v[2:5], v[5:9], v[9:12]))
    wp, wr, ws = [], [], []
    for nm, par, t, r, sc in joints:
        q = Quaternion((r[3], r[0], r[1], r[2])); tv = Vector(t); sv = Vector(sc)
        if par < 0:
            wp.append(tv); wr.append(q); ws.append(sv)
        else:
            lt = Vector((tv.x * ws[par].x, tv.y * ws[par].y, tv.z * ws[par].z))
            wp.append(wp[par] + wr[par] @ lt); wr.append(wr[par] @ q)
            ws.append(Vector((sv.x * ws[par].x, sv.y * ws[par].y, sv.z * ws[par].z)))
    return dict(pos=pos, uv=uv, bidx=bidx, bwt=bwt, tris=tris, meshes=meshes,
                names=[j[0] for j in joints], parents=[j[1] for j in joints], jpos=wp)

def read_mdl(path):
    d = open(path, 'rb').read()
    scale = struct.unpack_from('<3f', d, 8); trans = struct.unpack_from('<3f', d, 20)
    nskins, sw, sh, nverts, ntris, nframes = struct.unpack_from('<6i', d, 48)
    o = 84
    for _ in range(nskins):
        g, = struct.unpack_from('<i', d, o); o += 4
        if g == 0: o += sw * sh
        else:
            nb, = struct.unpack_from('<i', d, o); o += 4 + 4 * nb + nb * sw * sh
    st = [struct.unpack_from('<3i', d, o + i * 12) for i in range(nverts)]; o += nverts * 12
    tris = [struct.unpack_from('<4i', d, o + i * 16) for i in range(ntris)]; o += ntris * 16
    o += 4 + 24
    vb = d[o:o + nverts * 4]
    pos = [tuple(scale[k] * vb[i * 4 + k] + trans[k] for k in range(3)) for i in range(nverts)]
    return pos, st, tris, sw, sh

mats = {}
def material(key, tex):
    if key in mats: return mats[key]
    m = bpy.data.materials.new(key); m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if tex and os.path.exists(tex) and bsdf:
        node = m.node_tree.nodes.new('ShaderNodeTexImage'); node.image = bpy.data.images.load(tex, check_existing=True)
        m.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        print('NO TEXTURE for', key, tex)
    mats[key] = m
    return m

def add_mesh(name, verts, faces, loop_uvs, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uvl = me.uv_layers.new()
    for poly in me.polygons:
        for k, li in enumerate(poly.loop_indices):
            uvl.data[li].uv = loop_uvs[poly.index][k]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)

def clear_scene():
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes): bpy.data.meshes.remove(me)
    for cam in list(bpy.data.cameras): bpy.data.cameras.remove(cam)

# ------------------------------------------------------------------ rig
bpy.ops.wm.read_factory_settings(use_empty=True)
LEGS = {'rt': read_iqm(LEG_RT), 'lf': read_iqm(LEG_LF)}
tpos, tst, ttris, tsw, tsh = read_mdl(TORSO)

RIG = {}
for s, m in LEGS.items():
    J = {n: i for i, n in enumerate(m['names'])}
    children = {}
    for i, p in enumerate(m['parents']): children.setdefault(p, []).append(i)
    def subtree(root, children=children):
        out, st = set(), [root]
        while st:
            j = st.pop(); out.add(j); st.extend(children.get(j, []))
        return out
    jp = m['jpos']
    up, lo, ft = J['leg_upper_' + s], J['leg_lower_' + s], J['leg_foot_' + s]
    RIG[s] = dict(m=m, jp=jp, H0=jp[up], Kb=jp[lo], Ab=jp[ft], Lup=(jp[lo] - jp[up]).length, Llo=(jp[ft] - jp[lo]).length,
                  dup_b=(jp[lo] - jp[up]).normalized(), dlo_b=(jp[ft] - jp[lo]).normalized(),
                  upper=subtree(up) - subtree(lo), lower=subtree(lo) - subtree(ft), foot=subtree(ft))

def solve_leg(H, Aw, Lup, Llo, pole):
    to = Aw - H; raw = to.length
    aim = to / raw
    nat = Lup + Llo; start = nat * SOFT_START
    if raw > start:
        span = nat - start
        soft = start + span * (1.0 - math.exp(-(raw - start) / span)); stretch = raw / soft
    else:
        soft = raw; stretch = 1.0
    sc = min(stretch, STRETCH_MAX)
    Lu, Ll = Lup * sc, Llo * sc
    reach = clamp(sc * soft, abs(Lu - Ll) * 1.001 + 0.01, (Lu + Ll) * 0.999)
    ang = math.acos(clamp((Lu * Lu + reach * reach - Ll * Ll) / (2 * Lu * reach), -1, 1))
    pp = pole - aim * pole.dot(aim)
    if pp.length < 1e-4: pp = FWD.copy()
    pp.normalize()
    axis = aim.cross(pp).normalized()
    K = H + (Quaternion(axis, ang) @ aim) * Lu
    A_solved = H + aim * reach
    return dict(K=K, A=A_solved, Lu=Lu, Ll=Ll, stretch=stretch, gap=(Aw - A_solved).length)

def leg_transforms(s, body_T, H, sv, foot_yaw):
    r = RIG[s]; jp = r['jp']
    T = [Matrix.Identity(4) for _ in jp]
    dup = (sv['K'] - H).normalized(); dlo = (sv['A'] - sv['K']).normalized()
    R_up = (body_T.to_3x3().to_quaternion() @ r['dup_b']).rotation_difference(dup) @ body_T.to_3x3().to_quaternion()
    R_lo = (body_T.to_3x3().to_quaternion() @ r['dlo_b']).rotation_difference(dlo) @ body_T.to_3x3().to_quaternion()
    for j in r['upper']:
        T[j] = Matrix.Translation(H) @ R_up.to_matrix().to_4x4() @ Matrix.Translation(-r['H0'])
    for j in r['lower']:
        T[j] = Matrix.Translation(sv['K']) @ R_lo.to_matrix().to_4x4() @ Matrix.Translation(-r['Kb'])
    Rf = Quaternion(UP, foot_yaw)
    for j in r['foot']:
        T[j] = Matrix.Translation(sv['A']) @ Rf.to_matrix().to_4x4() @ Matrix.Translation(-r['Ab'])
    return T

def build_leg(s, T):
    m = RIG[s]['m']
    P = []
    for v, p in enumerate(m['pos']):
        pv = Vector(p); acc = Vector((0, 0, 0)); tw = 0.0
        for j, w in zip(m['bidx'][v], m['bwt'][v]):
            if w <= 0: continue
            w = w / 255.0; acc += (T[j] @ pv) * w; tw += w
        P.append(acc / tw if tw > 0 else pv)
    for (mn, mm, fv, nv, ft, nt) in m['meshes']:
        faces = [tuple(i - fv for i in m['tris'][t]) for t in range(ft, ft + nt)]
        uvs = [[(m['uv'][i][0], 1.0 - m['uv'][i][1]) for i in m['tris'][t]] for t in range(ft, ft + nt)]
        add_mesh('leg_%s_%s' % (s, mn), P[fv:fv + nv], faces, uvs, material(mm, os.path.join(TEX_DIR, os.path.basename(mm))))

def torso_xf(p):
    sxy, sz = 0.75, 0.75 * 1.4
    return Vector((-sxy * p[1], sxy * p[0], sz * p[2]))
TORSO_OFF = Vector((0.0, 1.27, 51.71)) - torso_xf((-1.3, 0.0, 13.0))

def build_torso(body_T):
    faces, uvs = [], []
    for ff, a, b, c in ttris:
        faces.append((a, b, c))
        tri = []
        for vi in (a, b, c):
            onseam, s_, t_ = tst[vi]
            if onseam and not ff: s_ += tsw // 2
            tri.append(((s_ + 0.5) / tsw, 1.0 - (t_ + 0.5) / tsh))
        uvs.append(tri)
    add_mesh('torso', [body_T @ (torso_xf(p) + TORSO_OFF) for p in tpos], faces, uvs, material('torso', TORSO_TEX))

scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.display.shading.show_backface_culling = False
scene.render.resolution_x = 1280; scene.render.resolution_y = 960
world = bpy.data.worlds.new('w'); scene.world = world; world.color = (0.25, 0.25, 0.28)

def shot(loc, look, lens, fname):
    cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); scene.collection.objects.link(co)
    co.location = loc
    co.rotation_euler = (Vector(look) - Vector(loc)).normalized().to_track_quat('-Z', 'Y').to_euler()
    cam.lens = lens; cam.clip_start = 0.05; cam.clip_end = 10000
    scene.camera = co; scene.render.filepath = fname
    bpy.ops.render.render(write_still=True); print('RENDERED', fname)

def floor():
    me = bpy.data.meshes.new('floor')
    me.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new('floor', me); scene.collection.objects.link(ob)

# ------------------------------------------------------------------ checks and poses
def v3(v): return '(%.2f, %.2f, %.2f)' % (v.x, v.y, v.z)
tmin = min(p[2] for p in tpos)
for s in ('rt', 'lf'):
    side = SIDE_X[s]
    band = [torso_xf(p) + TORSO_OFF for p in tpos if p[2] < tmin + 2.5 and p[1] * (-side) > 1.0]
    c = sum(band, Vector((0, 0, 0))) / len(band)
    r = RIG[s]
    print('HIP %s  slayer hip %s  torso hip-band centroid %s  gap %s (%.2f)  thigh %.2f shin %.2f' % (
        s, v3(r['H0']), v3(c), v3(c - r['H0']), (c - r['H0']).length, r['Lup'], r['Llo']))

ANKLE_Z = RIG['rt']['Ab'].z
# name, body drop (crouch), body yaw deg (feet stay), per-foot planted (x, y) or None for under the hip, foot yaw deg
POSES = [
    ('stand', 0.0, 0.0, None, None),
    ('crouch_half', 8.0, 0.0, None, None),
    ('crouch_deep', 16.0, 0.0, None, None),
    ('step_forward', 2.0, 0.0, {'rt': (-4.2, -9.0), 'lf': (4.2, 4.0)}, None),
    ('turn_40_feet_planted', 0.0, 40.0, None, None),
]
print('TABLE|pose|side|hip|ankleTarget|knee|ankleSolved|gap|stretch|kneeBendDeg')
for name, drop, yaw, feet, _ in POSES:
    clear_scene()
    body_T = Matrix.Translation((0, 0, -drop)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
    for s in ('rt', 'lf'):
        r = RIG[s]
        H = body_T @ r['H0']
        if feet:
            Aw = Vector((feet[s][0], feet[s][1], ANKLE_Z))
        else:
            Aw = Vector((r['Ab'].x, r['Ab'].y, ANKLE_Z))          # planted where the standing foot is, body turn or not
        pole = (body_T.to_3x3() @ (FWD * POLE_FWD + Vector((SIDE_X[s], 0, 0)) * POLE_OUT)).normalized()
        sv = solve_leg(H, Aw, r['Lup'], r['Llo'], pole)
        bend = 180.0 - math.degrees((H - sv['K']).angle(sv['A'] - sv['K']))
        print('TABLE|%s|%s|%s|%s|%s|%s|%.2f|%.3f|%.1f' % (name, s, v3(H), v3(Aw), v3(sv['K']), v3(sv['A']), sv['gap'], sv['stretch'], bend))
        build_leg(s, leg_transforms(s, body_T, H, sv, 0.0))
    build_torso(body_T)
    floor()
    tag = '%s_%s' % (OUT, name)
    shot((-55, -60, 45), (0, -2, 28 - drop * 0.5), 32, tag + '_threequarter.png')
    shot((-85, -3, 30), (0, -2, 28 - drop * 0.5), 38, tag + '_side.png')
