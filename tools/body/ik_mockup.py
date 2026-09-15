# REFERENCE ARM SOLVER, driven against the mockup rig. Headless Blender, scratch only.
# blender -b --factory-startup -P ik_mockup.py -- OUT_PREFIX ARMS_IQM HAND_IQM HAND_TEX TORSO_MDL TORSO_TEX
#
# This is the math the plan's piece B asks the engine to carry, written once in Python so it can be
# seen working before anyone ports it. Frame: the Slayer FILE frame (+X left, -Y forward, +Z up, map
# units) -- the engine's IQM load mirror (models_iqm.cpp:359-361) is not applied here, see plan 3e.
#
# Per arm, given the drawn hand (palm position, finger direction, index-side direction):
#   1. wrist target  = palm - fingerDir * WRIST_BACK      (the RS stub end sits 1 unit inside the cuff)
#   2. FREE solve    = shelved IK_SolveTwoBoneArm (reach clamp, law of cosines, pole projection with
#                      two fallbacks) PLUS soft reach (NEW): past SOFT_START of the natural length the
#                      solved reach eases toward it, and stretch-by-lengthening (capped STRETCH_MAX)
#                      makes up the difference, so the elbow never snaps straight
#   3. SWIVEL ALIGNMENT (NEW, not shelved; v2 after the owner saw v1's broken elbows):
#      the elbow stays on the exact two-bone swivel circle (both lengths exact, wrist exact). The
#      natural elbow is the pole direction; alignment only rotates the elbow about the shoulder->wrist
#      axis toward the swivel angle of (wrist - fingerDir * forearmLen), by weight w, clamped to
#      +-SWIVEL_MAX. v1 lerped toward that point and projected onto the upper-arm sphere, which dragged
#      the elbow in front of the chest whenever the hand pointed along the aim line.
#   4. rotations     = minimal swing from the bind bone directions (as shelved)
#   5. forearm twist = the hand's index-side vs the swung bind index-side, about the forearm, clamped,
#                      spread over the roll pins by their position along the bone (swing-twist, as shelved)
import bpy, sys, os, struct, math
from mathutils import Vector, Quaternion, Matrix

A = sys.argv[sys.argv.index('--') + 1:]
OUT, ARMS, HAND, HAND_TEX, TORSO, TORSO_TEX = A[:6]

K_HAND = 0.34
STUB_END_Z = 10.6
STUB_INSIDE = 1.0
WRIST_BACK = STUB_END_Z * K_HAND - STUB_INSIDE   # palm -> Slayer wrist, map units
STRETCH_MAX = 1.25
POLE_OUT, POLE_DOWN, POLE_BACK = 1.0, 0.6, 0.35
TWIST_MAX = math.radians(110.0)
SWIVEL_MAX = math.radians(40.0)
SOFT_START = 0.90       # fraction of natural arm length where soft reach begins
UP = Vector((0, 0, 1)); BACK = Vector((0, 1, 0))
SIDE_X = {'rt': -1.0, 'lf': 1.0}

def clamp(x, lo, hi): return lo if x < lo else hi if x > hi else x

# ------------------------------------------------------------------ readers (as compose_mockup.py)
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
    bidx = get(4, nvert, 'H' if arr[4][0] == 3 else 'B') if 4 in arr else None
    bwt = get(5, nvert, 'B' if arr[5][0] == 1 else 'f') if 5 in arr else None
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
arms = read_iqm(ARMS); hand = read_iqm(HAND)
tpos, tst, ttris, tsw, tsh = read_mdl(TORSO)
J = {n: i for i, n in enumerate(arms['names'])}
jp = arms['jpos']
children = {}
for i, p in enumerate(arms['parents']): children.setdefault(p, []).append(i)
def subtree(root):
    out, st = set(), [root]
    while st:
        j = st.pop(); out.add(j); st.extend(children.get(j, []))
    return out

RIG = {}
for s in ('rt', 'lf'):
    up, lo, hd = J['arm_upper_' + s], J['arm_lower_' + s], J['arm_hand_' + s]
    S0, Eb, Wb = jp[up], jp[lo], jp[hd]
    dup_b = (Eb - S0).normalized(); dlo_b = (Wb - Eb).normalized()
    across = jp[J['index_part02_' + s]] - jp[J['pinky_part02_' + s]]
    across_b = (across - dlo_b * across.dot(dlo_b)).normalized()
    RIG[s] = dict(S0=S0, Eb=Eb, Wb=Wb, Lup=(Eb - S0).length, Llo=(Wb - Eb).length, dup_b=dup_b, dlo_b=dlo_b,
                  across_b=across_b, upper=subtree(up) - subtree(lo), lower=subtree(lo) - subtree(hd), hand=subtree(hd))

