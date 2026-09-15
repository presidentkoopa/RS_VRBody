import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
TAGS = [("pinch", 28), ("claw", 51), ("fist", 58), ("splay", 87), ("point", 144), ("flat", 186)]
fig, axes = plt.subplots(2, 6, figsize=(24, 9), dpi=80)
for i, (t, f) in enumerate(TAGS):
    for r, v in enumerate(("side", "palm")):
        ax = axes[r, i]; ax.set_axis_off()
        im = plt.imread(os.path.join(HERE, "out", "fit2_%s_%s.png" % (t, v)))
        ax.imshow(im[120:840, 280:1000])
        ax.set_title("%s (his frame %d) - %s" % (t, f, v), fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "out", "ermac_six_poses.png"))
print("wrote montage")
