"""
mglib - minimal kinetic motion-graphics toolkit (Pillow + NumPy).

Design rules:
  * Every frame is a pure function of time t -> image. No state carried between frames,
    so frames can be rendered in any order, in parallel, and re-rendered individually.
  * Draw at supersample scale S (default 2x), then downsample with LANCZOS for anti-aliasing.
  * All layout coordinates are written in OUTPUT pixels (e.g. 1920x1080). Use P() to convert.
  * Animation = easing(prog(t, start, end)). Never move things linearly.
"""
import math, os, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------- config
class Cfg:
    W, H = 1920, 1080          # output size
    S = 2                      # supersample factor (2 = draw at 4K for a 1080p output)
    FPS = 30
    FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts')
    FONT_FILES = {'Black': 'Montserrat-Black.ttf', 'Bold': 'Montserrat-Bold.ttf', 'Medium': 'Montserrat-Medium.ttf'}

def configure(**kw):
    for k, v in kw.items(): setattr(Cfg, k, v)
    _fc.clear(); _bg_cache.clear()

def CW(): return Cfg.W * Cfg.S
def CH(): return Cfg.H * Cfg.S
def P(v): return int(round(v * Cfg.S))

# palette (premium dark / gold)
GOLD = (255, 194, 40); GOLD_L = (255, 224, 130); WHITE = (244, 245, 247); GREY = (150, 154, 162)
def rgba(c, a): return (c[0], c[1], c[2], int(max(0, min(1, a)) * 255))

# ---------------------------------------------------------------- timing / easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a))          # 0..1 progress of t inside [a,b]
def lerp(a, b, x): return a + (b - a) * x
def ease_out_expo(x): return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)   # snappy arrival: THE premium curve
def ease_in_expo(x): return 0.0 if x <= 0 else 2 ** (10 * x - 10)     # accelerating exit
def ease_in_out_cubic(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def ease_out_back(x, s=1.6):                                          # overshoot pop (logos, checkmarks)
    x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
eo, ei, eio, eback = ease_out_expo, ease_in_expo, ease_in_out_cubic, ease_out_back

# ---------------------------------------------------------------- fonts
_fc = {}
def font(weight, size):
    k = (weight, size, Cfg.S)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(os.path.join(Cfg.FONT_DIR, Cfg.FONT_FILES[weight]), int(size * Cfg.S))
    return _fc[k]

# ---------------------------------------------------------------- background
_bg_cache = {}
def radial_bg(inner=(22, 23, 27), outer=(6, 7, 9), cy=0.46, power=1.6):
    """float32 HxWx3 radial gradient at output res (cached)."""
    k = (inner, outer, cy, power, Cfg.W, Cfg.H)
    if k in _bg_cache: return _bg_cache[k]
    yy, xx = np.mgrid[0:Cfg.H, 0:Cfg.W].astype(np.float32)
    d = np.sqrt(((xx - Cfg.W / 2) / (Cfg.W * .62)) ** 2 + ((yy - Cfg.H * cy) / (Cfg.H * .62)) ** 2)
    g = np.clip(1 - d, 0, 1) ** power
    o = np.array(outer, np.float32); i = np.array(inner, np.float32)
    _bg_cache[k] = o + g[..., None] * (i - o)
    return _bg_cache[k]

def canvas(bg=None):
    """Supersampled RGBA canvas initialised with a background array."""
    bg = radial_bg() if bg is None else bg
    return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).resize((CW(), CH()), Image.BILINEAR).convert('RGBA')