# ------------------------------------------------------------------ solver
def pole_for(side):
    return (Vector((SIDE_X[side], 0, 0)) * POLE_OUT + Vector((0, 0, -1)) * POLE_DOWN + BACK * POLE_BACK).normalized()

def solve_free(S0, W, Lup, Llo, pole):
    to = W - S0; raw = to.length
    if raw < 1e-4: return None
    aim = to / raw
    # SOFT REACH. Near full extension the two-bone elbow moves without limit per unit of reach (the swivel
    # radius goes like sqrt(1 - reach^2)), so tracking noise at arm's length shimmers the elbow. Past
    # SOFT_START the solved reach eases toward -- never onto -- the natural length, and the bones
    # lengthen by raw/soft so the wrist still lands exactly (a similar triangle, same angles).
    nat = Lup + Llo
    start = nat * SOFT_START
    if raw > start:
        span = nat - start
        soft = start + span * (1.0 - math.exp(-(raw - start) / span))
        stretch = raw / soft
    else:
        soft = raw
        stretch = 1.0
    sc = min(stretch, STRETCH_MAX)
    Lu, Ll = Lup * sc, Llo * sc
    # ONE CONTINUOUS MAPPING. The solved reach is sc * soft. Below the cap sc*soft == raw (the wrist lands
    # exactly); past the cap the bend keeps following the same soft curve and the hand simply leads. A
    # separate rule past the cap (tried: clamp, then re-softening against the capped length) switches
    # formulas at the cap and pops the elbow -- measured 2.3 units in one step.
    reach = sc * soft
    reach = clamp(reach, abs(Lu - Ll) * 1.001 + 0.01, (Lu + Ll) * 0.999)
    ang = math.acos(clamp((Lu * Lu + reach * reach - Ll * Ll) / (2 * Lu * reach), -1, 1))
    pp = pole - aim * pole.dot(aim)
    if pp.length < 1e-4:
        pp = aim.cross(UP)
        if pp.length < 1e-4: pp = Vector((1, 0, 0))
    pp.normalize()
    axis = aim.cross(pp).normalized()
    E = S0 + (Quaternion(axis, ang) @ aim) * Lu
    return dict(E=E, Lu=Lu, Ll=Ll, stretch=stretch, aim=aim, pp=pp, raw=raw, reach=reach)

# ---- IDEA 6: ELBOW KEEPS CLEAR OF WALLS. Walls are half-spaces (point, unit normal pointing into free
# space). The arm is sampled at the upper-arm middle, the elbow and the forearm middle with ARM_RADIUS; if
# any sample is inside, the elbow swings around its exact swivel circle (lengths and wrist unchanged) by
# Newton steps on the penetration until clear, capped at WALL_SWIVEL_MAX. Continuous: nothing moves until
# contact, and the correction grows from zero with the penetration. A nearly straight arm has no circle to
# swing on and simply stays (the hand leads). In the engine the half-spaces come from a render-side level
# query around the arm (nearby lines/planes, read-only) -- piece B asks a clearance callback, it does not
# know about levels.
ARM_RADIUS = 2.8
WALL_SWIVEL_MAX = math.radians(100.0)

def arm_penetration(S0, E, W, walls):
    worst = 0.0
    for p in (S0.lerp(E, 0.5), E, E.lerp(W, 0.5)):
        for p0, n in walls:
            worst = max(worst, ARM_RADIUS - (p - p0).dot(n))
    return worst

def wall_swivel(S0, C, u0, v0, rad, W, phi, walls):
    def pen(ph): return arm_penetration(S0, C + (u0 * math.cos(ph) + v0 * math.sin(ph)) * rad, W, walls)
    h = math.radians(2.0)
    for _ in range(12):
        p = pen(phi)
        if p <= 0: break
        g = (pen(phi + h) - pen(phi - h)) / (2 * h)
        if abs(g) < 1e-6: break
        phi = clamp(phi - p / g, -WALL_SWIVEL_MAX, WALL_SWIVEL_MAX)
    return phi

