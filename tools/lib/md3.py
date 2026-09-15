#!/usr/bin/env python3
"""
md3.py -- one robust, dependency-free MD3 reader for this whole workspace.

WHY THIS EXISTS

Before this file, RS_ModelSwapper alone had three independent MD3 parsers
(tools_md3_reorigin.py and tools_md3_render.py each hand-roll their own
struct.unpack_from calls against hardcoded byte offsets; tools_md3_pitch.py
has a fourth, at least reused by three other scripts) plus a fifth in
md3_reload_check.py. None of them validate an offset or count against the
file's actual size before trusting it -- a truncated or hand-edited MD3
either throws a bare struct.error pointing at the wrong line, or an
IndexError three functions away from where the bad read happened, or in the
worst case reads whatever bytes happen to sit past the real data and reports
them as vertices. This is the one parser that is supposed to fail loudly, at
the offset that is actually wrong, with a message that says what was expected
-- and otherwise to just be correct, so nothing downstream has to carry its
own copy of the format ever again.

FORMAT REFERENCE (id Software MD3, as GZDoom and every source port read it)

    Header        108 bytes   ident, version, name, flags, counts, offsets
    Frame          56 bytes   mins, maxs, origin, radius, name        x num_frames
    Tag           112 bytes   name, origin, 3x3 axis                 x num_tags x num_frames
    Surface       108 bytes   its own sub-header, offsets relative to itself
      Shader       68 bytes   name, shader index                     x num_shaders
      Triangle     12 bytes   three vertex indices                   x num_triangles
      ST            8 bytes   texture coordinates                    x num_verts
      XYZNormal     8 bytes   packed position (x1/64) + packed normal x num_verts x num_frames

Usage as a library:

    from md3 import MD3Model
    m = MD3Model.load("pistolet.md3")
    for s in m.surfaces:
        print(s.index, s.name, s.num_verts, s.moves())

Usage from the command line -- a structural self-check, independent of any
one tool's downstream use of the data:

    python md3.py path/to/model.md3
"""

from __future__ import annotations

import math
import struct
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

MD3_IDENT = b"IDP3"
MD3_VERSION = 15

HEADER_FMT = "<4si64s9i"
HEADER_SIZE = struct.calcsize(HEADER_FMT)          # 108
FRAME_FMT = "<10f16s"
FRAME_SIZE = struct.calcsize(FRAME_FMT)             # 56
TAG_FMT = "<64s12f"
TAG_SIZE = struct.calcsize(TAG_FMT)                 # 112
SURFACE_FMT = "<4s64s10i"
SURFACE_SIZE = struct.calcsize(SURFACE_FMT)         # 108
SHADER_FMT = "<64si"
SHADER_SIZE = struct.calcsize(SHADER_FMT)           # 68
TRIANGLE_FMT = "<3i"
TRIANGLE_SIZE = struct.calcsize(TRIANGLE_FMT)       # 12
ST_FMT = "<2f"
ST_SIZE = struct.calcsize(ST_FMT)                   # 8
VERTEX_FMT = "<3hH"
VERTEX_SIZE = struct.calcsize(VERTEX_FMT)           # 8

XYZ_SCALE = 1.0 / 64.0

# A generous ceiling on any count field, chosen to be far above anything a
# real MD3 ships (id's own tools capped surfaces well under this) and far
# below what would silently exhaust memory on a corrupt count. Any file
# claiming more than this is corrupt or lying, and the error says so instead
# of the process hanging or paging to death trying to honour it.
SANE_COUNT_CEILING = 200_000


class MD3Error(ValueError):
	"""Anything wrong with an MD3 file that stops it being read safely.

	Always carries enough in the message to go straight to the byte offset
	and the field that failed -- 'surface 2 (\'mag\') claims ofs_end=9412 but
	the file is only 8004 bytes past the surface start' rather than a bare
	struct.error three stack frames from the actual fault.
	"""


def _decode_name(raw: bytes, what: str) -> str:
	return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _require(cond: bool, msg: str) -> None:
	if not cond:
		raise MD3Error(msg)


