"""The Pistolet's grip, measured in gun space (md3 x 1.35: x barrel, y across, z up).

Grip = receiver + magazine vertices behind the trigger (x < trigger front) and below the slide.
Prints the grip axis (principal direction in x-z), and per band along it the front and rear
edge, and the thickness in y. Read-only.
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
t = np.load(os.path.join(HERE, "pistolet_tris.npz"))
trig = t["rec.001"].reshape(-1, 3)
slide = t["slide"].reshape(-1, 3)
v = np.concatenate([t["rec"].reshape(-1, 3), t["mag"].reshape(-1, 3), t["mag.001"].reshape(-1, 3)])

trig_front = trig[:, 0].max()
trig_back = trig[:, 0].min()
slide_bottom = slide[:, 2].min()
grip = v[(v[:, 0] < trig_back) & (v[:, 2] < slide_bottom - 0.5)]
print("trigger x %.2f..%.2f z %.2f..%.2f   slide bottom z %.2f   grip verts %d"
      % (trig_back, trig_front, trig[:, 2].min(), trig[:, 2].max(), slide_bottom, len(grip)))

xz = grip[:, [0, 2]]
c = xz.mean(axis=0)
_, _, vt = np.linalg.svd(xz - c, full_matrices=False)
u = vt[0] if vt[0][1] > 0 else -vt[0]          # grip axis, pointing up
f = np.array([u[1], -u[0]])                    # across the grip, pointing forward (+x side)
if f[0] < 0:
    f = -f
print("grip centre (x %.2f, z %.2f)  axis up (%.3f, %.3f)  forward (%.3f, %.3f)" % (c[0], c[1], u[0], u[1], f[0], f[1]))

along = (xz - c) @ u
across = (xz - c) @ f
lo, hi = along.min(), along.max()
print("grip length along axis %.2f (%.2f..%.2f)" % (hi - lo, lo, hi))
bands = 8
for i in range(bands):
    a0 = lo + (hi - lo) * i / bands
    a1 = lo + (hi - lo) * (i + 1) / bands
    sel = (along >= a0) & (along < a1)
    if sel.sum() == 0:
        continue
    g = grip[sel]
    print("  along %6.2f..%6.2f  n %3d  rear %6.2f  front %6.2f  depth %5.2f  y %5.2f..%5.2f"
          % (a0, a1, sel.sum(), across[sel].min(), across[sel].max(), across[sel].max() - across[sel].min(),
             g[:, 1].min(), g[:, 1].max()))

np.savez(os.path.join(HERE, "grip_fit.npz"), centre=c, up=u, forward=f, lo=lo, hi=hi,
         ymin=grip[:, 1].min(), ymax=grip[:, 1].max(), trig_back=trig_back, slide_bottom=slide_bottom)