def solve_arm(side, palm, fdir, adir, w_align, wrist_back=None, walls=None):
    r = RIG[side]
    W = palm - fdir * (WRIST_BACK if wrist_back is None else wrist_back)
    fr = solve_free(r['S0'], W, r['Lup'], r['Llo'], pole_for(side))
    if fr is None: return None
    # swivel circle of all elbows that keep both bone lengths exact
    reach = fr['reach']
    a_ =(fr['Lu'] ** 2 - fr['Ll'] ** 2 + reach ** 2) / (2 * reach)
    rad = math.sqrt(max(fr['Lu'] ** 2 - a_ ** 2, 0.0))
    C = r['S0'] + fr['aim'] * a_
    u0 = fr['pp']; v0 = fr['aim'].cross(u0)
    phi = 0.0
    # The forearm lines up with the hand best when the elbow sits OPPOSITE the hand's off-axis direction
    # (lengths exact => |W-E| is constant, so maximising dot(W-E, fingerDir) picks that swivel).
    # Three weights keep that from ever popping, all stateless and continuous:
    #   fade  - a nearly straight arm has a tiny circle and no meaningful swivel
    #   conf  - a hand pointing along the shoulder->wrist line has no preferred swivel direction
    #   (1+cu) - as the aligned elbow approaches the ANTI-pole side the angle wraps at +-180; the weight
    #            goes to 0 there, so the wrap is multiplied by zero instead of flipping +40 <-> -40
    bend = rad / fr['Lu']                           # 0 = straight, 1 = elbow at 90 to the aim line
    fade = clamp((bend - 0.10) / 0.25, 0.0, 1.0)
    fperp = fdir - fr['aim'] * fdir.dot(fr['aim'])
    conf = clamp((fperp.length - 0.05) / 0.20, 0.0, 1.0)
    if w_align > 0 and fade > 0 and conf > 0:
        dt = -fperp.normalized()
        cu, cv = dt.dot(u0), dt.dot(v0)
        k = w_align * fade * conf * min(1.0, 1.0 + cu)
        phi = clamp(k * math.atan2(cv, cu), -SWIVEL_MAX, SWIVEL_MAX)
    phi_aligned = phi
    if walls and rad > 1e-3:
        phi = wall_swivel(r['S0'], C, u0, v0, rad, W, phi, walls)
    E = C + (u0 * math.cos(phi) + v0 * math.sin(phi)) * rad
    used = math.degrees(phi)
    dup = (E - r['S0']).normalized()
    dlo = (W - E).normalized()
    Ll_eff = min((W - E).length, r['Llo'] * STRETCH_MAX)
    W_solved = E + dlo * Ll_eff
    R_up = r['dup_b'].rotation_difference(dup)
    R_lo = r['dlo_b'].rotation_difference(dlo)
    c = R_lo @ r['across_b']; c = (c - dlo * c.dot(dlo)).normalized()
    t = adir - dlo * adir.dot(dlo)
    twist = 0.0
    tconf = clamp((t.length - 0.15) / 0.30, 0.0, 1.0)   # index side nearly along the forearm: roll is undefined
    if t.length > 1e-4:
        t.normalize()
        twist = math.atan2(dlo.dot(c.cross(t)), c.dot(t))
        # TAPER, not clamp: a hard clamp flips +110 <-> -110 when the raw roll crosses 180. Past the
        # limit the twist eases back to 0 at exactly 180, so both sides meet continuously.
        if abs(twist) > TWIST_MAX:
            twist = math.copysign(TWIST_MAX * (math.pi - abs(twist)) / (math.pi - TWIST_MAX), twist)
        twist *= tconf
    return dict(side=side, W=W, E=E, W_solved=W_solved, dup=dup, dlo=dlo, Lu=fr['Lu'], Ll_eff=Ll_eff, bend=bend, fade=fade,
                R_up=R_up, R_lo=R_lo, twist=twist, used=used, stretch=fr['stretch'], raw=fr['raw'],
                align_err=math.degrees(dlo.angle(fdir)), gap=(W_solved - W).length,
                elbow_side=(E - r['S0']).dot(fr['pp']) / fr['Lu'])

