import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
def rep(old, new, count=1):
    global s
    assert s.count(old) >= 1, "anchor missing: " + old[:60]
    s = s.replace(old, new, count)
rep('PLACE_ALL = PLACE7 + ["_scale_x", "_scale_y", "_scale_z"]\n',
    'PLACE_ALL = PLACE7 + ["_scale_x", "_scale_y", "_scale_z"]\nREACH_SUFFIXES = ["_stretch_max", "_soft_start", "_pole_out", "_pole_down", "_pole_back", "_align", "_align_max",\n                  "_align_fade_lo", "_align_fade_span", "_align_conf_lo", "_align_conf_span", "_swivel_rate",\n                  "_twist", "_twist_taper", "_twist_conf_lo", "_twist_conf_span", "_twist_ofs", "_twist_rate",\n                  "_follow", "_follow_max"]\n')
rep('        seat_prefixes.update(m.group(1).split())\n',
    '        seat_prefixes.update(m.group(1).split())\n    reach_prefixes = set()\n    for m in re.finditer(r"LINT-REACH:\\s*([^\\n]+)", zs):\n        reach_prefixes.update(m.group(1).split())\n')
rep('prefixes = set(re.findall(r"PlacementCVars\\s+(\\w+)", modeldef)) | (names - single) | dyn_prefixes | seat_prefixes\n',
    'prefixes = (set(re.findall(r"PlacementCVars\\s+(\\w+)", modeldef)) | (names - single) | dyn_prefixes | seat_prefixes) - reach_prefixes\n')
rep('                    return True\n        return False\n',
    '                    return True\n        return False\n\n    def reach_member(cv):\n        return any(cv == p + s for p in reach_prefixes for s in REACH_SUFFIXES)\n')
rep('if cv in literals or cv in dyn_cvars or cv in single or placement_member(cv):',
    'if cv in literals or cv in dyn_cvars or cv in single or placement_member(cv) or reach_member(cv):')
rep('if placement_member(cv) or cv in single or cv in live_ok:',
    'if placement_member(cv) or cv in single or cv in live_ok or reach_member(cv):')
open(p, "w", encoding="utf-8").write(s)
print("patched")