def grid(offx=0, offy=0, alpha=0.04, step=80):
    """Faint UI grid that can drift (parallax / 'tech' texture)."""
    lay = Image.new('RGBA', (CW(), CH()), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    c = (255, 255, 255, int(255 * alpha)); st = step * Cfg.S
    ox, oy = int(offx * Cfg.S) % st, int(offy * Cfg.S) % st
    for x in range(ox - st, CW() + st, st): d.line([(x, 0), (x, CH())], fill=c, width=Cfg.S)
    for y in range(oy - st, CH() + st, st): d.line([(0, y), (CW(), y)], fill=c, width=Cfg.S)
    return lay

# ---------------------------------------------------------------- compositing
def comp(base, layer, x, y):
    """alpha_composite with clipping (PIL refuses negative / out-of-bounds dest)."""
    x, y = int(round(x)), int(round(y)); lw, lh = layer.size
    if x >= base.width or y >= base.height or x + lw <= 0 or y + lh <= 0: return
    cx0, cy0 = max(0, -x), max(0, -y); cx1, cy1 = min(lw, base.width - x), min(lh, base.height - y)
    if cx0 or cy0 or cx1 < lw or cy1 < lh:
        layer = layer.crop((cx0, cy0, cx1, cy1)); x += cx0; y += cy0
    base.alpha_composite(layer, (x, y))

def comp_center(base, layer, cx, cy):
    """cx, cy in output px."""
    comp(base, layer, cx * Cfg.S - layer.width / 2, cy * Cfg.S - layer.height / 2)

def set_alpha(layer, a):
    if a >= 0.999: return layer
    arr = np.asarray(layer).copy(); arr[..., 3] = (arr[..., 3] * clamp(a)).astype(np.uint8)
    return Image.fromarray(arr)

def scale_layer(layer, sc):
    if abs(sc - 1) < 1e-3: return layer
    return layer.resize((max(1, int(layer.width * sc)), max(1, int(layer.height * sc))), Image.BICUBIC)

def glow(layer, radius=18, strength=1.0, color=None):
    """Bloom: blur a 1/4-res copy (fast), optionally recoloured. Composite UNDER the source."""
    w, h = layer.size
    sm = layer.resize((max(1, w // 4), max(1, h // 4)), Image.BILINEAR)
    if color is not None:
        a = sm.split()[3]; sm = Image.new('RGBA', sm.size, color + (0,)); sm.putalpha(a)
    sm = sm.filter(ImageFilter.GaussianBlur(radius * Cfg.S / 4)).resize((w, h), Image.BILINEAR)
    return set_alpha(sm, strength) if strength < 1 else _boost(sm, strength)

def _boost(img, k):
    if abs(k - 1) < 1e-3: return img
    arr = np.asarray(img).copy(); arr[..., 3] = np.clip(arr[..., 3] * k, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)

def soft_scrim(w, h, alpha=0.75, color=(4, 5, 7)):
    """Blurred dark ellipse placed behind text so it reads over busy visuals.
    The ellipse is inset so the blur never hits the layer edge (avoids visible boxes)."""
    lay = Image.new('RGBA', (P(w), P(h)), (0, 0, 0, 0))
    ImageDraw.Draw(lay).ellipse([lay.width * .18, lay.height * .2, lay.width * .82, lay.height * .8], fill=color + (int(255 * alpha),))
    return lay.resize((lay.width // 8, lay.height // 8)).filter(ImageFilter.GaussianBlur(14)).resize(lay.size, Image.BILINEAR)

def shadow_for(im, strength=0.6):
    a = im.split()[3].resize((im.width // 4 + 1, im.height // 4 + 1)).filter(ImageFilter.GaussianBlur(6))
    sh = Image.new('RGBA', a.size, (0, 0, 0, 0)); sh.putalpha(a.point(lambda v: int(v * strength)))
    return sh.resize((im.width + P(30), im.height + P(30)), Image.BILINEAR)

# ---------------------------------------------------------------- kinetic typography
class Text:
    """Rendered text line. per_char(i) -> (dx, dy, alpha) in output px gives per-letter animation.
    .anchor is the y (in layer px) of the cap-height centre, so lines align optically."""
    def __init__(self, s, weight='Black', size=150, color=WHITE, tracking=0.0, per_char=None, colors=None, pad=100):
        f = font(weight, size); asc, desc = f.getmetrics(); tr = tracking * Cfg.S
        adv = [f.getlength(c) for c in s]
        self.width_px = sum(adv) + tr * (len(s) - 1)
        self.pad = P(pad)
        img = Image.new('RGBA', (int(self.width_px) + 2 * self.pad, asc + desc + 2 * self.pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img); x = self.pad
        for i, c in enumerate(s):
            dx, dy, a = per_char(i) if per_char else (0, 0, 1.0)
            if a > 0.003:
                d.text((x + dx * Cfg.S, self.pad + dy * Cfg.S), c, font=f, fill=rgba(colors[i] if colors else color, a))
            x += adv[i] + tr
        bb = f.getbbox('H')
        self.cap_top, self.cap_bot = self.pad + bb[1], self.pad + bb[3]
        self.anchor = (self.cap_top + self.cap_bot) / 2
        self.img = img

    def mask(self, extra=14):
        """Clip to the cap band (+extra px): letters sliding in from below appear to rise out of a slot."""
        arr = np.asarray(self.img).copy(); t, b = int(self.cap_top - P(extra)), int(self.cap_bot + P(extra))
        arr[:max(0, t), :, 3] = 0; arr[b:, :, 3] = 0
        self.img = Image.fromarray(arr); return self

    def shine(self, phase, color=(255, 226, 140), width=0.06, slant=0.35):
        """Diagonal light sweep clipped to the glyphs. phase 0..1."""
        if not 0 < phase < 1: return self
        a = np.asarray(self.img.split()[3], np.float32) / 255; h, w = a.shape
        X = np.arange(w)[None, :] + np.arange(h)[:, None] * slant
        band = np.exp(-((X - lerp(-0.2, 1.3, phase) * w) / (w * width)) ** 2)
        sh = np.zeros((h, w, 4), np.uint8); sh[..., :3] = color; sh[..., 3] = (a * band * 255).astype(np.uint8)
        self.img = self.img.copy(); self.img.alpha_composite(Image.fromarray(sh)); return self

    def draw(self, base, cx, cy, scale=1.0, alpha=1.0, glow_color=GOLD, glow_strength=0.3, glow_radius=24, rgb_split_px=0):
        lay = self.img
        g = glow(lay, glow_radius, glow_strength, glow_color) if glow_strength > 0 else None
        if rgb_split_px: lay = rgb_split(lay, rgb_split_px)
        lay = set_alpha(scale_layer(lay, scale), alpha)
        x = cx * Cfg.S - lay.width / 2; y = cy * Cfg.S - self.anchor * scale
        if g is not None:
            g = set_alpha(scale_layer(g, scale), alpha)
            comp(base, g, cx * Cfg.S - g.width / 2, y)
        comp(base, lay, x, y)

def rgb_split(layer, amt):
    """Chromatic-aberration glitch: red and cyan ghosts offset horizontally."""
    if amt < 0.5: return layer
    a = layer.split()[3]; o = P(amt)
    out = Image.new('RGBA', (layer.width + 2 * o, layer.height), (0, 0, 0, 0))
    for col, dx in (((255, 40, 60), 0), ((40, 220, 255), 2 * o)):
        g = Image.new('RGBA', layer.size, col + (0,)); g.putalpha(a.point(lambda v: v * 0.7)); out.alpha_composite(g, (dx, 0))
    out.alpha_composite(layer, (o, 0))
    # keep original width so centring is unchanged
    return out.crop((o, 0, o + layer.width, layer.height))

def stagger_rise(t, start, step=0.035, dur=0.5, dist=150, order=None):
    """per_char factory: letters rise from below with a stagger (use with Text(...).mask())."""
    def pc(i):
        k = order(i) if order else i
        e = eo(prog(t, start + k * step, start + k * step + dur))
        return (0, (1 - e) * dist, clamp(e * 2))
    return pc

def rule(base, cx, y, width, color=GOLD, thickness=3, glow_strength=1.2):
    """Gold line that grows from centre."""
    if width < 1: return
    rl = Image.new('RGBA', (P(width) + 1, P(thickness)), color + (255,))
    comp(base, glow(rl, 10, glow_strength, color), cx * Cfg.S - rl.width / 2, P(y))
    comp(base, rl, cx * Cfg.S - rl.width / 2, P(y))

# ---------------------------------------------------------------- abstract media cards
_PAL = [((38, 56, 84), (12, 18, 30)), ((92, 58, 36), (24, 14, 10)), ((30, 78, 80), (8, 20, 22)),
        ((68, 48, 96), (16, 12, 26)), ((96, 82, 40), (24, 20, 8)), ((60, 66, 74), (16, 17, 20))]

def media_card(kind='video', seed=0, w=300, h=188):
    """Pre-render once, reuse every frame (rotate/scale per frame). kind: video|image|audio|folder."""
    r = random.Random(seed); k = 3; u = Cfg.S * k
    if kind == 'audio': h = 120
    if kind == 'folder': w, h = 250, 190
    WW, HH = w * u, h * u
    img = Image.new('RGBA', (WW, HH), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    c1, c2 = _PAL[r.randrange(len(_PAL))]
    if kind == 'folder':
        d.rounded_rectangle([0, 0, 100 * u, 40 * u], radius=10 * u, fill=(34, 36, 42, 255))
        d.rounded_rectangle([0, 34 * u, WW - 1, HH - 1], radius=14 * u, fill=(44, 47, 54, 255), outline=(78, 82, 90, 255), width=2 * u)
        d.ellipse([WW - 44 * u, HH - 46 * u, WW - 26 * u, HH - 28 * u], fill=GOLD + (255,))
    else:
        d.rounded_rectangle([0, 0, WW - 1, HH - 1], radius=14 * u, fill=(24, 26, 31, 255), outline=(66, 70, 78, 255), width=2 * u)
        ins = 8 * u
        if kind == 'audio':
            n = 34; bw = (WW - 2 * ins - 20 * u) / n
            for i in range(n):
                bh = (0.25 + 0.75 * abs(math.sin(i * 0.55 + seed)) * r.uniform(.5, 1)) * (HH - 2 * ins - 16 * u)
                x0 = ins + 10 * u + i * bw
                d.rounded_rectangle([x0, HH / 2 - bh / 2, x0 + bw * .55, HH / 2 + bh / 2], radius=int(bw * .27),
                                    fill=GOLD + (255,) if i < n * .4 else (170, 174, 182, 255))
        else:
            tw, th = WW - 2 * ins, HH - 2 * ins - (26 * u if kind == 'video' else 0)
            t_ = np.linspace(0, 1, th, dtype=np.float32)[:, None, None]
            arr = np.array(c1, np.float32) + t_ * (np.array(c2, np.float32) - np.array(c1, np.float32))
            g = Image.fromarray(np.repeat(arr, tw, axis=1).astype(np.uint8)).convert('RGBA'); gd = ImageDraw.Draw(g)
            hz = th * r.uniform(.55, .75)
            gd.polygon([(0, th)] + [(x, hz - r.uniform(0, th * .35)) for x in np.linspace(0, tw, 6)] + [(tw, th)],
                       fill=tuple(int(v * .6) for v in c2) + (255,))
            m = Image.new('L', (tw, th), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, tw - 1, th - 1], radius=8 * u, fill=255)
            img.paste(g, (ins, ins), m)
            if kind == 'video':
                cx, cy, s = ins + tw / 2, ins + th / 2, 22 * u
                d.ellipse([cx - s * 1.5, cy - s * 1.5, cx + s * 1.5, cy + s * 1.5], fill=(0, 0, 0, 110))
                d.polygon([(cx - s * .5, cy - s * .75), (cx - s * .5, cy + s * .75), (cx + s * .85, cy)], fill=(255, 255, 255, 230))
                by = HH - 18 * u; pw = r.uniform(.2, .8)
                d.rounded_rectangle([ins + 4 * u, by - 3 * u, WW - ins - 4 * u, by + 3 * u], radius=3 * u, fill=(60, 64, 72, 255))
                d.rounded_rectangle([ins + 4 * u, by - 3 * u, ins + 4 * u + (WW - 2 * ins - 8 * u) * pw, by + 3 * u], radius=3 * u, fill=GOLD + (255,))
    return img.resize((w * Cfg.S, h * Cfg.S), Image.LANCZOS)

def transform_card(tex, scale, rot_deg, alpha=1.0):
    im = scale_layer(tex, scale)
    if abs(rot_deg) > .2: im = im.rotate(rot_deg, resample=Image.BICUBIC, expand=True)
    return set_alpha(im, alpha)

# ---------------------------------------------------------------- post (output res, numpy float32 HxWx3)
def to_output(img):
    return np.asarray(img.convert('RGB').resize((Cfg.W, Cfg.H), Image.LANCZOS), np.float32)

def zoom(arr, sc):
    if abs(sc - 1) < 1e-3: return arr
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)); w, h = int(Cfg.W * sc), int(Cfg.H * sc)
    im = im.resize((w, h), Image.BICUBIC)
    if sc > 1:
        l, t = (w - Cfg.W) // 2, (h - Cfg.H) // 2; return np.asarray(im.crop((l, t, l + Cfg.W, t + Cfg.H)), np.float32)
    out = Image.new('RGB', (Cfg.W, Cfg.H)); out.paste(im, ((Cfg.W - w) // 2, (Cfg.H - h) // 2)); return np.asarray(out, np.float32)

def shift(arr, dx, fill=None):
    dx = int(dx); fill = radial_bg() if fill is None else fill
    if dx == 0: return arr
    out = fill.copy()
    if dx > 0: out[:, dx:] = arr[:, :Cfg.W - dx]
    else: out[:, :Cfg.W + dx] = arr[:, -dx:]
    return out

def hblur(arr, px):
    """Cheap horizontal motion blur for whip pans."""
    px = int(px)
    if px < 2: return arr
    acc = np.zeros_like(arr); n = 0
    for k in range(-px, px + 1, max(1, px // 6)): acc += np.roll(arr, k, axis=1); n += 1
    return acc / n

def flash(arr, amount, color=(255, 236, 190)):
    if amount <= 0: return arr
    return arr + (np.array(color, np.float32) - arr) * amount

_vig = {}; _grain = {}
def finish(arr, frame_index, vignette=0.55, grain=3.2):
    """Vignette + film grain: removes the flat 'digital' look and hides banding in dark gradients."""
    k = (Cfg.W, Cfg.H)
    if k not in _vig:
        yy, xx = np.mgrid[0:Cfg.H, 0:Cfg.W].astype(np.float32)
        _vig[k] = np.clip(1 - vignette * (((xx - Cfg.W / 2) / (Cfg.W * .7)) ** 2 + ((yy - Cfg.H / 2) / (Cfg.H * .75)) ** 2), .35, 1)[..., None]
        rng = np.random.default_rng(7); _grain[k] = [rng.normal(0, 1, (Cfg.H, Cfg.W, 1)).astype(np.float32) for _ in range(6)]
    arr = arr * _vig[k] + _grain[k][frame_index % 6] * grain
    return np.clip(arr, 0, 255).astype(np.uint8)

# transitions: return output-res arrays
def whip_out(render_fn, t, t0, t1, dist=1400, blur=90):
    k = ei(prog(t, t0, t1)); return hblur(shift(to_output(render_fn(t)), -k * dist), k * blur)
def whip_in(render_fn, t, t0, t1, dist=1400, blur=90):
    k = 1 - eo(prog(t, t0, t1)); return hblur(shift(to_output(render_fn(t)), k * dist), k * blur)
def zoom_through_out(render_fn, t, t0, t1, amount=0.35):
    k = ei(prog(t, t0, t1)); return zoom(to_output(render_fn(t)), 1 + amount * k) * (1 - 0.7 * k)
def zoom_in(render_fn, t, t0, t1, start=1.18):
    return zoom(to_output(render_fn(t)), lerp(start, 1.0, eo(prog(t, t0, t1))))

# ---------------------------------------------------------------- render driver
def render_all(frame_fn, n_frames, out_dir='frames', workers=None, start=0, end=None):
    """frame_fn(i) -> uint8 HxWx3. Renders PNGs in parallel; skips frames that already exist (resumable)."""
    from multiprocessing import Pool
    os.makedirs(out_dir, exist_ok=True)
    end = n_frames if end is None else end
    global _FRAME_FN, _OUT
    _FRAME_FN, _OUT = frame_fn, out_dir
    with Pool(workers or os.cpu_count()) as pool:
        pool.map(_work, range(start, end), chunksize=4)

_FRAME_FN = None; _OUT = 'frames'
def _work(i):
    p = os.path.join(_OUT, f'f{i:04d}.png')
    if not os.path.exists(p): Image.fromarray(_FRAME_FN(i)).save(p, compress_level=1)