def joint_transforms(solves):
    T = [Matrix.Identity(4) for _ in arms['names']]
    for sv in solves:
        r = RIG[sv['side']]
        for j in r['upper']:
            pb = jp[j]; tt = clamp((pb - r['S0']).dot(r['dup_b']) / r['Lup'], 0, 1)
            p = r['S0'] + sv['R_up'] @ ((pb - r['S0']) + r['dup_b'] * (tt * (sv['Lu'] - r['Lup'])))
            T[j] = Matrix.Translation(p) @ sv['R_up'].to_matrix().to_4x4() @ Matrix.Translation(-pb)
        for j in r['lower'] | r['hand']:
            pb = jp[j]
            tt = 1.0 if j in r['hand'] else clamp((pb - r['Eb']).dot(r['dlo_b']) / r['Llo'], 0, 1)
            p = sv['E'] + sv['R_lo'] @ ((pb - r['Eb']) + r['dlo_b'] * (tt * (sv['Ll_eff'] - r['Llo'])))
            R = Quaternion(sv['dlo'], sv['twist'] * tt) @ sv['R_lo']
            T[j] = Matrix.Translation(p) @ R.to_matrix().to_4x4() @ Matrix.Translation(-pb)
    return T

# ------------------------------------------------------------------ builders
def build_arms(T):
    armdir = os.path.dirname(ARMS)
    P = []
    for v, p in enumerate(arms['pos']):
        pv = Vector(p); acc = Vector((0, 0, 0)); tw = 0.0
        for j, w in zip(arms['bidx'][v], arms['bwt'][v]):
            if w <= 0: continue
            w = w / 255.0; acc += (T[j] @ pv) * w; tw += w
        P.append(acc / tw if tw > 0 else pv)
    for (mn, mm, fv, nv, ft, nt) in arms['meshes']:
        faces = [tuple(i - fv for i in arms['tris'][t]) for t in range(ft, ft + nt)]
        uvs = [[(arms['uv'][i][0], 1.0 - arms['uv'][i][1]) for i in arms['tris'][t]] for t in range(ft, ft + nt)]
        add_mesh('arm_' + mn, P[fv:fv + nv], faces, uvs, material(mm, os.path.join(armdir, os.path.basename(mm))))

# ---- IDEA 1: THE RS HAND'S OWN WRIST BENDS. The stub (model z > 0) is skinned to Root_joint (99-100% past
# z 2.5, blending near the palm); the palm and fingers to HANDPALM_joint and below. Swinging Root_joint's
# vertices about the palm point (model origin) aims the stub at a point STUB_INSIDE inside the gauntlet cuff
# while the palm and fingers stay exactly where the controller put them. In the engine this is piece A on
# the hand actor: Root_joint rotated about the palm pivot, HANDPALM counter-rotated.
HJ = {n: i for i, n in enumerate(hand['names'])}
HAND_ROOT = HJ['Root_joint']
HAND_RW = [sum(w for j, w in zip(hand['bidx'][v], hand['bwt'][v]) if j == HAND_ROOT) / 255.0 for v in range(len(hand['pos']))]
STUB_IDX = [v for v, p in enumerate(hand['pos']) if p[2] > 0.0]
STUB_BEND_MAX = math.radians(70.0)
BEND_STUB = 'bendstub' in A
# v2 of idea 1. The mesh hinges where it is skinned -- at the palm (Root/HANDPALM blend, model z 0..2.5) --
# so the gauntlet's wrist must sit AT the palm for the stub to live inside the gauntlet and hinge at the
# cuff. v1 kept the wrist 2.6 units behind the palm and aimed at a point: the stub barely turned (21 deg of
# stub for 90 of hand) and clipped MORE than the rigid hand.
WRIST_BACK_BENT = 0.5

def hand_basis(side, fdir, adir):
    mirror = 1.0 if side == 'rt' else -1.0      # file-space right hand; see plan 3e
    cz = -fdir
    cx = adir if mirror > 0 else -adir
    cy = cz.cross(cx)
    return mirror, Matrix((cx, cy, cz)).transposed()

def stub_q(side, palm, fdir, adir, wrist_solved, forearm_dir):
    mirror, R = hand_basis(side, fdir, adir)
    d = -forearm_dir                                       # the stub lies straight down the forearm axis
    m = R.transposed() @ d.normalized()
    m = Vector((mirror * m.x, m.y, m.z))                  # into the hand's unmirrored model space
    q = Vector((0, 0, 1)).rotation_difference(m)
    if q.angle > STUB_BEND_MAX:
        q = Quaternion().slerp(q, STUB_BEND_MAX / q.angle)
    return q