def _decode_normal(packed: int) -> Tuple[float, float, float]:
	"""MD3's packed vertex normal, decoded EXACTLY as the engine does
	(GZDoom models_md3.cpp UnpackVector): the HIGH byte is the azimuth, the
	LOW byte the polar angle, each in steps of pi/128.

	The old decoder read the high byte as polar and used 2*pi/255 steps, so
	every mesh decoded here and written back through md3_write came out with
	wrong lighting normals (positions and UVs were always exact). Found by the
	weapons lane, 2026-09-13, by byte-comparing split meshes to their donors."""
	azimuth = ((packed >> 8) & 0xFF) * (math.pi / 128.0)
	polar = (packed & 0xFF) * (math.pi / 128.0)
	nx = math.cos(azimuth) * math.sin(polar)
	ny = math.sin(azimuth) * math.sin(polar)
	nz = math.cos(polar)
	return (nx, ny, nz)


@dataclass
class MD3Frame:
	mins: Tuple[float, float, float]
	maxs: Tuple[float, float, float]
	origin: Tuple[float, float, float]
	radius: float
	name: str


@dataclass
class MD3Tag:
	name: str
	origin: Tuple[float, float, float]
	axis: Tuple[float, ...]   # 9 floats, row-major 3x3


@dataclass
class MD3Shader:
	name: str
	shader_index: int


@dataclass
class MD3Surface:
	index: int
	name: str
	num_frames: int
	shaders: List[MD3Shader] = field(default_factory=list)
	triangles: List[Tuple[int, int, int]] = field(default_factory=list)
	st: List[Tuple[float, float]] = field(default_factory=list)
	# verts[frame][vert] -> (x, y, z) in map units, already scaled.
	verts: List[List[Tuple[float, float, float]]] = field(default_factory=list)
	# normals[frame][vert] -> unit (x, y, z), already decoded.
	normals: List[List[Tuple[float, float, float]]] = field(default_factory=list)

	@property
	def num_verts(self) -> int:
		return len(self.st)

	@property
	def num_triangles(self) -> int:
		return len(self.triangles)

	def centroid(self, frame: int) -> Tuple[float, float, float]:
		"""The average vertex position for one frame -- cheap and stable
		enough to compare frame-to-frame for 'does this surface move', which
		is the only thing most callers actually want a position for."""
		vs = self.verts[frame]
		n = len(vs)
		_require(n > 0, f"surface {self.index} ('{self.name}') has no vertices")
		sx = sum(v[0] for v in vs) / n
		sy = sum(v[1] for v in vs) / n
		sz = sum(v[2] for v in vs) / n
		return (sx, sy, sz)

	def max_centroid_drift(self) -> float:
		"""The largest distance between this surface's centroid on any two
		of its frames. Zero (or near it) means the surface is geometrically
		static across the whole animation, whatever its name claims."""
		if self.num_frames < 2:
			return 0.0
		best = 0.0
		cs = [self.centroid(f) for f in range(self.num_frames)]
		for i in range(len(cs)):
			for j in range(i + 1, len(cs)):
				d = _dist(cs[i], cs[j])
				if d > best:
					best = d
		return best

	def moves(self, threshold: float = 3.0) -> bool:
		return self.max_centroid_drift() >= threshold

	def extent(self, frame: int) -> float:
		"""The largest axis-aligned bounding-box dimension of this surface on
		one frame. THIS IS WHAT 'FAR FROM REST' CANNOT TELL YOU ON ITS OWN.

		A mesh author collapsing a part to a single point (to hide it, at
		full extension) produces a centroid that is often FARTHER from the
		rest pose than the part's genuinely-fully-extended frame is -- a
		point can sit past where the real geometry would -- so picking
		'frame with max centroid drift' as the apex walks straight into that
		trap. Extent answers the question drift cannot: is this still a real
		object on this frame, or has it been squashed to nothing.
		"""
		vs = self.verts[frame]
		_require(len(vs) > 0, f"surface {self.index} ('{self.name}') has no vertices")
		xs = [v[0] for v in vs]
		ys = [v[1] for v in vs]
		zs = [v[2] for v in vs]
		return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

	def is_degenerate(self, frame: int, threshold: float = 1.0) -> bool:
		"""True if this surface has been collapsed toward a point on this
		frame -- the 'hide the part' convention several donor meshes in this
		project use instead of (or alongside) an actual hidden/empty frame."""
		return self.extent(frame) < threshold

	def best_extended_frame(self, candidates: List[int] = None) -> int:
		"""Of the given frames (all of them, if none are named), the one
		farthest from rest (frame 0) THAT IS NOT DEGENERATE. This is the
		right way to answer 'which frame is this part fully drawn out and
		still a real object' -- the plain farthest-from-rest frame is not,
		because it cannot distinguish 'fully extended' from 'collapsed to a
		point past where the real geometry would be'.
		"""
		if candidates is None:
			candidates = list(range(self.num_frames))
		rest = self.centroid(0)
		real = [f for f in candidates if not self.is_degenerate(f)]
		pool = real if real else candidates
		return max(pool, key=lambda f: _dist(self.centroid(f), rest))

	def frame_deltas(self) -> List[float]:
		"""Frame-to-frame centroid movement. deltas[i] is the distance between
		frame i and frame i+1; length is num_frames - 1."""
		return [_dist(self.centroid(i), self.centroid(i + 1)) for i in range(self.num_frames - 1)]

	def stable_plateaus(self, step_threshold: float = 0.5) -> List[Tuple[int, int]]:
		"""Contiguous frame ranges (inclusive start, end) where this surface
		holds still frame-to-frame -- candidate POSES, found by where the
		part actually stops moving rather than assumed to sit at frame 0.

		THIS IS WHY: many meshes in this project pack more than one part's
		travel into one shared frame range (a slide's 25-29 window sharing a
		32-frame file with a magazine's 5-11 window and a casing's own
		range). Frame 0 is not reliably 'the' rest pose for any one part --
		it is wherever that part happens to be sitting outside its own
		active window, which is usually its rest pose but is not guaranteed
		to be. A plateau found by actual stability holds regardless of where
		in the file a part's own window falls.

		Both a real held pose (rest, or fully extended) and a degenerate
		'collapsed to hide it' pose show up as plateaus here -- extent() is
		what tells them apart, deliberately kept as a separate call rather
		than filtered out here, since a caller may want the collapsed one
		too (it is exactly what feedHidden names).
		"""
		if self.num_frames < 2:
			return [(0, max(0, self.num_frames - 1))]
		deltas = self.frame_deltas()
		plateaus = []
		start = 0
		for i, d in enumerate(deltas):
			if d > step_threshold:
				plateaus.append((start, i))
				start = i + 1
		plateaus.append((start, self.num_frames - 1))
		return plateaus


