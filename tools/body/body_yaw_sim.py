"""Idea 9 offline check: RS_VRBody body heading, today's head-only rule vs a hands-aware rule.

Today's rule is body_rig.zs:258-295 (turn 1:1, pitch freeze, neck deadzone, follow the excess).
The hands rule adds: when BOTH hands are held out in front of the body, the target heading blends
from the head toward where the hands point, the deadzone narrows and the follow speeds up, and the
pitch freeze no longer blocks it (aiming low while looking down is normal). Values: owner's ini.
"""
import math

TIC = 35
DEAD, FOLLOW, MAXPITCH = 25.0, 0.15, 55.0          # owner ini: rs_body_yaw_deadzone / _follow / _maxpitch
H_MIN, H_SPAN = 6.0, 6.0                           # hand must be 6..12 map units out horizontally
H_FWD, H_FWD_SPAN = 0.0, 0.5                        # ... and in the front half of the body
H_DEAD, H_FOLLOW = 10.0, 0.25                       # hands: narrow deadzone, faster follow

def norm(a): return (a + 180.0) % 360.0 - 180.0
def clamp(x, lo, hi): return max(lo, min(hi, x))

def update(by, head, pitch, hands, turn, use_hands):
    by = norm(by + turn)
    W, sx, sy = 0.0, 0.0, 0.0
    if use_hands:
        ws = []
        for ang, dist, low in hands:
            fwd = math.cos(math.radians(ang - by))
            w = clamp((dist - H_MIN) / H_SPAN, 0, 1) * clamp((fwd - H_FWD) / H_FWD_SPAN, 0, 1) * (0.0 if low else 1.0)
            ws.append(w)
            sx += math.cos(math.radians(ang)) * w; sy += math.sin(math.radians(ang)) * w
        W = min(ws)
    head_ok = abs(pitch) <= MAXPITCH
    if W <= 0 and not head_ok: return by, W
    if W > 0:
        yh = math.degrees(math.atan2(sy, sx))
        target = norm(head + norm(yh - head) * W) if head_ok else yh
    else:
        target = head
    d = norm(target - by)
    dead = DEAD * (1 - W) + H_DEAD * W
    follow = FOLLOW * (1 - W) + H_FOLLOW * W
    if abs(d) <= dead: return by, W
    excess = d - math.copysign(dead, d)
    return norm(by + excess * follow), W

def run(name, seconds, script, use_hands):
    by = 0.0; maxstep = 0.0; trace = []
    prev_turn_total = 0.0
    for i in range(int(seconds * TIC)):
        t = i / TIC
        head, pitch, hands, turn_total = script(t)
        turn = turn_total - prev_turn_total; prev_turn_total = turn_total
        nb, W = update(by, head, pitch, hands, turn, use_hands)
        maxstep = max(maxstep, abs(norm(nb - by) - turn))
        by = nb
        trace.append((t, head, by, hands, W))
    return by, maxstep, trace

def hands_aim(yaw, dist=14.0): return [(yaw, dist, False), (yaw + 4, dist - 2, False)]
def hands_down(yaw): return [(yaw + 90, 3.0, True), (yaw - 90, 3.0, True)]

SCENARIOS = {
    'A look around, hands at sides': (4.0, lambda t: (80 * math.sin(2 * math.pi * 0.5 * t), 0, hands_down(0), 0)),
    'B aim forward, look left 70':   (3.0, lambda t: (min(70, 140 * t), 0, hands_aim(0), 0)),
    'C swing aim + head to 90 in 1s': (3.0, lambda t: (min(90, 90 * t), 0, hands_aim(min(90, 90 * t)), 0)),
    'D one hand out, one down, look 70': (3.0, lambda t: (min(70, 140 * t), 0, [(0, 14, False), (-90, 3, True)], 0)),
    'E aim at 40 looking down 70':   (3.0, lambda t: (40, -70, hands_aim(40), 0)),
    'F snap 45 while aiming':        (2.0, lambda t: ((45 if t >= 0.5 else 0), 0, hands_aim(45 if t >= 0.5 else 0), (45 if t >= 0.5 else 0))),
}

for name, (secs, script) in SCENARIOS.items():
    for use in (False, True):
        by, maxstep, tr = run(name, secs, script, use)
        # metrics: max |body - hands yaw| while hands are out, over the last second; lag in C
        aim_err = max((abs(norm(b - h[0][0])) for (t, hd, b, h, W) in tr if t > secs - 1.0 and not h[0][2]), default=float('nan'))
        head_err = max(abs(norm(b - hd)) for (t, hd, b, h, W) in tr if t > secs - 1.0)
        print('%-34s %-10s final body %7.1f | last-second max |body-hands| %6.1f | |body-head| %6.1f | max per-tic step (excl. snap) %5.2f' % (
            name, 'HANDS' if use else 'today', by, aim_err, head_err, maxstep))
