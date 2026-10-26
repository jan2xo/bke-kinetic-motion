"""
mg3d - 2.5D module for bke-kinetic-motion (v2.1). Flat textured cards in real 3D space, CPU only.

Python + NumPy + Pillow (+ FFmpeg for encoding, via the kit). No GPU, no Blender, no new framework.
Read docs/3D_DECISIONS.md first: real 3D is used only when space carries meaning; otherwise fake depth in 2D.

Coordinate system (right-handed, Y up). Units are "design pixels": a card of width 240 placed on the plane z = 0
and seen by the default camera at distance Camera.design_distance() covers exactly 240 output pixels.

  Camera   position, target, up, vertical FOV (or lens_mm, 24 mm sensor height), look-at matrix, projection
  CameraRig ONE move per shot (dolly | orbit <= 25 deg | crane), slow-in/slow-out easing, never overshoot
  Track    keyframed values (scalars or vectors) eased with mglib curves
  Card     textured quad (Pillow RGBA) with a 3D transform (pos, rot (rx, ry, rz) in degrees, scale, alpha)
  Renderer projects the 4 corners, warps with Image.transform(PERSPECTIVE), composites back to front (painter's
           algorithm), culls behind-camera and edge-on cards, depth of field by z-band, fog/dimming by depth,
           drop shadows on a ground plane, one accent key light (rim/edge glow brightened by facing angle) + ambient
  helpers  floor_grid, card_wall (grid layout in 3D), scatter (seeded volume), scatter_align (interpolates transforms)
  lint     lint_rig / tilt_deg / check_readable: the decision rules as code

  python3 mg3d.py bench [--cards 30] [--frames 6] [--S 2]   # speed at 1080p
  python3 mg3d.py demo out.png                               # one still

Every frame is still a pure function of t (mglib rule), so frames render in parallel with mglib.render_all.
"""
import math, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mglib as M

EASE = {'linear': lambda x: x, 'eo': M.eo, 'ei': M.ei, 'eio': M.eio,
        'expo_out': M.eo, 'expo_in': M.ei, 'cubic_in_out': M.eio,
        'sine_in_out': lambda x: 0.5 - 0.5 * math.cos(math.pi * x)}
NO_OVERSHOOT = set(EASE)          # back_out / elastic are deliberately absent: cameras and headlines never overshoot
SENSOR_H_MM = 24.0                # full-frame sensor height: "35-50 mm equivalent"


# ------------------------------------------------------------------ maths
def v3(x): return np.asarray(x, np.float64).reshape(3)
def norm(v):
    n = float(np.linalg.norm(v)); return v / n if n > 1e-12 else v
def fov_from_mm(mm, sensor_h=SENSOR_H_MM): return math.degrees(2 * math.atan(sensor_h / (2.0 * mm)))
def mm_from_fov(fov_deg, sensor_h=SENSOR_H_MM): return sensor_h / (2 * math.tan(math.radians(fov_deg) / 2))