def hand_vert_world(v, palm, basis, q):
    mirror, R = basis
    p = Vector(hand['pos'][v])
    if q is not None:
        p = p.lerp(q @ p, HAND_RW[v])                     # linear blend: Root_joint weight takes the swing
    return palm + R @ (Vector((mirror * p.x, p.y, p.z)) * K_HAND)

def build_hand(side, palm, fdir, adir, q=None):
    basis = hand_basis(side, fdir, adir)
    verts = [hand_vert_world(v, palm, basis, q) for v in range(len(hand['pos']))]
    uvs = [[(hand['uv'][i][0], 1.0 - hand['uv'][i][1]) for i in t] for t in hand['tris']]
    add_mesh('hand_' + side, verts, [tuple(t) for t in hand['tris']], uvs, material('rs_hand', HAND_TEX))

def build_torso():
    sxy, sz = 0.75, 0.75 * 1.4
    def xf(p): return Vector((-sxy * p[1], sxy * p[0], sz * p[2]))
    off = Vector((0.0, 1.27, 51.71)) - xf((-1.3, 0.0, 13.0))
    faces, uvs = [], []
    for ff, a, b, c in ttris:
        faces.append((a, b, c))
        tri = []
        for vi in (a, b, c):
            onseam, s_, t_ = tst[vi]
            if onseam and not ff: s_ += tsw // 2
            tri.append(((s_ + 0.5) / tsw, 1.0 - (t_ + 0.5) / tsh))
        uvs.append(tri)
    add_mesh('torso', [xf(p) + off for p in tpos], faces, uvs, material('torso', TORSO_TEX))

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

# ------------------------------------------------------------------ test hands (palm, finger dir, index side)
def H(p, f, a):
    f = Vector(f).normalized(); a = Vector(a); a = (a - f * a.dot(f)).normalized()
    return (Vector(p), f, a)
REST_RT = H((-11.5, -2.5, 33.0), (0, -0.15, -1), (0, -1, 0))
REST_LF = H((11.5, -2.5, 33.0), (0, -0.15, -1), (0, -1, 0))
POSES = [
    ('pistol_two_hand', 1.0, H((-2.5, -17, 45.5), (0.15, -0.97, 0.2), (0, 0, 1)), H((1.5, -15, 44), (-0.1, -0.95, 0.25), (0, 0.2, 1))),
    ('pistol_two_hand_w0', 0.0, H((-2.5, -17, 45.5), (0.15, -0.97, 0.2), (0, 0, 1)), H((1.5, -15, 44), (-0.1, -0.95, 0.25), (0, 0.2, 1))),
    ('rt_overhead',     1.0, H((-8, -6, 70), (0, -0.25, 1), (0, -1, 0)), REST_LF),
    ('rt_across_body',  1.0, H((7, -13, 43), (0.75, -0.65, 0), (0, 0, 1)), REST_LF),
    ('rest',            1.0, REST_RT, REST_LF),
    ('rt_near_chest',   1.0, H((-4, -9, 47), (0.3, -0.9, 0.3), (0, 0, 1)), REST_LF),
    ('rt_low_forward',  1.0, H((-8, -15, 36), (0, -1, -0.2), (0, 0, 1)), REST_LF),
    ('rt_palm_up',      1.0, H((-5, -15, 44), (0.1, -0.98, 0.1), (-1, 0, 0)), REST_LF),
    ('rt_reach_back',   1.0, H((-12, 8, 40), (0, 0.6, -0.8), (-1, 0, 0)), REST_LF),
    ('rt_too_far',      1.0, H((-6, -32, 52), (0, -1, 0), (0, 0, 1)), REST_LF),
    ('rt_wrist_bent_w1', 1.0, H((-5, -17, 40), (0.2, -0.5, -0.85), (0, -0.8, 0.5)), REST_LF),
    ('rt_wrist_bent_w0', 0.0, H((-5, -17, 40), (0.2, -0.5, -0.85), (0, -0.8, 0.5)), REST_LF),
]

NORENDER = 'norender' in A
def v3(v): return '(%.2f, %.2f, %.2f)' % (v.x, v.y, v.z)
for s in ('rt', 'lf'):
    r = RIG[s]
    print('RIG %s shoulder %s elbow_bind %s wrist_bind %s upper %.3f forearm %.3f pole %s' % (
        s, v3(r['S0']), v3(r['Eb']), v3(r['Wb']), r['Lup'], r['Llo'], v3(pole_for(s))))