@dataclass
class MD3Model:
	source: str
	name: str
	num_frames: int
	frames: List[MD3Frame] = field(default_factory=list)
	tags: List[List[MD3Tag]] = field(default_factory=list)   # tags[frame][tag]
	surfaces: List[MD3Surface] = field(default_factory=list)

	@classmethod
	def load(cls, path: str) -> "MD3Model":
		with open(path, "rb") as f:
			data = f.read()
		return cls.from_bytes(data, source=path)

	@classmethod
	def from_bytes(cls, data: bytes, source: str = "<bytes>") -> "MD3Model":
		size = len(data)
		_require(size >= HEADER_SIZE,
			f"{source}: file is {size} bytes, too small for even an MD3 header ({HEADER_SIZE})")

		(ident, version, name_raw, flags, num_frames, num_tags, num_surfaces,
		 num_skins, ofs_frames, ofs_tags, ofs_surfaces, ofs_eof) = struct.unpack_from(HEADER_FMT, data, 0)

		_require(ident == MD3_IDENT,
			f"{source}: not an MD3 -- ident is {ident!r}, expected {MD3_IDENT!r}")
		if version != MD3_VERSION:
			# Not fatal -- some tools write nonstandard versions and GZDoom
			# reads them anyway -- but worth the caller knowing.
			pass

		for label, n in (("num_frames", num_frames), ("num_tags", num_tags),
		                  ("num_surfaces", num_surfaces), ("num_skins", num_skins)):
			_require(0 <= n <= SANE_COUNT_CEILING,
				f"{source}: header {label}={n} is out of a sane range (0..{SANE_COUNT_CEILING}) -- file is likely corrupt")

		for label, o in (("ofs_frames", ofs_frames), ("ofs_tags", ofs_tags),
		                  ("ofs_surfaces", ofs_surfaces), ("ofs_eof", ofs_eof)):
			_require(0 <= o <= size,
				f"{source}: header {label}={o} falls outside the file (size {size})")
		_require(ofs_eof <= size,
			f"{source}: header claims ofs_eof={ofs_eof} but the file is only {size} bytes")

		model = cls(source=source, name=_decode_name(name_raw, "model name"), num_frames=num_frames)

		# ---- FRAMES ---------------------------------------------------------
		need = ofs_frames + num_frames * FRAME_SIZE
		_require(need <= size,
			f"{source}: {num_frames} frames from ofs_frames={ofs_frames} need {need} bytes, file has {size}")
		for i in range(num_frames):
			off = ofs_frames + i * FRAME_SIZE
			vals = struct.unpack_from(FRAME_FMT, data, off)
			mins = vals[0:3]
			maxs = vals[3:6]
			origin = vals[6:9]
			radius = vals[9]
			fname = _decode_name(vals[10], "frame name")
			model.frames.append(MD3Frame(mins, maxs, origin, radius, fname))

		# ---- TAGS -------------------------------------------------------------
		# num_tags per frame, laid out frame-major: frame0's tags, then frame1's...
		need = ofs_tags + num_frames * num_tags * TAG_SIZE
		_require(need <= size,
			f"{source}: {num_frames}x{num_tags} tags from ofs_tags={ofs_tags} need {need} bytes, file has {size}")
		for fr in range(num_frames):
			frame_tags: List[MD3Tag] = []
			for t in range(num_tags):
				off = ofs_tags + (fr * num_tags + t) * TAG_SIZE
				vals = struct.unpack_from(TAG_FMT, data, off)
				tname = _decode_name(vals[0], "tag name")
				torigin = vals[1:4]
				taxis = vals[4:13]
				frame_tags.append(MD3Tag(tname, torigin, taxis))
			model.tags.append(frame_tags)

		# ---- SURFACES -----------------------------------------------------
		# Each surface is a self-contained block; the NEXT surface starts at
		# this one's own ofs_end, relative to where THIS surface began -- not
		# a fixed stride. Trusting a bad ofs_end walks the rest of the file
		# off into the weeds, so it is bounds-checked before it is used to
		# step forward.
		surf_off = ofs_surfaces
		for s in range(num_surfaces):
			_require(surf_off + SURFACE_SIZE <= size,
				f"{source}: surface {s} header at {surf_off} runs past the file (size {size})")

			(sident, sname_raw, sflags, s_num_frames, s_num_shaders, s_num_verts,
			 s_num_tris, ofs_tri, ofs_shaders, ofs_st, ofs_xyzn, ofs_send) = \
				struct.unpack_from(SURFACE_FMT, data, surf_off)

			sname = _decode_name(sname_raw, "surface name")
			_require(sident == MD3_IDENT,
				f"{source}: surface {s} ('{sname}') has bad ident {sident!r} at offset {surf_off} -- "
				f"the previous surface's ofs_end likely walked to the wrong place")

			for label, n in (("num_frames", s_num_frames), ("num_shaders", s_num_shaders),
			                  ("num_verts", s_num_verts), ("num_triangles", s_num_tris)):
				_require(0 <= n <= SANE_COUNT_CEILING,
					f"{source}: surface {s} ('{sname}') {label}={n} is out of a sane range")

			if s_num_frames != num_frames:
				# Legal per spec (a surface may in principle carry fewer
				# poses) but every MD3 this project has ever shipped keeps
				# them in lockstep, and a mismatch is the signature of an
				# export gone wrong far more often than an intentional
				# choice -- worth surfacing rather than silently trusting.
				sys.stderr.write(
					f"warning: {source}: surface {s} ('{sname}') has {s_num_frames} frames, "
					f"model header says {num_frames}\n")

			# Sub-block offsets are relative to surf_off. Bounds-check each
			# against ofs_send (this surface's own claimed size) as well as
			# the file, so a corrupt sub-offset is caught before it is used.
			_require(0 <= ofs_send and surf_off + ofs_send <= size,
				f"{source}: surface {s} ('{sname}') ofs_end={ofs_send} puts the next surface "
				f"at {surf_off + ofs_send}, past the file (size {size})")

			def _sub_ok(label: str, ofs: int, count: int, item_size: int) -> int:
				start = surf_off + ofs
				end = start + count * item_size
				_require(0 <= ofs and end <= surf_off + ofs_send,
					f"{source}: surface {s} ('{sname}') {label} at +{ofs} for {count} items "
					f"({item_size}B each) runs past this surface's own ofs_end ({ofs_send})")
				return start

			shaders_start = _sub_ok("ofs_shaders", ofs_shaders, s_num_shaders, SHADER_SIZE)
			tris_start = _sub_ok("ofs_triangles", ofs_tri, s_num_tris, TRIANGLE_SIZE)
			st_start = _sub_ok("ofs_st", ofs_st, s_num_verts, ST_SIZE)
			xyzn_start = _sub_ok("ofs_xyznormal", ofs_xyzn, s_num_frames * s_num_verts, VERTEX_SIZE)

			surf = MD3Surface(index=s, name=sname, num_frames=s_num_frames)

			for i in range(s_num_shaders):
				vals = struct.unpack_from(SHADER_FMT, data, shaders_start + i * SHADER_SIZE)
				surf.shaders.append(MD3Shader(_decode_name(vals[0], "shader name"), vals[1]))

			for i in range(s_num_tris):
				surf.triangles.append(struct.unpack_from(TRIANGLE_FMT, data, tris_start + i * TRIANGLE_SIZE))

			for i in range(s_num_verts):
				surf.st.append(struct.unpack_from(ST_FMT, data, st_start + i * ST_SIZE))

			for fr in range(s_num_frames):
				frame_verts: List[Tuple[float, float, float]] = []
				frame_norms: List[Tuple[float, float, float]] = []
				base = xyzn_start + fr * s_num_verts * VERTEX_SIZE
				for v in range(s_num_verts):
					x, y, z, n = struct.unpack_from(VERTEX_FMT, data, base + v * VERTEX_SIZE)
					frame_verts.append((x * XYZ_SCALE, y * XYZ_SCALE, z * XYZ_SCALE))
					frame_norms.append(_decode_normal(n))
				surf.verts.append(frame_verts)
				surf.normals.append(frame_norms)

			# Cross-check triangle indices actually address real vertices --
			# a truncated or hand-edited surface can pass every offset check
			# above and still reference vertex 9000 in an 80-vertex surface.
			for (a, b, c) in surf.triangles:
				_require(0 <= a < s_num_verts and 0 <= b < s_num_verts and 0 <= c < s_num_verts,
					f"{source}: surface {s} ('{sname}') has a triangle indexing outside its "
					f"{s_num_verts} vertices: ({a}, {b}, {c})")

			model.surfaces.append(surf)
			surf_off += ofs_send

		return model