def rot_matrix(rx, ry, rz):
    """R = Ry @ Rx @ Rz (degrees): spin in plane, then tilt, then yaw."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


# ------------------------------------------------------------------ animation
class Track:
    """Keyframed value. keys: [(t, value), (t, value, 'eio'), ...]; the ease on a key shapes the segment ENDING there.
    Values may be scalars or sequences (vectors). Before the first key / after the last, the value holds."""
    def __init__(self, keys, ease='eio'):
        self.keys = sorted([(float(k[0]), np.asarray(k[1], np.float64), k[2] if len(k) > 2 else ease) for k in keys], key=lambda k: k[0])
        for k in self.keys:
            if k[2] not in EASE: raise ValueError(f'easing {k[2]!r} not allowed (no overshoot curves on 3D moves)')

    def __call__(self, t):
        ks = self.keys
        if t <= ks[0][0]: return ks[0][1].copy()
        for (t0, v0, _), (t1, v1, e) in zip(ks, ks[1:]):
            if t <= t1:
                x = EASE[e](M.prog(t, t0, t1)); return v0 + (v1 - v0) * x
        return ks[-1][1].copy()

    @property
    def span(self): return self.keys[0][0], self.keys[-1][0]


# ------------------------------------------------------------------ camera
class Camera:
    def __init__(self, pos=(0, 0, 1800), target=(0, 0, 0), up=(0, 1, 0), fov=None, lens_mm=40.0, W=None, H=None, near=60.0):
        self.pos, self.target, self.up = v3(pos), v3(target), v3(up)
        self.fov = float(fov) if fov is not None else fov_from_mm(lens_mm)     # vertical, degrees
        self.W, self.H = W or M.Cfg.W, H or M.Cfg.H
        self.near = near
        self._basis()

    @staticmethod
    def design_distance(fov=None, lens_mm=40.0, H=None):
        """Distance at which 1 world unit on z=0 maps to 1 output pixel."""
        f = float(fov) if fov is not None else fov_from_mm(lens_mm)
        return (H or M.Cfg.H) / 2 / math.tan(math.radians(f) / 2)

    def _basis(self):
        f = norm(self.target - self.pos)
        r = norm(np.cross(f, self.up))
        if np.linalg.norm(r) < 1e-9: r = np.array([1.0, 0, 0])
        u = np.cross(r, f)
        self.fwd, self.right, self.upv = f, r, u
        self.fpx = self.H / 2 / math.tan(math.radians(self.fov) / 2)        # focal length in output pixels

    @property
    def lens_mm(self): return mm_from_fov(self.fov)

    def view_matrix(self):
        """4x4 look-at (OpenGL convention: camera looks down -Z in view space)."""
        r, u, f = self.right, self.upv, self.fwd
        Mv = np.eye(4); Mv[0, :3], Mv[1, :3], Mv[2, :3] = r, u, -f
        Mv[:3, 3] = -Mv[:3, :3] @ self.pos
        return Mv

    def projection_matrix(self, far=1e5):
        a = self.W / self.H; f = 1 / math.tan(math.radians(self.fov) / 2); n = self.near
        return np.array([[f / a, 0, 0, 0], [0, f, 0, 0], [0, 0, (far + n) / (n - far), 2 * far * n / (n - far)], [0, 0, -1, 0]])

    def to_camera(self, P):
        """World points (N,3) -> camera space (N,3) with x right, y up, z = depth in front of the lens."""
        d = np.atleast_2d(P) - self.pos
        return np.stack([d @ self.right, d @ self.upv, d @ self.fwd], -1)

    def project(self, P):
        """World points (N,3) -> screen (N,2) in OUTPUT pixels, and depth (N,). Depth <= 0 means behind the camera."""
        c = self.to_camera(P); z = c[:, 2]
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        sx = self.W / 2 + self.fpx * c[:, 0] / zs
        sy = self.H / 2 - self.fpx * c[:, 1] / zs
        return np.stack([sx, sy], -1), z


class CameraRig:
    """One camera move per shot. kind: 'static' | 'dolly' | 'orbit' | 'crane'. All moves ease slow-in/slow-out
    (default 'eio'); overshooting curves are refused. lint_rig() checks the rest of the rules."""
    MAX_ORBIT = 25.0

    def __init__(self, kind, t0, t1, *, lens_mm=40.0, target=(0, 0, 0), ease='eio', **p):
        if ease not in NO_OVERSHOOT: raise ValueError(f'camera ease {ease!r} would overshoot or is unknown')
        self.kind, self.t0, self.t1, self.lens_mm, self.ease, self.p = kind, float(t0), float(t1), float(lens_mm), ease, p
        self.target = v3(target)
        if kind == 'orbit' and abs(p.get('az1', 0) - p.get('az0', 0)) > self.MAX_ORBIT + 1e-9:
            raise ValueError(f"orbit of {abs(p['az1'] - p['az0']):.1f} deg exceeds {self.MAX_ORBIT} deg")
        if kind not in ('static', 'dolly', 'orbit', 'crane'): raise ValueError(f'unknown move {kind!r}')

    def k(self, t): return EASE[self.ease](M.prog(t, self.t0, self.t1)) if self.t1 > self.t0 else 1.0

    def at(self, t, W=None, H=None):
        k = self.k(t); p = self.p; tg = self.target
        if self.kind == 'static':
            pos = v3(p.get('pos', (0, 0, Camera.design_distance(lens_mm=self.lens_mm))))
        elif self.kind == 'dolly':          # straight line along the view axis (or any two points)
            a, b = v3(p['from']), v3(p['to']); pos = a + (b - a) * k
        elif self.kind == 'crane':          # vertical rise or fall, target fixed
            a = v3(p['pos']); pos = a + np.array([0, (p['y1'] - p['y0']) * k + p['y0'] - a[1], 0])
        else:                               # orbit around target in the horizontal plane
            az = math.radians(p['az0'] + (p['az1'] - p['az0']) * k); r = p['radius']; el = math.radians(p.get('elev', 0))
            pos = tg + np.array([r * math.sin(az) * math.cos(el), r * math.sin(el), r * math.cos(az) * math.cos(el)])
        return Camera(pos, tg, lens_mm=self.lens_mm, W=W, H=H)

    def velocity(self, t, dt=1 / 60):
        return float(np.linalg.norm(self.at(t + dt).pos - self.at(t - dt).pos) / (2 * dt))


# ------------------------------------------------------------------ cards
class Card:
    """A textured quad. tex: Pillow RGBA. size: (w, h) in world units (design px on z=0).
    xf: dict(pos=(x,y,z), rot=(rx,ry,rz) degrees, scale=float, alpha=0..1). is_text marks type (readability rule)."""
    def __init__(self, tex, size=None, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0, alpha=1.0, is_text=False, shadow=True, rim=True, name='', layer=0):
        self.tex = tex
        self.size = size or (tex.width / M.Cfg.S, tex.height / M.Cfg.S)
        self.pos, self.rot, self.scale, self.alpha = v3(pos), tuple(rot), float(scale), float(alpha)
        self.is_text, self.shadow, self.rim, self.name = is_text, shadow, rim, name
        self.layer = layer          # draw-order override: higher layers composite after lower ones (type that must stay readable)

    def with_xf(self, pos=None, rot=None, scale=None, alpha=None):
        c = Card.__new__(Card); c.__dict__.update(self.__dict__)
        if pos is not None: c.pos = v3(pos)
        if rot is not None: c.rot = tuple(rot)
        if scale is not None: c.scale = float(scale)
        if alpha is not None: c.alpha = float(alpha)
        return c

    def corners(self):
        """World corners TL, TR, BR, BL (texture order)."""
        w, h = self.size[0] * self.scale / 2, self.size[1] * self.scale / 2
        L = np.array([[-w, h, 0], [w, h, 0], [w, -h, 0], [-w, -h, 0]], np.float64)
        return L @ rot_matrix(*self.rot).T + self.pos

    def normal(self): return rot_matrix(*self.rot) @ np.array([0, 0, 1.0])


def tilt_deg(card, cam):
    """Angle between the card's normal and the camera's view axis (0 = parallel to the image plane = frontal).
    A card parallel to the image plane projects without foreshortening anywhere in frame, so this is the angle
    that decides readability (not the angle to the line of sight, which is non-zero for any off-centre card)."""
    c = abs(float(card.normal() @ cam.fwd))
    return math.degrees(math.acos(min(1.0, c)))


# ------------------------------------------------------------------ perspective warp
def perspective_coeffs(dst, src):
    """Coefficients for Image.transform(PERSPECTIVE): maps OUTPUT points dst[i] -> INPUT points src[i]."""
    A = []; B = []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.asarray(A, np.float64), np.asarray(B, np.float64)).tolist()


# ------------------------------------------------------------------ renderer
class Renderer:
    """Draws cards for one camera into a supersampled RGBA canvas (mglib conventions: draw at S, LANCZOS down).

    dof:    dict(focus=<camera-space depth of the focus plane>, max_px=<blur radius at full defocus, output px>,
            bands=5, aperture=<defocus scale>) or None. Blur radius is quantised to `bands` z-bands.
    fog:    dict(near=, far=, max=0..1, color=(r,g,b)) dims and tints by camera depth.
    light:  dict(pos=(x,y,z) world, color=accent, ambient=0..1, key=0..1, rim=0..1) ONE key light + ambient.
    shadow: dict(ground_y=, dir=(dx,dy,dz) light travel direction, strength=, blur=) drop shadows on y = ground_y.
    """
    def __init__(self, cam, dof=None, fog=None, light=None, shadow=None, edge_cull_deg=85.0, near_fade=(80.0, 380.0), backface='dim'):
        self.cam = cam; self.dof = dof; self.fog = fog; self.light = light; self.shadow = shadow
        self.edge_cos = math.cos(math.radians(edge_cull_deg)); self.near_fade = near_fade; self.backface = backface
        self.stats = dict(drawn=0, culled_behind=0, culled_edge=0, culled_offscreen=0)

    # -------- per-card decisions (pure, unit-tested)
    def classify(self, card):
        """'draw' | 'behind' | 'edge' | 'offscreen' for one card with the current camera."""
        C = card.corners(); scr, z = self.cam.project(C)
        if (z < self.cam.near).any(): return 'behind', scr, z
        to_cam = norm(self.cam.pos - card.pos)
        if abs(float(card.normal() @ to_cam)) < self.edge_cos: return 'edge', scr, z
        x0, y0 = scr.min(0); x1, y1 = scr.max(0)
        if x1 < -50 or y1 < -50 or x0 > self.cam.W + 50 or y0 > self.cam.H + 50: return 'offscreen', scr, z
        return 'draw', scr, z

    def depth(self, card): return float(self.cam.to_camera(card.pos[None])[0, 2])

    def sort(self, cards):
        """Painter's algorithm: farthest first (by camera depth of the card centre), within each `layer`.
        layer > 0 lifts a card above everything in lower layers regardless of depth: use it only for type that must be
        read and would otherwise be crossed by a card in front of it (readability beats physical correctness)."""
        return sorted(cards, key=lambda c: (getattr(c, 'layer', 0), -self.depth(c)))

    def dof_radius(self, z):
        """Gaussian radius (output px) from distance to the focus plane, quantised to z-bands."""
        d = self.dof
        if not d: return 0.0
        coc = d.get('aperture', 1.0) * abs(z - d['focus']) / max(z, 1.0)          # thin-lens-like circle of confusion
        full = d.get('full_at', 0.6)                                                # coc at which blur saturates
        x = min(1.0, coc / full); n = int(d.get('bands', 5))
        band = int(math.floor(x * (n - 1) + 0.5))
        return band / (n - 1) * d.get('max_px', 8.0)

    def dof_band(self, z):
        d = self.dof
        if not d: return 0
        return int(round(self.dof_radius(z) / d.get('max_px', 8.0) * (int(d.get('bands', 5)) - 1)))

    def fog_amount(self, z):
        f = self.fog
        if not f: return 0.0
        x = M.clamp((z - f['near']) / (f['far'] - f['near']))
        return f.get('max', 0.7) * x * x * (3 - 2 * x)

    def light_terms(self, card, facing_n):
        """(shade multiplier for the texture, rim intensity 0..1). One key light + ambient."""
        L = self.light
        if not L: return 1.0, 0.0
        ldir = norm(v3(L['pos']) - card.pos)
        ndl = max(0.0, float(facing_n @ ldir))
        shade = L.get('ambient', 0.72) + L.get('key', 0.28) * ndl
        view = norm(self.cam.pos - card.pos)
        graze = 1.0 - abs(float(facing_n @ view))                    # edge-on to the viewer = brighter rim
        rim = L.get('rim', 0.8) * (0.25 + 0.75 * ndl) ** 2 * (0.45 + 0.55 * min(1.0, graze * 3.0))
        return shade, M.clamp(rim)

    # -------- drawing
    def floor_grid(self, base, ground_y=-700, x_span=(-4000, 4000), z_span=(-3000, 3000), step=250, alpha=0.06, color=(255, 255, 255)):
        """Perspective floor grid on y = ground_y, faded by fog (drawn on the supersampled canvas)."""
        S = M.Cfg.S; lay = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        segs = []
        for x in np.arange(x_span[0], x_span[1] + 1, step):
            zs = np.linspace(z_span[0], z_span[1], 24); segs.append(np.stack([np.full_like(zs, x), np.full_like(zs, ground_y), zs], -1))
        for z in np.arange(z_span[0], z_span[1] + 1, step):
            xs = np.linspace(x_span[0], x_span[1], 24); segs.append(np.stack([xs, np.full_like(xs, ground_y), np.full_like(xs, z)], -1))
        for P in segs:
            scr, zc = self.cam.project(P)
            for k in range(len(P) - 1):
                if zc[k] < self.cam.near * 2 or zc[k + 1] < self.cam.near * 2: continue
                zm = 0.5 * (zc[k] + zc[k + 1]); a = alpha * (1 - self.fog_amount(zm)) * M.clamp((zm - 200) / 600)
                if a < 0.004: continue
                d.line([(scr[k, 0] * S, scr[k, 1] * S), (scr[k + 1, 0] * S, scr[k + 1, 1] * S)], fill=color + (int(255 * a),), width=S)
        base.alpha_composite(lay)

    def shadows(self, base, cards):
        """Soft drop shadows of all cards on the ground plane, drawn at 1/4 res and blurred once."""
        sh = self.shadow
        if not sh: return
        q = 4; S = M.Cfg.S; W, H = base.size[0] // q, base.size[1] // q
        m = Image.new('L', (W, H), 0); d = ImageDraw.Draw(m)
        ld = norm(v3(sh.get('dir', (0.15, -1, -0.35)))); gy = sh.get('ground_y', -700)
        for c in cards:
            if not c.shadow or c.alpha < 0.02: continue
            C = c.corners(); s_ = (gy - C[:, 1]) / ld[1]
            if (s_ < 0).any(): continue
            G = C + s_[:, None] * ld[None]; scr, z = self.cam.project(G)
            if (z < self.cam.near).any(): continue
            hgt = float(c.pos[1] - gy)
            a = sh.get('strength', 0.45) * c.alpha * M.clamp(1.2 - hgt / 1600) * (1 - self.fog_amount(float(z.mean())))
            if a <= 0.01: continue
            d.polygon([(x * S / q, y * S / q) for x, y in scr], fill=int(255 * min(1, a)))
        m = m.filter(ImageFilter.GaussianBlur(sh.get('blur', 10) * S / q)).resize(base.size, Image.BILINEAR)
        lay = Image.new('RGBA', base.size, (0, 0, 0, 0)); lay.putalpha(m)
        base.alpha_composite(lay)

    def draw_card(self, base, card):
        st, scr, z = self.classify(card)
        if st != 'draw':
            self.stats['culled_' + st] += 1; return None
        S = M.Cfg.S; zc = self.depth(card)
        n = card.normal(); to_cam = norm(self.cam.pos - card.pos); front = float(n @ to_cam) >= 0
        if not front and (self.backface == 'cull' or card.is_text):
            self.stats['culled_edge'] += 1; return None
        nf = n if front else -n
        a = card.alpha * M.clamp((zc - self.near_fade[0]) / max(1.0, self.near_fade[1] - self.near_fade[0]))
        if a < 0.01: return None
        r = self.dof_radius(zc); pad = int(math.ceil(r * 3 * S)) + 4 * S
        P = scr * S; x0, y0 = np.floor(P.min(0)).astype(int) - pad; x1, y1 = np.ceil(P.max(0)).astype(int) + pad
        cx0, cy0 = max(x0, -pad), max(y0, -pad); cx1, cy1 = min(x1, base.width + pad), min(y1, base.height + pad)   # clip huge near cards
        w, h = int(cx1 - cx0), int(cy1 - cy0)
        if w < 2 or h < 2: return None
        tw, th = card.tex.size
        dst = [(px - cx0, py - cy0) for px, py in P]
        src = [(0, 0), (tw, 0), (tw, th), (0, th)]
        try: co = perspective_coeffs(dst, src)
        except np.linalg.LinAlgError: return None
        lay = card.tex.transform((w, h), Image.PERSPECTIVE, co, Image.BICUBIC)
        shade, rim = self.light_terms(card, nf)
        if not front: shade *= 0.55
        fog = self.fog_amount(zc)
        arr = np.asarray(lay, np.float32)
        rgb, al = arr[..., :3], arr[..., 3:4]
        fc = np.array(self.fog.get('color', (8, 9, 12)) if self.fog else (0, 0, 0), np.float32)
        rgb = rgb * (shade * (1 - fog)) + fc * fog
        if card.rim and rim > 0.02 and self.light:
            edge = Image.new('L', (w, h), 0); ImageDraw.Draw(edge).line(dst + [dst[0]], fill=255, width=max(1, int(1.6 * S)), joint='curve')
            sm = edge.resize((max(1, w // 4), max(1, h // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.2 * S / 4 + 0.5)).resize((w, h), Image.BILINEAR)
            e = (np.asarray(edge, np.float32) * 0.9 + np.asarray(sm, np.float32) * 1.6)[..., None] / 255.0 * rim * (1 - fog)
            e = np.clip(e, 0, 1); acc = np.array(self.light.get('color', M.GOLD), np.float32)
            rgb = rgb * (1 - e) + acc * e; al = np.maximum(al, e * 255 * 0.85)
        out = np.concatenate([np.clip(rgb, 0, 255), al * a], -1).astype(np.uint8)
        lay = Image.fromarray(out, 'RGBA')
        if r >= 0.4:                         # depth of field: this card's z-band radius, blurred at reduced res
            f = max(1, int(r * S / 3)); small = lay.resize((max(1, w // f), max(1, h // f)), Image.BILINEAR)
            lay = small.filter(ImageFilter.GaussianBlur(r * S / f)).resize((w, h), Image.BILINEAR)
        M.comp(base, lay, cx0, cy0)
        self.stats['drawn'] += 1
        return dict(name=card.name, depth=zc, dof=r, band=self.dof_band(zc), fog=fog, rim=rim)

    def render(self, base, cards, floor=None):
        """Floor grid -> shadows -> cards back to front. Returns per-card draw info (front-most last)."""
        if floor is not None: self.floor_grid(base, **floor)
        self.shadows(base, cards)
        return [x for x in (self.draw_card(base, c) for c in self.sort(cards)) if x]


# ------------------------------------------------------------------ layout helpers
def card_wall(n, cols, cell=(260, 168), center=(0, 0, 0), order='rows'):
    """Grid layout in 3D: list of dict(pos, rot, col, row) for n cards, row-major, centred on `center`."""
    rows = int(math.ceil(n / cols)); cx, cy, cz = center; out = []
    for i in range(n):
        c, r = i % cols, i // cols
        x = cx + (c - (cols - 1) / 2) * cell[0]; y = cy - (r - (rows - 1) / 2) * cell[1]
        out.append(dict(pos=(x, y, cz), rot=(0, 0, 0), col=c, row=r))
    return out


def scatter(n, seed=1, x=(-1500, 1500), y=(-700, 700), z=(-1600, 1200), rot=(35, 55, 25), avoid_axis=260):
    """Seeded random transforms in a volume. avoid_axis keeps cards out of a tube around the view axis so a
    dolly passes between them instead of through them."""
    rng = np.random.default_rng(seed); out = []
    while len(out) < n:
        p = np.array([rng.uniform(*x), rng.uniform(*y), rng.uniform(*z)])
        if math.hypot(p[0], p[1]) < avoid_axis: continue
        out.append(dict(pos=tuple(p), rot=tuple(rng.uniform(-r, r) for r in rot), drift=tuple(rng.uniform(-1, 1, 3)), spin=tuple(rng.uniform(-1, 1, 3))))
    return out


def lerp_xf(a, b, k):
    """Interpolate two transforms (pos, rot, scale, alpha) by k in 0..1 (k already eased)."""
    pa, pb = v3(a['pos']), v3(b['pos']); ra, rb = np.asarray(a.get('rot', (0, 0, 0)), float), np.asarray(b.get('rot', (0, 0, 0)), float)
    return dict(pos=tuple(pa + (pb - pa) * k), rot=tuple(ra + (rb - ra) * k),
                scale=a.get('scale', 1.0) + (b.get('scale', 1.0) - a.get('scale', 1.0)) * k,
                alpha=a.get('alpha', 1.0) + (b.get('alpha', 1.0) - a.get('alpha', 1.0)) * k)


def scatter_align(froms, tos, t, t0, dur=0.5, stagger=0.0, order=None, ease='eo'):
    """Interpolate many cards from scattered to aligned transforms. Card i starts at t0 + rank_i * stagger
    (rank from `order`, default index) and arrives with `ease` (expo-out by default: arrive role)."""
    out = []; f = EASE[ease]
    for i, (a, b) in enumerate(zip(froms, tos)):
        k_ = order[i] if order is not None else i; s = t0 + k_ * stagger
        out.append(lerp_xf(a, b, f(M.prog(t, s, s + dur))))
    return out


# ------------------------------------------------------------------ lint: the decision rules as code
def lint_rig(rigs, shot_span=None):
    """Return a list of (level, message). rigs: CameraRig list for ONE shot."""
    out = []
    moving = [r for r in rigs if r.kind != 'static']
    if len(moving) > 1:
        for a in moving:
            for b in moving:
                if a is not b and a.t0 < b.t1 and b.t0 < a.t1:
                    out.append(('FAIL', f'stacked camera moves: {a.kind} {a.t0}-{a.t1}s overlaps {b.kind} {b.t0}-{b.t1}s')); break
        out.append(('FAIL', f'{len(moving)} camera moves in one shot; use one (dolly, orbit <= 25 deg, or crane)'))
    for r in rigs:
        if not (35.0 - 1e-6 <= r.lens_mm <= 50.0 + 1e-6):
            out.append(('FAIL', f'lens {r.lens_mm:.0f} mm is outside 35-50 mm: wide lenses distort type'))
        if r.ease not in ('eio', 'cubic_in_out', 'sine_in_out') and r.kind != 'static':
            out.append(('WARN', f'camera ease {r.ease!r}: use slow-in/slow-out (cubic or sine in-out)'))
        if r.kind != 'static':
            v0, v1 = r.velocity(r.t0 + 1e-3), r.velocity(r.t1 - 1e-3)
            vmax = max(r.velocity(r.t0 + (r.t1 - r.t0) * x) for x in (0.25, 0.5, 0.75))
            if vmax > 0 and (v0 > 0.15 * vmax or v1 > 0.15 * vmax):
                out.append(('FAIL', f'camera {r.kind} starts or stops abruptly (v0 {v0:.0f}, v1 {v1:.0f}, vmax {vmax:.0f} units/s)'))
    if not out: out.append(('PASS', 'one move, 35-50 mm, eased in and out, no overshoot'))
    return out


def check_readable(cards, cam, max_tilt=20.0):
    """FAIL for every text card tilted more than max_tilt from the camera at the moment it must be read."""
    out = []
    for c in cards:
        if not c.is_text or c.alpha < 0.5: continue
        a = tilt_deg(c, cam)
        out.append(('PASS' if a <= max_tilt else 'FAIL', f'{c.name or "text"} tilt {a:.1f} deg (max {max_tilt:.0f})'))
    return out


# ------------------------------------------------------------------ CLI: bench / demo
def _bench_scene(n=30, seed=4):
    kinds = ['video', 'image', 'audio', 'folder']
    tex = [M.media_card(kinds[i % 4], i * 7 + 3) for i in range(8)]
    pts = scatter(n, seed)
    return [Card(tex[i % 8], (240, 150), p['pos'], p['rot'], name=f'c{i}') for i, p in enumerate(pts)]


def bench_frame(cards, t, rig):
    cam = rig.at(t); R = Renderer(cam, dof=dict(focus=cam.pos[2], max_px=7, bands=5, aperture=1.0),
                                    fog=dict(near=1600, far=5200, max=0.7, color=(8, 9, 12)),
                                    light=dict(pos=(-900, 700, 2600), color=M.GOLD, ambient=0.75, key=0.3, rim=0.7),
                                    shadow=dict(ground_y=-760, strength=0.4, blur=10))
    base = M.canvas()
    R.render(base, cards, floor=dict(ground_y=-760))
    return M.finish(M.to_output(base), int(t * 30))


if __name__ == '__main__':
    a = sys.argv[1:]
    cmd = a[0] if a else 'bench'
    opt = {k: v for k, v in zip(a[1::2], a[2::2])} if cmd == 'bench' else {}
    if cmd == 'bench':
        M.configure(S=int(opt.get('--S', 2)))
        n = int(opt.get('--cards', 30)); nf = int(opt.get('--frames', 6))
        cards = _bench_scene(n)
        rig = CameraRig('dolly', 0, 2, **{'from': (0, 0, 4200), 'to': (0, 0, 2000)})
        bench_frame(cards, 0.0, rig)     # warm caches (background, grain)
        ts = []
        for k in range(nf):
            t0 = time.perf_counter(); bench_frame(cards, k * 2.0 / max(1, nf - 1), rig); ts.append(time.perf_counter() - t0)
        print(f'mg3d bench: {n} cards, 1920x1080, S={M.Cfg.S}, single process: mean {np.mean(ts):.3f} s/frame, max {np.max(ts):.3f} s')
    elif cmd == 'demo':
        cards = _bench_scene(30); rig = CameraRig('dolly', 0, 2, **{'from': (0, 0, 4200), 'to': (0, 0, 2000)})
        Image.fromarray(bench_frame(cards, 1.0, rig)).save(a[1] if len(a) > 1 else 'mg3d_demo.png')
    else:
        print(__doc__)