print('TABLE|pose|w|side|palm|fingerDir|indexDir|wristTarget|elbow|wristSolved|stretch|swivelDeg|forearmVsHandDeg|gap|twistDeg|elbowSide|bend')
for name, w_align, hr, hl in POSES:
    clear_scene()
    solves = []
    for side, (palm, f, a) in (('rt', hr), ('lf', hl)):
        sv = solve_arm(side, palm, f, a, w_align, WRIST_BACK_BENT if BEND_STUB else None)
        solves.append(sv)
        print('TABLE|%s|%.2f|%s|%s|%s|%s|%s|%s|%s|%.3f|%.2f|%.1f|%.2f|%.1f|%.2f|%.2f' % (
            name, w_align, side, v3(palm), v3(f), v3(a), v3(sv['W']), v3(sv['E']), v3(sv['W_solved']),
            sv['stretch'], sv['used'], sv['align_err'], sv['gap'], math.degrees(sv['twist']), sv['elbow_side'], sv['bend']))
        if not NORENDER:
            build_hand(side, palm, f, a, stub_q(side, palm, f, a, sv['W_solved'], sv['dlo']) if BEND_STUB else None)
    if NORENDER: continue
    build_arms(joint_transforms(solves))
    build_torso()
    tag = f'{OUT}_{name}'
    shot((-40, -52, 62), (0, -8, 47), 30, tag + '_threequarter.png')
    shot((-60, -12, 50), (0, -8, 47), 35, tag + '_side.png')
    wr = solves[0]['W_solved']
    shot(tuple(wr + Vector((-9, -7, 5))), tuple(wr), 45, tag + '_wrist.png')
    shot((0, 0.5, 60.5), (0, -18, 40), 14, tag + '_firstperson.png')
# ------------------------------------------------------------------ WALL TESTS (idea 6)
def wall_case(name, side, hand_, walls):
    palm, f, a = hand_
    s0 = solve_arm(side, palm, f, a, 1.0)
    s1 = solve_arm(side, palm, f, a, 1.0, None, walls)
    r_ = RIG[side]
    p0 = arm_penetration(r_['S0'], s0['E'], s0['W'], walls)
    p1 = arm_penetration(r_['S0'], s1['E'], s1['W'], walls)
    print('WALLTEST|%s|%s|swivelNoWall %.1f|swivelWall %.1f|penBefore %.2f|penAfter %.2f|elbowNoWall %s|elbowWall %s|gap %.2f' % (
        name, side, s0['used'], s1['used'], p0, p1, v3(s0['E']), v3(s1['E']), s1['gap']))
    return s1

RIGHT_WALL = [(Vector((-14.5, 0, 0)), Vector((1, 0, 0)))]          # a wall just outside the right elbow
FRONT_WALL = [(Vector((0, -8.0, 0)), Vector((0, 1, 0)))]           # a wall in front of the chest
wall_case('rest_right_wall', 'rt', REST_RT, RIGHT_WALL)
wall_case('across_right_wall', 'rt', H((7, -13, 43), (0.76, -0.65, 0), (0, 0, 1)), RIGHT_WALL)
wall_case('near_chest_front_wall', 'rt', H((-4, -7.5, 47), (0.3, -0.9, 0.3), (0, 0, 1)), FRONT_WALL)
print('WALLSWEEP|steps|maxElbowStep|maxSwivelStepDeg|finalPen   (right wall slides from x=-20 to x=-12 against the resting arm)')
for steps in (60, 240):
    prev = None; mE = mS = 0.0; lastpen = 0.0
    for i in range(steps + 1):
        wx = -20.0 + 8.0 * i / steps
        walls = [(Vector((wx, 0, 0)), Vector((1, 0, 0)))]
        sv = solve_arm('rt', REST_RT[0], REST_RT[1], REST_RT[2], 1.0, None, walls)
        lastpen = arm_penetration(RIG['rt']['S0'], sv['E'], sv['W'], walls)
        if prev:
            mE = max(mE, (sv['E'] - prev['E']).length)
            mS = max(mS, abs(sv['used'] - prev['used']))
        prev = sv
    print('WALLSWEEP|%d|%.3f|%.2f|%.2f' % (steps, mE, mS, lastpen))

