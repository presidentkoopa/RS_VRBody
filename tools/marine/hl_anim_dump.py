"""Decode a GoldSrc (Half-Life) studio model's skeletal animation to JSON. Read-only, nothing is written back.

usage: hl_anim_dump.py MODEL.mdl --list
       hl_anim_dump.py MODEL.mdl --seq walk [-o walk.json] [--blend 0] [--frames 0:9] [--bones Bip01]

WHY THIS EXISTS. Our marine body (marine_whole.iqm) has a full skeleton and no animation at all -- 1 frame,
0 framechannels. Half-Life's player model has hand-authored locomotion that still reads correctly twenty-five
years on, so it is the cheapest available source of *motion*: joint curves and timing. This tool lifts those
numbers out so they can be retargeted onto our bip_* skeleton.

WHAT WE TAKE AND WHAT WE DO NOT. Half-Life's models are Valve's assets. We extract MOTION DATA -- per-bone
Euler curves and their frame timing -- to study and retarget. We do not ship, redistribute or convert Valve's
mesh, skins, bone set or model file, and this tool deliberately has no mesh path in it at all: it reads bones,
sequences and animation blocks and nothing else. No model file is copied anywhere by this script.

FORMAT REFERENCE. E:/XashWork/XashVR/tools/studiomdl/src/engine/studio.h (the struct layout), plus the
authoritative decoder in E:/XashWork/hlsdk-portable/cl_dll/StudioModelRenderer.cpp
(StudioCalcBonePosition / StudioCalcBoneQuaterion) and the matching *encoder* in
E:/XashWork/XashVR/tools/studiomdl/src/utils/studiomdl/studiomdl.c. The RLE below is transcribed from those,
not reconstructed from a wiki -- the run-length scheme has two counters that mean different things and every
third-party description of it that I have seen gets the "ran out of values" branch wrong.

UNITS AND AXES -- GOLDSRC, WHICH IS *NOT* OUR FRAME.
  * Space: right-handed, +X forward, +Y left, +Z up. Quake's frame, inherited whole.
  * Length: Quake map units, ~1 unit = 1 inch (the HL player hull is 72 units for a six-foot marine).
  * Rotation: radians about the bone's own local X, Y, Z, composed Rz(z) * Ry(y) * Rx(x) -- X is applied
    first, Z last. That is the order baked into the engine's AngleQuaternion(), so it is the order our
    retarget has to undo. This tool reports DEGREES because a human is going to read them.
  * OUR marine IQM file frame is +X left, -Y forward, +Z up (see marine_to_iqm.py): a 90 degree yaw about Z
    away from GoldSrc. Do not paste these numbers onto bip_* bones without rebasing them -- and rebasing means
    against our bind pose, because both skeletons store rotations as deltas from their own rest pose, and the
    two rest poses are not the same shape.

ON-DISK LAYOUT, the parts this tool walks:
  studiohdr_t   (244 bytes) -- numbones/boneindex, numseq/seqindex, numseqgroups/seqgroupindex.
  mstudiobone_t (112 bytes) -- name[32], parent, flags, bonecontroller[6], value[6], scale[6].
                               value[] is the REST pose (3 pos then 3 rot); scale[] converts the stored
                               int16 deltas to units/radians. scale is per-bone per-channel and is chosen by
                               studiomdl to span that bone's actual range across the whole model, so it is
                               never a constant -- STUDIO_TO_RAD (pi/32768) is only the theoretical worst case.
  mstudioseqdesc_t (176 bytes) -- label[32], fps, flags (1 = looping), numframes, numblends, animindex,
                               seqgroup, motiontype/motionbone/linearmovement (the root motion the engine
                               strips out and replaces with actual movement).
  mstudioanim_t (12 bytes)  -- unsigned short offset[6], one per channel, in the order X Y Z XR YR ZR.
                               Laid out [blend][bone]: blend b's bone i is at animindex + (b*numbones + i)*12.
                               offset == 0 means "this channel never moves"; the value is bone.value[c].
                               A non-zero offset is BYTES FROM THE START OF THAT 12-BYTE RECORD, not from the
                               file or the sequence -- getting this wrong gives plausible-looking garbage.
"""
import argparse, json, struct, sys, os
import numpy as np