def _dist(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
	return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)


def _self_check(path: str) -> int:
	try:
		m = MD3Model.load(path)
	except MD3Error as e:
		print(f"FAIL: {e}")
		return 1

	print(f"=== {path} ===")
	print(f"name: {m.name!r}   frames: {m.num_frames}   surfaces: {len(m.surfaces)}   tags/frame: {len(m.tags[0]) if m.tags else 0}")
	print()
	for s in m.surfaces:
		tag = "MOVES" if s.moves() else "static"
		print(f"  [{s.index}] {s.name:20} verts={s.num_verts:5} tris={s.num_triangles:5} "
			f"shaders={len(s.shaders)}  drift={s.max_centroid_drift():7.2f}  {tag}")
	print()
	print("OK -- structurally valid, every offset and index in range.")
	return 0


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print("Usage: python md3.py path/to/model.md3")
		sys.exit(1)
	sys.exit(_self_check(sys.argv[1]))


# ============================================================================
# RIGID FIT (Kabsch) -- how a part ACTUALLY moves, separated from the body.
#
# WHY CENTROIDS ARE NOT ENOUGH. A part's centroid moves when the part
# translates, and it ALSO moves when the whole weapon rotates underneath it,
# and when the part itself rotates about anything other than its own centroid.
# Differencing centroids therefore mixes three motions and reports their sum as
# a translation. Measured on m4a3.md3 that way, the slide reads as 9.47 units
# along (-0.95, -0.27, -0.13) with a per-frame length that bounces 0, 0.6, 7.6,
# 5.4, 1.8, 3.4, 9.5 -- which is not a slide sliding, it is noise.
#
# A rigid fit answers the question actually being asked: what single rotation
# and translation best carries this part's vertices from frame A to frame B.
# The same slide, fitted, is 6.78 units along (-1.0000, 0, -0.0002) -- dead
# along one axis, which is what a slide does.
#
# Kabsch is the standard solution and it is short: centre both point sets,
# take the SVD of their covariance, and the rotation falls out. The only
# subtlety is the reflection guard -- without it, a noisy or near-degenerate
# set can produce a mirror instead of a rotation, which reads as a part
# turning itself inside out.
#
# Pure Python: this runs over a few hundred vertices a handful of times, and a
# numpy dependency for one 3x3 SVD is not worth it for a modding tool.
# ============================================================================