if not NORENDER:
    clear_scene()
    solves = [solve_arm('rt', REST_RT[0], REST_RT[1], REST_RT[2], 1.0, None, RIGHT_WALL), solve_arm('lf', REST_LF[0], REST_LF[1], REST_LF[2], 1.0)]
    for sv, (palm, f, a) in zip(solves, (REST_RT, REST_LF)):
        build_hand(sv['side'], palm, f, a)
    build_arms(joint_transforms(solves))
    build_torso()
    wx = RIGHT_WALL[0][0].x
    add_mesh('wall', [(wx, -30, 20), (wx, 20, 20), (wx, 20, 70), (wx, -30, 70)], [(0, 1, 2, 3)],
             [[(0, 0), (1, 0), (1, 1), (0, 1)]], material('wall', None))
    shot((-40, -52, 62), (0, -8, 47), 30, OUT + '_wall_rest_threequarter.png')
    shot((0, -60, 48), (0, 0, 45), 35, OUT + '_wall_rest_front.png')

# ------------------------------------------------------------------ CLIP CHECK: does the RS wrist stub poke through the gauntlet?
# Gauntlet surface is approximated per band along the forearm axis by a LOW percentile of the forearm
# mesh's radial distances (so bumps and spikes do not count as room). A stub vertex whose radial
# distance from the forearm axis exceeds that band's radius, while it lies inside the gauntlet's length,
# pokes through. Stub = RS hand vertices with model z > 0 (the forearm side of the palm).
def gauntlet_profile(side, pct=0.20, band=0.05):
    r = RIG[side]; prof = {}
    for v, p in enumerate(arms['pos']):
        idx = arms['bidx'][v]; wts = arms['bwt'][v]
        dom = idx[max(range(len(wts)), key=lambda k: wts[k])]
        if dom not in (r['lower'] | r['hand']): continue
        w = Vector(p) - r['Eb']; t = w.dot(r['dlo_b']) / r['Llo']
        if t < 0.3 or t > 1.1: continue
        rad = (w - r['dlo_b'] * w.dot(r['dlo_b'])).length
        prof.setdefault(int(t / band), []).append(rad)
    return {k: sorted(v)[int(len(v) * pct)] for k, v in prof.items() if len(v) >= 20}
PROF = {s: gauntlet_profile(s) for s in ('rt', 'lf')}
def clip_amount(side, E, Wsol, palm, fdir, adir, q=None, band=0.05):
    axis = Wsol - E; L = axis.length; axis = axis / L
    basis = hand_basis(side, fdir, adir)
    worst, poking = -99.0, 0
    for v in STUB_IDX:
        wp = hand_vert_world(v, palm, basis, q)
        w = wp - E; t = w.dot(axis) / L
        key = int(t / band)
        if key not in PROF[side]: continue          # outside the gauntlet's length: visible wrist, not a clip
        pen = (w - axis * w.dot(axis)).length - PROF[side][key]
        worst = max(worst, pen)
        if pen > 0: poking += 1
    return worst, poking

print('CLIPPROFILE|side|t band start -> gauntlet radius (20th percentile)')
for s in ('rt',):
    print('CLIPPROFILE|%s|%s' % (s, ' '.join('%.2f:%.2f' % (k * 0.05, v) for k, v in sorted(PROF[s].items()))))

# Pure geometry: forearm fixed at bind, hand bent by theta about two axes at the wrist target point.
print('CLIPBEND|axis|thetaDeg|rigidWorst|rigidPoking|bentWorst|bentPoking|stubBendDeg  (stub verts: %d)' % len(STUB_IDX))
r = RIG['rt']
for axname, ax in (('flex', r['across_b']), ('side', r['dlo_b'].cross(r['across_b']).normalized())):
    for th in range(0, 95, 5):
        qh = Quaternion(ax, math.radians(th))
        f = qh @ r['dlo_b']; a = qh @ r['across_b']
        palm = r['Wb'] + f * WRIST_BACK
        w0, p0 = clip_amount('rt', r['Eb'], r['Wb'], palm, f, a)
        palm_b = r['Wb'] + f * WRIST_BACK_BENT
        qs = stub_q('rt', palm_b, f, a, r['Wb'], r['dlo_b'])
        w1, p1 = clip_amount('rt', r['Eb'], r['Wb'], palm_b, f, a, qs)
        print('CLIPBEND|%s|%d|%.2f|%d|%.2f|%d|%.1f' % (axname, th, w0, p0, w1, p1, math.degrees(qs.angle) if qs else 0.0))