# ---------------------------------------------------------------- struct sizes, from studio.h
HDR_SIZE, BONE_SIZE, SEQ_SIZE, SEQGROUP_SIZE, ANIM_SIZE = 244, 112, 176, 104, 12
CHAN = ("X", "Y", "Z", "XR", "YR", "ZR")          # mstudioanim_t.offset[] order; 0..2 pos, 3..5 rot
# mstudioseqdesc_t.motiontype bits we care to report (studio.h STUDIO_*). The engine zeroes the motion bone's
# position on the flagged axes and drives the entity instead, so a walk's forward travel is usually NOT in the
# curve -- it is in linearmovement. We report both so the retarget can put the travel back or leave it out.
MOTION_BITS = [(0x0001, "X"), (0x0002, "Y"), (0x0004, "Z"),
               (0x0008, "XR"), (0x0010, "YR"), (0x0020, "ZR"),
               (0x0040, "LX"), (0x0080, "LY"), (0x0100, "LZ")]


def cstr(buf, off, n):
    s = buf[off:off + n]
    z = s.find(b"\0")
    return (s if z < 0 else s[:z]).decode("latin-1")


class Studio:
    """One .mdl, parsed far enough to answer questions about bones and sequences. Mesh data is ignored."""

    def __init__(self, path):
        self.path = path
        self.buf = open(path, "rb").read()
        ident, self.version = struct.unpack_from("<4si", self.buf, 0)
        if ident != b"IDST":
            # IDSQ is a sequence-group file (player01.mdl and friends): animation only, no header we can
            # navigate from. Those are opened as a *companion* to the main model, never on their own.
            raise SystemExit(f"{path}: not a GoldSrc studio model (magic {ident!r}; IDSQ = sequence group, "
                             f"pass the main .mdl instead)")
        if self.version != 10:
            raise SystemExit(f"{path}: studio version {self.version}, expected 10 (GoldSrc)")
        self.name = cstr(self.buf, 8, 64)
        (self.numbones, self.boneindex, _nbc, _bci, _nhb, _hbi,
         self.numseq, self.seqindex, self.numseqgroups, self.seqgroupindex) = struct.unpack_from("<10i", self.buf, 140)
        if self.numbones == 0 and self.numseq == 0:
            # playert.mdl and friends: a texture-only companion. Same IDST magic, every count zeroed. Worth
            # naming, because the alternative is a silent empty listing that looks like a decode failure.
            print(f"{path}: texture-only companion file (0 bones, 0 sequences) -- "
                  f"the skeleton and animation live in the main .mdl", file=sys.stderr)
        self.bones = self._bones()
        self.seqgroups = self._seqgroups()
        self.sequences = self._sequences()
        # Sequence groups above 0 live in a sibling file. We resolve them lazily and cache the bytes, because
        # most models have exactly one group and we should not go looking for files we do not need.
        self._groupbuf = {0: self.buf}

    # ------------------------------------------------------------ bones
    def _bones(self):
        out = []
        for i in range(self.numbones):
            o = self.boneindex + i * BONE_SIZE
            name = cstr(self.buf, o, 32)
            parent, flags = struct.unpack_from("<ii", self.buf, o + 32)
            ctl = struct.unpack_from("<6i", self.buf, o + 40)
            value = struct.unpack_from("<6f", self.buf, o + 64)
            scale = struct.unpack_from("<6f", self.buf, o + 88)
            out.append(dict(index=i, name=name, parent=parent, flags=flags,
                            bonecontroller=list(ctl), value=list(value), scale=list(scale)))
        return out

    def _seqgroups(self):
        out = []
        for i in range(self.numseqgroups):
            o = self.seqgroupindex + i * SEQGROUP_SIZE
            out.append(dict(index=i, label=cstr(self.buf, o, 32), name=cstr(self.buf, o + 32, 64)))
        return out

    # ------------------------------------------------------------ sequences
    def _sequences(self):
        out = []
        for i in range(self.numseq):
            o = self.seqindex + i * SEQ_SIZE
            label = cstr(self.buf, o, 32)
            fps, flags, activity, actweight = struct.unpack_from("<fiii", self.buf, o + 32)
            numevents, eventindex, numframes = struct.unpack_from("<3i", self.buf, o + 48)
            motiontype, motionbone = struct.unpack_from("<2i", self.buf, o + 68)
            linearmovement = struct.unpack_from("<3f", self.buf, o + 76)
            bbmin = struct.unpack_from("<3f", self.buf, o + 96)
            bbmax = struct.unpack_from("<3f", self.buf, o + 108)
            numblends, animindex = struct.unpack_from("<2i", self.buf, o + 120)
            blendtype = struct.unpack_from("<2i", self.buf, o + 128)
            blendstart = struct.unpack_from("<2f", self.buf, o + 136)
            blendend = struct.unpack_from("<2f", self.buf, o + 144)
            seqgroup = struct.unpack_from("<i", self.buf, o + 156)[0]
            out.append(dict(index=i, label=label, fps=fps, flags=flags, looping=bool(flags & 1),
                            activity=activity, actweight=actweight, numevents=numevents,
                            numframes=numframes, motiontype=motiontype, motionbone=motionbone,
                            linearmovement=list(linearmovement), numblends=numblends, animindex=animindex,
                            blendtype=list(blendtype), blendstart=list(blendstart), blendend=list(blendend),
                            seqgroup=seqgroup, bbmin=list(bbmin), bbmax=list(bbmax)))
        return out

    def group_buffer(self, grp):
        """Bytes holding sequence group `grp`'s animation blocks.

        Group 0 is inline in the main file and animindex is an offset from the studiohdr_t. Groups 1+ are
        demand-loaded siblings (player01.mdl); the engine loads the whole file and then does
        `(byte*)data + animindex`, so for those animindex is an offset from byte 0 OF THAT FILE -- past its
        76-byte studioseqhdr_t, which we therefore never have to parse.
        """
        if grp in self._groupbuf:
            return self._groupbuf[grp]
        want = self.seqgroups[grp]["name"].replace("\\", "/").rsplit("/", 1)[-1]
        cand = os.path.join(os.path.dirname(os.path.abspath(self.path)), want)
        if not os.path.exists(cand):
            # Case differs between a Steam install and the compiler's record of the path often enough to be
            # worth a directory scan rather than a confusing "file not found".
            d = os.path.dirname(os.path.abspath(self.path))
            hit = [f for f in os.listdir(d) if f.lower() == want.lower()]
            if not hit:
                raise SystemExit(f"sequence group {grp} needs '{want}' next to {self.path}; not present")
            cand = os.path.join(d, hit[0])
        self._groupbuf[grp] = open(cand, "rb").read()
        return self._groupbuf[grp]