def _mat_mul(A, B):
	return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _transpose(A):
	return [[A[j][i] for j in range(3)] for i in range(3)]


def _det3(A):
	return (A[0][0] * (A[1][1]*A[2][2] - A[1][2]*A[2][1])
	      - A[0][1] * (A[1][0]*A[2][2] - A[1][2]*A[2][0])
	      + A[0][2] * (A[1][0]*A[2][1] - A[1][1]*A[2][0]))


def _svd3(A, iters=64):
	"""One-sided Jacobi SVD of a 3x3, enough for a rigid fit.

	Returns (U, S, Vt). Jacobi rather than anything cleverer because the matrix
	is 3x3 and always will be, and a rotation this is used for needs accuracy
	rather than speed."""
	V = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
	B = [row[:] for row in A]
	for _ in range(iters):
		off = 0.0
		for p in range(2):
			for q in range(p + 1, 3):
				alpha = sum(B[k][p] * B[k][p] for k in range(3))
				beta  = sum(B[k][q] * B[k][q] for k in range(3))
				gamma = sum(B[k][p] * B[k][q] for k in range(3))
				off += abs(gamma)
				if abs(gamma) < 1e-14:
					continue
				zeta = (beta - alpha) / (2.0 * gamma)
				t = (1.0 if zeta >= 0 else -1.0) / (abs(zeta) + math.sqrt(1.0 + zeta * zeta))
				c = 1.0 / math.sqrt(1.0 + t * t)
				s = c * t
				for k in range(3):
					bp, bq = B[k][p], B[k][q]
					B[k][p] = c * bp - s * bq
					B[k][q] = s * bp + c * bq
					vp, vq = V[k][p], V[k][q]
					V[k][p] = c * vp - s * vq
					V[k][q] = s * vp + c * vq
		if off < 1e-14:
			break
	sing = [math.sqrt(sum(B[k][j] * B[k][j] for k in range(3))) for j in range(3)]
	U = [[0.0] * 3 for _ in range(3)]
	for j in range(3):
		if sing[j] > 1e-12:
			for k in range(3):
				U[k][j] = B[k][j] / sing[j]
		else:
			U[j][j] = 1.0
	return U, sing, _transpose(V)