print('CLIPPOSE|pose|side|forearmVsHandDeg|rigidWorst|rigidPoking|bentWorst|bentPoking|stubBendDeg')
for name, w_align, hr, hl in POSES:
    for side, (palm, f, a) in (('rt', hr), ('lf', hl)):
        sv = solve_arm(side, palm, f, a, w_align)
        w0, p0 = clip_amount(side, sv['E'], sv['W_solved'], palm, f, a)
        sb = solve_arm(side, palm, f, a, w_align, WRIST_BACK_BENT)
        qs = stub_q(side, palm, f, a, sb['W_solved'], sb['dlo'])
        w1, p1 = clip_amount(side, sb['E'], sb['W_solved'], palm, f, a, qs)
        print('CLIPPOSE|%s|%s|%.1f|%.2f|%d|%.2f|%d|%.1f' % (name, side, sv['align_err'], w0, p0, w1, p1, math.degrees(qs.angle) if qs else 0.0))

# ------------------------------------------------------------------ continuity sweeps (jitter / pop test)
PD = {name: (w, hr, hl) for name, w, hr, hl in POSES}
def lerpH(h0, h1, t):
    p = h0[0].lerp(h1[0], t)
    f = h0[1].lerp(h1[1], t).normalized()
    a = h0[2].lerp(h1[2], t); a = a - f * a.dot(f)
    a = a.normalized() if a.length > 1e-6 else h0[2]
    return (p, f, a)
SWEEPS = [('rest_to_pistol', REST_RT, PD['pistol_two_hand'][1]),
          ('pistol_to_overhead', PD['pistol_two_hand'][1], PD['rt_overhead'][1]),
          ('rest_to_across', REST_RT, PD['rt_across_body'][1]),
          ('pistol_to_near_chest', PD['pistol_two_hand'][1], PD['rt_near_chest'][1]),
          ('pistol_to_too_far', PD['pistol_two_hand'][1], PD['rt_too_far'][1]),
          ('rest_to_reach_back', REST_RT, PD['rt_reach_back'][1]),
          ('pistol_to_palm_up', PD['pistol_two_hand'][1], PD['rt_palm_up'][1]),
          ('bent_w1_to_rest', PD['rt_wrist_bent_w1'][1], REST_RT)]
# CONTINUITY TEST: each sweep runs at 60 and at 240 steps. A continuous solver's worst per-step jump
# shrinks ~4x with 4x the steps; a discontinuity (a pop) does not shrink. E0 is the natural elbow
# (alignment off) so swivel pops and the two-bone extension singularity can be told apart.
print('SWEEP|name|steps|maxWristStep|maxElbowStep|maxNaturalElbowStep|maxSwivelStepDeg|maxTwistStepDeg|minElbowSide|atT|bend|reachOverNatural')
for name, h0, h1 in SWEEPS:
    for STEPS in (60, 240):
        prev = prev0 = None; mW = mE = mE0 = mS = mT = 0.0; minSide = 9.0; at = (0.0, 0.0, 0.0)
        for i in range(STEPS + 1):
            p, f, a = lerpH(h0, h1, i / STEPS)
            sv = solve_arm('rt', p, f, a, 1.0)
            s0 = solve_arm('rt', p, f, a, 0.0)
            minSide = min(minSide, sv['elbow_side'])
            if prev:
                mW = max(mW, (sv['W_solved'] - prev['W_solved']).length)
                de = (sv['E'] - prev['E']).length
                if de > mE:
                    mE = de; at = (i / STEPS, sv['bend'], sv['raw'] / (RIG['rt']['Lup'] + RIG['rt']['Llo']))
                mE0 = max(mE0, (s0['E'] - prev0['E']).length)
                mS = max(mS, abs(sv['used'] - prev['used']))
                mT = max(mT, abs(math.degrees(sv['twist'] - prev['twist'])))
            prev, prev0 = sv, s0
        print('SWEEP|%s|%d|%.3f|%.3f|%.3f|%.2f|%.2f|%.2f|%.3f|%.2f|%.3f' % (name, STEPS, mW, mE, mE0, mS, mT, minSide, at[0], at[1], at[2]))
print('DONE')