# ---------------------------------------------------------------- the run-length scheme
#
# Each animated channel is a stream of mstudioanimvalue_t, a 2-byte union that is read EITHER as a pair of
# bytes (valid, total) OR as a signed short (value) depending on where you are in the stream. The stream is a
# sequence of spans. A span is:
#
#     [ valid,total ]  [ v0 ][ v1 ] ... [ v(valid-1) ]
#      one 2-byte hdr   `valid` 2-byte signed shorts
#
# and the span covers `total` frames, of which the first `valid` have their own stored value; frames
# valid..total-1 repeat the LAST stored value. So `total >= valid` always, `valid` is how many shorts follow,
# and `total - valid` is the length of the held run. The next span's header sits at hdr + 1 + valid entries.
#
# That is why the encoder in studiomdl.c increments num.valid only when it actually writes a short, and
# num.total on every frame: a bone that is still for 40 frames costs one header and one short, a bone that
# moves every frame costs one header and 40 shorts. Both counters are single BYTES, so a span can never
# exceed 255 frames -- studiomdl force-splits at 255, and long idles really do produce several spans.
#
# To read frame k: walk spans subtracting `total` until k falls inside one, then take value[k] if k < valid,
# else the last stored value. The engine also guards `if (total < valid) k = 0` before and inside the walk;
# that is a corruption trap, not part of the format, and we keep it so a malformed file gives frame 0 rather
# than walking off the end of the buffer.
def _hdr(av, p):
    """The (valid, total) byte pair at entry `p`.

    The entry is a signed int16 in our view, so we re-widen to unsigned before splitting: little-endian puts
    num.valid in the low byte and num.total in the high byte. Going through a Python int here is not
    fastidiousness -- `p += valid + 1` with a raw numpy int16 on the right-hand side promotes the whole
    expression back to int16 and overflows the moment a channel sits past entry 32767, which every sequence
    after the first few in a real model does. That bug decodes silently and plausibly.
    """
    w = int(av[p]) & 0xFFFF
    return w & 0xFF, w >> 8