def rigid_fit(src, dst):
	"""Best rotation+translation carrying point list `src` onto `dst`.

	Returns (R, t, rmsd). R is row-major 3x3. rmsd is how well the rigid
	assumption actually held -- a large value means the part DEFORMS and no
	single transform describes it, which is a fact worth knowing rather than
	an error to hide."""
	n = len(src)
	_require(n == len(dst) and n > 0, "rigid_fit needs two equal, non-empty point sets")
	cs = [sum(p[i] for p in src) / n for i in range(3)]
	cd = [sum(p[i] for p in dst) / n for i in range(3)]
	P = [[p[i] - cs[i] for i in range(3)] for p in src]
	Q = [[p[i] - cd[i] for i in range(3)] for p in dst]

	H = [[sum(P[k][i] * Q[k][j] for k in range(n)) for j in range(3)] for i in range(3)]
	U, _s, Vt = _svd3(H)
	V = _transpose(Vt)
	Ut = _transpose(U)
	R = _mat_mul(V, Ut)

	# REFLECTION GUARD. A negative determinant is a mirror, not a rotation --
	# it would report a part as having turned inside out.
	if _det3(R) < 0:
		V2 = [row[:] for row in V]
		for k in range(3):
			V2[k][2] = -V2[k][2]
		R = _mat_mul(V2, Ut)

	t = [cd[i] - sum(R[i][j] * cs[j] for j in range(3)) for i in range(3)]

	err = 0.0
	for k in range(n):
		m = [sum(R[i][j] * src[k][j] for j in range(3)) + t[i] for i in range(3)]
		err += sum((m[i] - dst[k][i]) ** 2 for i in range(3))
	return R, t, math.sqrt(err / n)


