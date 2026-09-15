#!/usr/bin/env python3
"""
menu_lint.py -- every slider has to move something.

WHY THIS EXISTS

A slider that points at a cvar nothing reads does nothing, and in a headset it
is indistinguishable from a slider that is broken -- or from the engine being
broken. This project has lost whole nights to exactly that: a placement prefix
set to the literal name "None" silently killed a hand's sliders; a cvar saved
in the ini outranked a changed default; a _scale slider dragged below zero did
nothing because the renderer ignores it. None of those produce an error. All of
them are catchable by reading the files.

So this reads them, on every build, and fails the build on:

  E1  a menu control naming a cvar that CVARINFO does not declare
  E2  a declared cvar nothing consumes -- not read by the ZScript, not part of
      a placement set the renderer reads, not listed as built at runtime
  E3  a ZScript Cvf/Cvb/Cvi/GetCVar read of a cvar that is not declared
  E4  a placement prefix in use that is missing any of its seven cvars, or has
      no sliders in the menu
  E5  a slider whose range does not contain the cvar's default, or a size
      slider that reaches zero or below (the renderer ignores those)

Placement prefixes come from MODELDEF `PlacementCVars` and from single-quoted
name literals in the ZScript. Names built at runtime are declared in comments:

    // LINT-PREFIXES: wm_main_slide wm_off_slide ...
    // LINT-CVARS:    wm_main_slide_travel_x ...

A PAGE WHOSE SLIDERS MUST MOVE THINGS LIVE says so in MENUDEF:

    // LINT-LIVE: WM_GrabMenu WM_HandSeats

Every slider on such a page must name a cvar the RENDERER reads -- a placement
set member, a seat set, or a cvar handed to one of the per-actor channels by
name (ScaleCVar, AlphaCVar, VisibleCVar, FollowActorOfsCVar...). A menu freezes
the playsim, so a script-read slider on a tuning page moves nothing at all while
the person is looking at it, which is the only moment it exists for. E7.

A SEAT-ONLY set is declared the same way:

    // LINT-SEATS: wm_grab_all

A REACH CHAIN'S tuning set (the engine reach chain reads <prefix> plus the REACH_SUFFIXES,
renderer-side, every frame) is declared the same way:

    // LINT-REACH: rs_arm_rt rs_arm_lf

Those are read by AActor.FollowActorOfsCVar, which adds _ofs_x/_ofs_y/_ofs_z to
a followed model's seat and reads nothing else. Requiring the turn and size
cvars there would mean shipping four sliders that move nothing, which is the
very fault this tool exists to catch.

USAGE
    python menu_lint.py PACKAGE_DIR --prefix wm_ [--dep EARLIER_PACKAGE_DIR ...]

--dep names a package this one loads after; its ZScript classes count as
declared for E6 (a MODELDEF block here may draw a class declared there). Cvars
are never taken from it.
"""

from __future__ import annotations

import os
import re
import sys

PLACE7 = ["_ofs_x", "_ofs_y", "_ofs_z", "_yaw", "_pitch", "_roll", "_scale"]
PLACE_OFS = ["_ofs_x", "_ofs_y", "_ofs_z"]
PLACE_ALL = PLACE7 + ["_scale_x", "_scale_y", "_scale_z", "_eyefade_near", "_eyefade_far"]
# The engine reach chain (src/r_data/model_reach.cpp) reads these under each LINT-REACH prefix.
REACH_SUFFIXES = ["_stretch_max", "_soft_start", "_pole_out", "_pole_down", "_pole_back", "_align", "_align_max",
                  "_align_fade_lo", "_align_fade_span", "_align_conf_lo", "_align_conf_span", "_swivel_rate",
                  "_twist", "_twist_taper", "_twist_conf_lo", "_twist_conf_span", "_twist_ofs", "_twist_rate",
                  "_follow", "_follow_max", "_clear_radius", "_clear_max", "_clear_rate", "_aim", "_aim_max"]