def _decode_channel(av, start, frame):
    """One channel, one frame, as the raw int16 the encoder stored. `av` is an int16 view of the group buffer,
    `start` is the channel's first entry index in that view."""
    p = int(start)
    k = int(frame)
    valid, total = _hdr(av, p)
    if total < valid:
        k = 0
    while total <= k:
        k -= total
        p += valid + 1
        valid, total = _hdr(av, p)
        if total < valid:
            k = 0
    if valid > k:
        return int(av[p + 1 + k])          # inside the stored run
    return int(av[p + valid])              # past it: hold the last stored value


def dump_sequence(st, seq, blend=0, frames=None, bone_filter=None):
    """Every bone's 6 DOF for every frame of one sequence, already scaled into units and radians.

    We sample exactly on frames (the engine's `s` interpolant = 0). These are the authored keys; interpolating
    between them here would only blur what we are trying to measure.
    """
    buf = st.group_buffer(seq["seqgroup"])
    # int16 view of the whole buffer, so a channel is just an index into it. The engine reads animvalues
    # through an Unaligned() wrapper, which reads as if the stream might be odd-aligned -- it is not; that
    # wrapper exists for architectures that fault on unaligned loads, not because studiomdl ever writes the
    # stream off a 2-byte boundary. We still refuse an odd animindex below rather than skew every value by a
    # byte and produce numbers that look like a plausible animation of something else entirely.
    if len(buf) % 2:
        buf = buf + b"\0"          # odd trailing byte: pad so the int16 view covers the whole file
    av = np.frombuffer(buf, dtype="<i2")

    if blend >= seq["numblends"]:
        raise SystemExit(f"sequence '{seq['label']}' has {seq['numblends']} blend(s); --blend {blend} is out of range")
    anim_base = seq["animindex"] + blend * st.numbones * ANIM_SIZE
    if anim_base % 2:
        raise SystemExit(f"animindex {anim_base} is odd; refusing to read int16s off a skewed base")

    want = range(seq["numframes"]) if frames is None else frames
    keep = None if bone_filter is None else set(b.lower() for b in bone_filter)

    bones_out, offsets = [], []
    for i, b in enumerate(st.bones):
        rec = anim_base + i * ANIM_SIZE
        off = struct.unpack_from("<6H", buf, rec)
        offsets.append((rec, off))
        if keep is not None and b["name"].lower() not in keep:
            continue
        bones_out.append(dict(
            index=i, name=b["name"], parent=b["parent"],
            parent_name=(st.bones[b["parent"]]["name"] if b["parent"] >= 0 else None),
            rest_pos=[round(v, 6) for v in b["value"][:3]],
            rest_rot_deg=[round(np.degrees(v), 4) for v in b["value"][3:]],
            pos_scale=[round(v, 8) for v in b["scale"][:3]],
            rot_scale_deg=[round(np.degrees(v), 8) for v in b["scale"][3:]],
            animated=[CHAN[c] for c in range(6) if off[c] != 0]))

    frames_out = []
    for f in want:
        per = {}
        for i, b in enumerate(st.bones):
            if keep is not None and b["name"].lower() not in keep:
                continue
            rec, off = offsets[i]
            pos, rot = [], []
            for c in range(6):
                if off[c] == 0:
                    raw = 0.0                      # channel absent: sits at the bone's rest value
                else:
                    # offset is bytes from the start of this bone's 12-byte mstudioanim_t record.
                    raw = _decode_channel(av, (rec + off[c]) // 2, f)
                v = b["value"][c] + raw * b["scale"][c]
                (pos if c < 3 else rot).append(v)
            per[b["name"]] = dict(pos=[round(v, 5) for v in pos],
                                  rot_deg=[round(float(np.degrees(v)), 4) for v in rot])
        frames_out.append(dict(frame=f, bones=per))

    motion = [n for bit, n in MOTION_BITS if seq["motiontype"] & bit]
    return dict(
        source=dict(file=os.path.basename(st.path), internal_name=st.name, studio_version=st.version,
                    note="motion data extracted for study and retargeting; no Valve mesh or model file is "
                         "copied, converted or redistributed by this tool"),
        convention=dict(space="right-handed, +X forward, +Y left, +Z up (Quake/GoldSrc)",
                        length_units="Quake units, ~1 unit = 1 inch",
                        rotation="local Euler, composed Rz*Ry*Rx (X applied first); stored radians, "
                                 "reported here in degrees",
                        sampling="exact frames, no interpolation",
                        values="pos/rot are ABSOLUTE local values = bone.value[c] + stored_int16 * bone.scale[c]"),
        # numframes counts what is STORED. The engine wraps f over [0, numframes-1) -- see
        # StudioEstimateFrame: `f -= (int)(f/(numframes-1)) * (numframes-1)`. So on a looping sequence the
        # last stored frame is a duplicate of frame 0 that never plays, and the true cycle is numframes-1
        # long. Retarget on the cycle, not on the stored count, or the loop gets one frame of hitch.
        sequence=dict(index=seq["index"], label=seq["label"], fps=seq["fps"], numframes=seq["numframes"],
                      cycle_frames=(seq["numframes"] - 1) if seq["looping"] else seq["numframes"],
                      cycle_seconds=(round((seq["numframes"] - 1) / seq["fps"], 4)
                                     if seq["looping"] and seq["fps"] else None),
                      duration_s=round(seq["numframes"] / seq["fps"], 4) if seq["fps"] else None,
                      looping=seq["looping"], activity=seq["activity"], numblends=seq["numblends"],
                      blend_used=blend, blendtype=seq["blendtype"],
                      blendstart=seq["blendstart"], blendend=seq["blendend"],
                      seqgroup=seq["seqgroup"], numevents=seq["numevents"],
                      motiontype=seq["motiontype"], motion_flags=motion,
                      motionbone=seq["motionbone"],
                      motionbone_name=(st.bones[seq["motionbone"]]["name"] if 0 <= seq["motionbone"] < st.numbones else None),
                      linearmovement=seq["linearmovement"],
                      motion_note="axes listed in motion_flags are stripped from motionbone by the engine and "
                                  "replaced by entity movement; forward travel usually lives in linearmovement, "
                                  "not in the curve"),
        bones=bones_out, frames=frames_out)


def parse_frames(spec, n):
    """'0:9' or '0,4,8' or '3'. Inclusive ranges, because that is how a person counts frames of a walk."""
    if spec is None:
        return None
    out = []
    for part in spec.split(","):
        if ":" in part:
            a, b = part.split(":")
            out.extend(range(int(a or 0), int(b if b else n - 1) + 1))
        else:
            out.append(int(part))
    bad = [f for f in out if not 0 <= f < n]
    if bad:
        raise SystemExit(f"frame(s) {bad} outside 0..{n - 1}")
    return out


def pick(st, key):
    """Match --seq by index, then exact label (case-insensitive), then unique substring. Ambiguity is an
    error with the candidates printed: silently taking the first match is how you measure the wrong walk."""
    if key.isdigit() and int(key) < st.numseq:
        return st.sequences[int(key)]
    exact = [s for s in st.sequences if s["label"].lower() == key.lower()]
    if len(exact) == 1:
        return exact[0]
    part = [s for s in st.sequences if key.lower() in s["label"].lower()]
    if len(part) == 1:
        return part[0]
    if not part:
        raise SystemExit(f"no sequence matching '{key}' (use --list)")
    raise SystemExit("ambiguous '%s': %s" % (key, ", ".join(f"{s['index']}:{s['label']}" for s in part)))


def main():
    ap = argparse.ArgumentParser(description="dump GoldSrc studio model animation")
    ap.add_argument("model")
    ap.add_argument("--list", action="store_true", help="list sequences and exit")
    ap.add_argument("--bones-only", action="store_true", help="print the bone hierarchy and exit")
    ap.add_argument("--seq", help="sequence name, substring, or index")
    ap.add_argument("--blend", type=int, default=0, help="blend index for multi-blend sequences (default 0)")
    ap.add_argument("--frames", help="frames to dump, e.g. 0:9 or 0,4,8 (default: all)")
    ap.add_argument("--bones", help="comma-separated bone names to keep (default: all)")
    ap.add_argument("-o", "--out", help="write JSON here instead of stdout")
    a = ap.parse_args()

    st = Studio(a.model)

    if a.list or (not a.seq and not a.bones_only):
        # If a dump is also being asked for and it is going to stdout, the listing must not land in the middle
        # of the JSON -- send it to stderr so `--list --seq walk > walk.json` still produces parseable output.
        fh = sys.stderr if (a.seq and not a.out) else sys.stdout
        def say(line=""):
            print(line, file=fh)
        say(f"{a.model}  IDST v{st.version}  '{st.name}'")
        say(f"{st.numbones} bones, {st.numseq} sequences, {st.numseqgroups} sequence group(s)")
        for g in st.seqgroups:
            say(f"  group {g['index']}: label='{g['label']}' file='{g['name']}'")
        say(f"{'idx':>4} {'label':<24} {'fps':>7} {'frames':>7} {'cyc':>5} {'sec':>6} {'blends':>7} "
            f"{'grp':>4} {'act':>4} {'loop':>5}  motion")
        for s in st.sequences:
            mot = "+".join(n for bit, n in MOTION_BITS if s["motiontype"] & bit) or "-"
            lm = s["linearmovement"]
            if any(lm):
                mot += "  lm=(%.1f,%.1f,%.1f)" % tuple(lm)
            cyc = (s["numframes"] - 1) if s["looping"] else s["numframes"]
            dur = cyc / s["fps"] if s["fps"] else 0
            say(f"{s['index']:>4} {s['label']:<24} {s['fps']:>7.2f} {s['numframes']:>7} {cyc:>5} {dur:>6.2f} "
                f"{s['numblends']:>7} {s['seqgroup']:>4} {s['activity']:>4} "
                f"{'yes' if s['looping'] else '':>5}  {mot}")
        if not a.seq:
            return

    if a.bones_only:
        # Which channels actually move is a property of a SEQUENCE, not of the bone, so it is deliberately
        # not in this table -- ask for it with --seq, where each bone carries its own "animated" list.
        print(f"{'idx':>4} {'bone':<24} {'parent':<24} rest_pos (local, +X down the bone)   rest_rot_deg")
        for b in st.bones:
            pn = st.bones[b["parent"]]["name"] if b["parent"] >= 0 else "-"
            r = [np.degrees(v) for v in b["value"][3:]]
            print(f"{b['index']:>4} {b['name']:<24} {pn:<24} "
                  f"({b['value'][0]:8.3f},{b['value'][1]:8.3f},{b['value'][2]:8.3f})   "
                  f"({r[0]:8.2f},{r[1]:8.2f},{r[2]:8.2f})")
        return

    seq = pick(st, a.seq)
    data = dump_sequence(st, seq, blend=a.blend,
                         frames=parse_frames(a.frames, seq["numframes"]),
                         bone_filter=[s.strip() for s in a.bones.split(",")] if a.bones else None)
    js = json.dumps(data, indent=1)
    if a.out:
        open(a.out, "w").write(js)
        print(f"wrote {a.out}: sequence '{seq['label']}' {seq['numframes']} frames @ {seq['fps']}fps, "
              f"{len(data['bones'])} bones", file=sys.stderr)
    else:
        print(js)


if __name__ == "__main__":
    main()