def part_motion(model, part_name, ref_name=None, rest_frame=0):
	"""How `part_name` moves, with `ref_name`'s own rigid motion divided out.

	This is the measurement a weapon card wants: a slide's travel along the
	GUN, not along the world, on a mesh where the whole receiver is also
	drifting 25 units. Returns a list of per-frame dicts."""
	surfs = {s.name: s for s in model.surfaces}
	_require(part_name in surfs, f"no surface named {part_name!r}")
	part = surfs[part_name]
	ref = surfs[ref_name] if ref_name else None
	if ref is not None:
		_require(ref_name in surfs, f"no surface named {ref_name!r}")

	out = []
	for f in range(part.num_frames):
		src = part.verts[rest_frame]
		dst = part.verts[f]
		R, t, rmsd = rigid_fit(src, dst)

		if ref is not None:
			# Divide out the reference's own motion, so what remains is the
			# part moving RELATIVE to the body it is mounted in.
			Rr, tr, _ = rigid_fit(ref.verts[rest_frame], ref.verts[f])
			Rrt = _transpose(Rr)
			dt = [t[i] - tr[i] for i in range(3)]
			t = [sum(Rrt[i][j] * dt[j] for j in range(3)) for i in range(3)]
			R = _mat_mul(Rrt, R)

		dist = math.sqrt(sum(x * x for x in t))
		axis = [x / dist for x in t] if dist > 1e-9 else [0.0, 0.0, 0.0]
		ang = math.degrees(math.acos(max(-1.0, min(1.0, (R[0][0] + R[1][1] + R[2][2] - 1.0) / 2.0))))

		# A COLLAPSED FRAME IS NOT A DEFORMING PART, AND THE DIFFERENCE MATTERS.
		#
		# Hiding a part by shrinking it to a single point is a common way for an
		# artist to make a magazine "leave" a gun -- pistolet.md3 does exactly
		# this over frames 12-14. Fitting a rigid transform to a degenerate
		# point cloud is meaningless, and it comes back as a LARGE RMSD, which
		# reads as "this part deforms and cannot be driven".
		#
		# That reading cost this project a donor mesh: pistolet's magazine was
		# written off as non-rigid on the strength of an rmsd of 4.288 that
		# appears at those three frames and nowhere else. Over frames 0-11 it
		# fits to better than 0.01 -- as clean as anything in the archive.
		#
		# So say which it is. A caller filtering on `degenerate` gets the frames
		# where the part is really there; one filtering on rmsd alone does not.
		ext = part.extent(f)
		degenerate = ext < 1e-6
		out.append({"frame": f, "translation": t, "distance": dist,
		            "axis": axis, "degrees": ang, "rmsd": rmsd,
		            "extent": ext, "degenerate": degenerate})
	return out


def usable_frames(motion):
	"""The frames where a part is actually present, in order.

	`motion` is what part_motion returned. Drops collapsed frames, so
	"how far does this part travel" is answered from frames where it exists.
	"""
	return [m for m in motion if not m["degenerate"]]


def best_travel(motion):
	"""The frame of greatest travel among frames where the part is REAL.

	This is the number a weapon card wants -- how far the part goes at full
	extension -- and taking it off a collapsed frame gives a distance the part
	never visibly moves, plus a garbage axis. Returns None if every frame is
	degenerate."""
	live = usable_frames(motion)
	if not live:
		return None
	return max(live, key=lambda m: m["distance"])