def read(path):
    # LUMP NAMES ARE CASE-INSENSITIVE AND IGNORE THE EXTENSION, so this finds
    # "CVARINFO.txt" as cvarinfo, CVARINFO, cvarinfo.lmp ... -- the glow lane's
    # mods ship lower-case, extension-less lumps. A lump that is not there reads
    # as empty rather than stopping the lint.
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    folder, want = os.path.split(path)
    stem = os.path.splitext(want)[0].lower()
    if os.path.isdir(folder or "."):
        for f in sorted(os.listdir(folder or ".")):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and os.path.splitext(f)[0].lower() == stem:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
    return ""


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = argv[1]
    prefix = "wm_"
    if "--prefix" in argv:
        prefix = argv[argv.index("--prefix") + 1]
    # --prefix takes a comma-separated list when a package's own cvars do not
    # share one stem (RS_VR_Weapons: wm_pump,wm_moonlight,...). `prefix` becomes a
    # tuple for startswith and `pre_re` the matching regex alternation; a single
    # prefix behaves exactly as before.
    prefix = tuple(p for p in prefix.split(",") if p)
    pre_re = "(?:" + "|".join(re.escape(p) for p in prefix) + ")"

    cvarinfo = read(os.path.join(root, "CVARINFO.txt"))
    menudef = read(os.path.join(root, "MENUDEF.txt"))
    modeldef = read(os.path.join(root, "MODELDEF.txt"))
    zs = ""
    for dp, _dn, fn in os.walk(os.path.join(root, "zscript")):
        for f in fn:
            if f.endswith(".zs"):
                zs += read(os.path.join(dp, f)) + "\n"

    # ---- declared
    decl = {}
    for m in re.finditer(r"^\s*(?:(?:user|server|nosave|noarchive|cheat|latch)\s+)+"
                         r"(int|float|bool|string|color)\s+(\w+)\s*=\s*([^;]+);",
                         strip_comments(cvarinfo), re.M):
        decl[m.group(2)] = (m.group(1), m.group(3).strip())

    # ---- menu controls
    controls = []
    for m in re.finditer(r'^\s*(Slider|Option|ScaleSlider|ColorPicker|TextField|NumberField)\s+'
                         r'"[^"]*"\s*,\s*"(\w+)"([^\n]*)', strip_comments(menudef), re.M):
        controls.append((m.group(1), m.group(2), m.group(3)))
    menu_cvars = {c[1] for c in controls}

    # ---- consumed by code
    zs_code = strip_comments(zs)
    literals = set(re.findall(r'"(' + pre_re + r'[a-z0-9_]+)"', zs_code))
    reads = set(re.findall(r'(?:Cvf|Cvb|Cvi|GetCVar)\(\s*"(' + pre_re + r'[a-z0-9_]+)"', zs_code))
    names = set(re.findall(r"'(" + pre_re + r"[a-z0-9_]+)'", zs_code))
    dyn_prefixes, dyn_cvars = set(), set()
    for m in re.finditer(r"LINT-PREFIXES:\s*([^\n]+)", zs):
        dyn_prefixes.update(m.group(1).split())
    for m in re.finditer(r"LINT-CVARS:\s*([^\n]+)", zs):
        dyn_cvars.update(m.group(1).split())
    seat_prefixes = set()
    for m in re.finditer(r"LINT-SEATS:\s*([^\n]+)", zs):
        seat_prefixes.update(m.group(1).split())
    reach_prefixes = set()
    for m in re.finditer(r"LINT-REACH:\s*([^\n]+)", zs):
        reach_prefixes.update(m.group(1).split())

    # A NAME LITERAL THAT IS ITSELF A CVAR IS A CVAR, not a placement prefix.
    # Fields like AActor.AlphaCVar and AActor.VisibleCVar are handed one cvar by
    # name, so 'wm_marker_alpha' appears in the ZScript exactly like a prefix
    # does -- and demanding seven placement cvars under it would be nonsense.
    single = {n for n in names if n in decl}
    prefixes = (set(re.findall(r"PlacementCVars\s+(\w+)", modeldef)) | (names - single) | dyn_prefixes | seat_prefixes) - reach_prefixes
    prefixes = {p for p in prefixes if p.startswith(prefix)}

    errors = []

    # ---- E6: every class MODELDEF draws, and every class a card names, must
    # exist. A MODELDEF block for an undeclared class stops the engine at
    # startup ("Unknown actor type"), and a -norun compile check never sees
    # it: -norun exits before models are loaded. That exact bug shipped once.
    declared_classes = {c.lower() for c in re.findall(r"^\s*class\s+(\w+)", zs_code, re.M)}
    # --dep DIR, repeatable: a package this one LOADS AFTER. Its ZScript classes
    # count as declared for E6 only -- a later package's MODELDEF may draw a class
    # the earlier one declares (RS_VR_Weapons draws RS_VR_Reload's WM_LooseMag).
    # Its cvars do not count: each package lints its own.
    for i, a in enumerate(argv):
        if a == "--dep" and i + 1 < len(argv):
            dep_zs = ""
            for dp, _dn, fn in os.walk(os.path.join(argv[i + 1], "zscript")):
                for f in fn:
                    if f.endswith(".zs"):
                        dep_zs += read(os.path.join(dp, f)) + "\n"
            if not dep_zs:
                print(f"menu_lint: --dep {argv[i + 1]} has no zscript/*.zs")
                return 2
            declared_classes |= {c.lower() for c in re.findall(r"^\s*class\s+(\w+)", strip_comments(dep_zs), re.M)}
    # The block header only: `Model WM_Name` and nothing after it but a brace.
    # The looser pattern also matched the `Model 0 "file.md3"` line INSIDE
    # every block and reported a class called "0".
    for cls in re.findall(r"^\s*Model\s+([A-Za-z_]\w*)\s*(?:\{.*)?$", strip_comments(modeldef), re.M):
        if cls.lower() not in declared_classes:
            errors.append(f"E6 MODELDEF draws '{cls}', which no ZScript here declares -- the engine stops at startup")
    card_path = os.path.join(root, "WMCARD.txt")
    if os.path.exists(card_path):
        card_text = read(card_path)
        wanted = re.findall(r'^\s*weapon\s+"(\w+)"', card_text, re.M | re.I)
        wanted += re.findall(r'^\s*prop\s*=\s*"(\w+)"', card_text, re.M | re.I)
        for cls in wanted:
            if cls.lower() not in declared_classes:
                errors.append(f"E6 WMCARD names class '{cls}', which no ZScript here declares")

    for kind, cv, _rest in controls:
        if cv.startswith(prefix) and cv not in decl:
            errors.append(f"E1 menu {kind} names '{cv}', which CVARINFO does not declare")

    def placement_member(cv):
        for p in prefixes:
            for s in PLACE_ALL:
                if cv == p + s:
                    return True
        return False

    def reach_member(cv):
        return any(cv == p + s for p in reach_prefixes for s in REACH_SUFFIXES)

    for cv in decl:
        if not cv.startswith(prefix):
            continue
        if cv in literals or cv in dyn_cvars or cv in single or placement_member(cv) or reach_member(cv):
            continue
        errors.append(f"E2 '{cv}' is declared but nothing reads it -- a slider on it would be dead")

    for cv in sorted(reads):
        if cv not in decl:
            errors.append(f"E3 the ZScript reads '{cv}', which CVARINFO does not declare")

    for p in sorted(prefixes):
        # A seat-only set is read by FollowActorOfsCVar, which takes the three
        # offsets and nothing else -- see LINT-SEATS in the header.
        want = PLACE_OFS if p in seat_prefixes else PLACE7
        missing = [p + s for s in want if p + s not in decl]
        if missing:
            errors.append(f"E4 placement set '{p}' is missing {missing}")
        # Any of the ten, not just the seven: a set steered only by its three
        # per-axis scales is a real set -- that is how a drawn oval is shaped.
        # A set named at RUN TIME (LINT-PREFIXES) usually has run-time rows too:
        # a page built from whatever gun is loaded cannot be written in MENUDEF,
        # so there is nothing here to find. The declaration is the promise.
        if p in dyn_prefixes or p in seat_prefixes:
            continue
        if not any((p + s) in menu_cvars for s in (want + PLACE_ALL)):
            errors.append(f"E4 placement set '{p}' has no sliders in the menu")

    # ---- E7: every slider on a LIVE page is read by the renderer.
    #
    # The fault this catches shipped twice in one day: sliders added to a tuning
    # page, read by script, dead behind the menu they live on. Nothing else
    # notices -- they compile, they save, they even work once the menu closes.
    live_pages = set()
    for m in re.finditer(r"LINT-LIVE:\s*([^\n]+)", menudef):
        live_pages.update(m.group(1).split())
    # Rows that pick WHAT is being tuned rather than moving it. A selector's job
    # is done by the page itself -- it lights the right thing through a gate the
    # renderer reads -- so it needs no channel of its own.
    live_ok = set()
    for m in re.finditer(r"LINT-LIVE-OK:\s*([^\n]+)", menudef):
        live_ok.update(m.group(1).split())
    # A cvar a clearscope UiTick path pushes every frame moves live under a menu
    # too, so the ZScript that pushes it may vouch for it beside the push:
    #     // LINT-UI-LIVE: rsf_density rsf_tint_r ...
    for m in re.finditer(r"LINT-UI-LIVE:\s*([^\n]+)", zs):
        live_ok.update(m.group(1).split())
    if live_pages:
        blocks = re.findall(r'(?im)^\s*OptionMenu\s+"?([A-Za-z0-9_]+)"?\s*\r?\n\s*\{(.*?)^\s*\}',
                            strip_comments(menudef), re.S | re.M)
        for page, body in blocks:
            if page not in live_pages:
                continue
            for m in re.finditer(r'^\s*(Slider|ScaleSlider|ColorPicker)\s+"[^"]*"\s*,\s*"(\w+)"',
                                 body, re.M):
                cv = m.group(2)
                if placement_member(cv) or cv in single or cv in live_ok or reach_member(cv):
                    continue
                errors.append(f"E7 '{cv}' is on live page {page} but nothing in the RENDERER reads it"
                              f" -- it will not move anything while the menu is open")

    for kind, cv, rest in controls:
        if kind != "Slider" or cv not in decl:
            continue
        nums = re.findall(r"-?\d+(?:\.\d+)?", rest)
        if len(nums) < 2:
            continue
        lo, hi = float(nums[0]), float(nums[1])
        try:
            dv = float(decl[cv][1])
        except ValueError:
            continue
        if not (min(lo, hi) - 1e-9 <= dv <= max(lo, hi) + 1e-9):
            errors.append(f"E5 slider '{cv}' runs {lo}..{hi} but defaults to {dv}")
        if re.search(r"_scale(_[xyz])?$", cv) and placement_member(cv) and lo <= 0:
            errors.append(f"E5 size slider '{cv}' reaches {lo}; the renderer ignores zero and below")

    print(f"menu_lint: {len(decl)} cvars, {len(controls)} menu controls, "
          f"{len(prefixes)} placement sets, {len(reads)} code reads")
    for e in errors:
        print("  " + e)
    if errors:
        print(f"menu_lint: {len(errors)} problem(s)")
        return 1
    print("menu_lint: every slider moves something")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
