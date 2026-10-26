import numpy as np, math, random, sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 2
W, H = 1920, 1080
CW, CH = W * S, H * S
FPS = 30
N = 300
GOLD = (255, 194, 40)
GOLD_L = (255, 224, 130)
WHITE = (244, 245, 247)
GREY = (150, 154, 162)
import pathlib
FD = str(pathlib.Path(__file__).resolve().parents[2] / 'fonts') + '/'
OUT = 'frames/'

_fc = {}
def font(w, size):
    k = (w, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FD + f'Montserrat-{w}.ttf', int(size * S))
    return _fc[k]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a))
def eo(x): return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)          # ease out expo
def ei(x): return 0.0 if x <= 0 else 2 ** (10 * x - 10)          # ease in expo
def eio(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def eback(x, s=1.6):
    x = x - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, x): return a + (b - a) * x
def P(v): return int(round(v * S))

def rgba(c, a): return (c[0], c[1], c[2], int(clamp(a) * 255))

# ---------------- backgrounds ----------------
def make_bg(tint=(0, 0, 0)):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x - W / 2) / (W * 0.62)) ** 2 + ((y - H * 0.46) / (H * 0.62)) ** 2)
    g = np.clip(1 - d, 0, 1) ** 1.6
    base = np.array([6, 7, 9], np.float32)
    top = np.array([22, 23, 27], np.float32) + np.array(tint, np.float32)
    img = base[None, None, :] + g[..., None] * (top - base)[None, None, :]
    return img

BG = make_bg()
BG_WARM = make_bg((10, 6, -4))
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = np.clip(1 - 0.55 * (((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.75)) ** 2), 0.35, 1)[..., None]
rng = np.random.default_rng(7)
GRAIN = [rng.normal(0, 1, (H, W, 1)).astype(np.float32) for _ in range(6)]

def grid_layer(offx, offy, alpha=0.05, step=80):
    lay = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = (255, 255, 255, int(255 * alpha))
    st = step * S
    ox = int(offx * S) % st
    oy = int(offy * S) % st
    for x in range(ox - st, CW + st, st):
        d.line([(x, 0), (x, CH)], fill=c, width=S)
    for y in range(oy - st, CH + st, st):
        d.line([(0, y), (CW, y)], fill=c, width=S)
    return lay

def canvas(bg=None):
    bg = BG if bg is None else bg
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).resize((CW, CH), Image.BILINEAR)
    return im.convert('RGBA')

# ---------------- glow / helpers ----------------
def glow(layer, radius=18, strength=1.0, color=None):
    w, h = layer.size
    sm = layer.resize((max(1, w // 4), max(1, h // 4)), Image.BILINEAR)
    if color is not None:
        a = sm.split()[3]
        sm = Image.new('RGBA', sm.size, color + (0,))
        sm.putalpha(a)
    sm = sm.filter(ImageFilter.GaussianBlur(radius * S / 4))
    g = sm.resize((w, h), Image.BILINEAR)
    if strength != 1.0:
        a = np.asarray(g.split()[3], np.float32) * strength
        g.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    return g

def set_alpha(layer, a):
    if a >= 0.999: return layer
    arr = np.asarray(layer).copy()
    arr[..., 3] = (arr[..., 3].astype(np.float32) * clamp(a)).astype(np.uint8)
    return Image.fromarray(arr)

def comp(base, layer, x, y):
    x, y = int(round(x)), int(round(y))
    # clip to base
    lw, lh = layer.size
    if x >= base.width or y >= base.height or x + lw <= 0 or y + lh <= 0: return
    cx0, cy0 = max(0, -x), max(0, -y)
    cx1, cy1 = min(lw, base.width - x), min(lh, base.height - y)
    if cx0 or cy0 or cx1 < lw or cy1 < lh:
        layer = layer.crop((cx0, cy0, cx1, cy1))
        x, y = x + cx0, y + cy0
    base.alpha_composite(layer, (x, y))

# ---------------- text ----------------
def text_layer(s, w, size, color, tracking=0.0, per_char=None, colors=None):
    f = font(w, size)
    asc, desc = f.getmetrics()
    tr = tracking * S
    adv = [f.getlength(c) for c in s]
    total = sum(adv) + tr * (len(s) - 1)
    pad = P(100)
    img = Image.new('RGBA', (int(total) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    bb = f.getbbox('H')
    for i, c in enumerate(s):
        dx, dy, a = 0, 0, 1.0
        if per_char: dx, dy, a = per_char(i)
        col = colors[i] if colors else color
        if a > 0.003:
            d.text((x + dx * S, pad + dy * S), c, font=f, fill=rgba(col, a))
        x += adv[i] + tr
    cap_top, cap_bot = pad + bb[1], pad + bb[3]
    return img, (cap_top + cap_bot) / 2, (cap_top, cap_bot), pad

def place_text(base, layer, cy_anchor, cx, cy):
    """cx, cy in 1x coords; layer centered horizontally, cap-center at cy"""
    comp(base, layer, cx * S - layer.width / 2, cy * S - cy_anchor)

def clip_rows(layer, top, bot):
    """keep only rows [top,bot) (mask reveal)"""
    arr = np.asarray(layer).copy()
    arr[:int(top), :, 3] = 0
    arr[int(bot):, :, 3] = 0
    return Image.fromarray(arr)

def scale_layer(layer, sc):
    if abs(sc - 1) < 1e-3: return layer
    return layer.resize((max(1, int(layer.width * sc)), max(1, int(layer.height * sc))), Image.BICUBIC)

def rgb_split(layer, amt):
    """glitchy chromatic offset; returns layer with red/cyan ghosts"""
    if amt < 0.5: return layer
    a = layer.split()[3]
    out = Image.new('RGBA', (layer.width + 2 * P(amt) + 2, layer.height), (0, 0, 0, 0))
    r = Image.new('RGBA', layer.size, (255, 40, 60, 0)); r.putalpha(a.point(lambda v: v * 0.7))
    c = Image.new('RGBA', layer.size, (40, 220, 255, 0)); c.putalpha(a.point(lambda v: v * 0.7))
    o = P(amt)
    out.alpha_composite(r, (0, 0))
    out.alpha_composite(c, (2 * o, 0))
    out.alpha_composite(layer, (o, 0))
    return out

# ---------------- media card textures ----------------
PAL = [((38, 56, 84), (12, 18, 30)), ((92, 58, 36), (24, 14, 10)), ((30, 78, 80), (8, 20, 22)),
       ((68, 48, 96), (16, 12, 26)), ((96, 82, 40), (24, 20, 8)), ((60, 66, 74), (16, 17, 20))]

def grad(w, h, c1, c2, vertical=False):
    t = np.linspace(0, 1, h if vertical else w, dtype=np.float32)
    c1 = np.array(c1, np.float32); c2 = np.array(c2, np.float32)
    col = c1[None, :] + t[:, None] * (c2 - c1)[None, :]
    if vertical: arr = np.repeat(col[:, None, :], w, axis=1)
    else: arr = np.repeat(col[None, :, :], h, axis=0)
    return Image.fromarray(arr.astype(np.uint8)).convert('RGBA')

def make_card(kind, seed):
    r = random.Random(seed)
    k = 3  # extra supersample for crisp edges
    w, h = (300, 188) if kind != 'audio' else (300, 120)
    if kind == 'folder': w, h = 250, 190
    WW, HH = w * S * k, h * S * k
    u = S * k
    img = Image.new('RGBA', (WW, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c1, c2 = PAL[r.randrange(len(PAL))]
    if kind == 'folder':
        d.rounded_rectangle([0, 18 * u, WW - 1, HH - 1], radius=14 * u, fill=(34, 36, 42, 255), outline=(70, 74, 82, 255), width=2 * u)
        d.rounded_rectangle([0, 0, 100 * u, 40 * u], radius=10 * u, fill=(34, 36, 42, 255))
        d.rounded_rectangle([0, 34 * u, WW - 1, HH - 1], radius=14 * u, fill=(44, 47, 54, 255), outline=(78, 82, 90, 255), width=2 * u)
        d.rounded_rectangle([22 * u, HH - 40 * u, 120 * u, HH - 30 * u], radius=5 * u, fill=(110, 114, 122, 255))
        d.ellipse([WW - 44 * u, HH - 46 * u, WW - 26 * u, HH - 28 * u], fill=GOLD + (255,))
    else:
        d.rounded_rectangle([0, 0, WW - 1, HH - 1], radius=14 * u, fill=(24, 26, 31, 255), outline=(66, 70, 78, 255), width=2 * u)
        ins = 8 * u
        if kind == 'audio':
            n = 34
            bw = (WW - 2 * ins - 20 * u) / n
            for i in range(n):
                amp = (0.25 + 0.75 * abs(math.sin(i * 0.55 + seed)) * r.uniform(0.5, 1.0))
                bh = amp * (HH - 2 * ins - 16 * u)
                x0 = ins + 10 * u + i * bw
                col = GOLD + (255,) if i < n * 0.4 else (170, 174, 182, 255)
                d.rounded_rectangle([x0, HH / 2 - bh / 2, x0 + bw * 0.55, HH / 2 + bh / 2], radius=int(bw * 0.27), fill=col)
        else:
            tw, th = WW - 2 * ins, HH - 2 * ins - (26 * u if kind == 'video' else 0)
            g = grad(tw, th, c1, c2, vertical=r.random() < 0.5)
            gd = ImageDraw.Draw(g)
            # abstract scene: horizon + shapes
            hz = th * r.uniform(0.55, 0.75)
            pts = [(0, th)] + [(x, hz - r.uniform(0, th * 0.35)) for x in np.linspace(0, tw, 6)] + [(tw, th)]
            gd.polygon(pts, fill=(int(c2[0] * 0.6), int(c2[1] * 0.6), int(c2[2] * 0.6), 255))
            if r.random() < 0.6:
                cx, cy, rr = tw * r.uniform(0.2, 0.8), th * r.uniform(0.2, 0.4), th * 0.12
                gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(min(255, c1[0] + 90), min(255, c1[1] + 80), min(255, c1[2] + 60), 255))
            m = Image.new('L', (tw, th), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, tw - 1, th - 1], radius=8 * u, fill=255)
            img.paste(g, (ins, ins), m)
            if kind == 'video':
                cx, cy, s = ins + tw / 2, ins + th / 2, 22 * u
                d.ellipse([cx - s * 1.5, cy - s * 1.5, cx + s * 1.5, cy + s * 1.5], fill=(0, 0, 0, 110))
                d.polygon([(cx - s * 0.5, cy - s * 0.75), (cx - s * 0.5, cy + s * 0.75), (cx + s * 0.85, cy)], fill=(255, 255, 255, 230))
                by = HH - 18 * u
                d.rounded_rectangle([ins + 4 * u, by - 3 * u, WW - ins - 4 * u, by + 3 * u], radius=3 * u, fill=(60, 64, 72, 255))
                pw = r.uniform(0.2, 0.8)
                d.rounded_rectangle([ins + 4 * u, by - 3 * u, ins + 4 * u + (WW - 2 * ins - 8 * u) * pw, by + 3 * u], radius=3 * u, fill=GOLD + (255,))
    return img.resize((w * S, h * S), Image.LANCZOS)

KINDS = ['video', 'image', 'video', 'folder', 'audio', 'image', 'video', 'image', 'folder', 'audio', 'video', 'image']
TEX = [make_card(KINDS[i], i * 13 + 5) for i in range(len(KINDS))]
TEX_BLUR = [t.filter(ImageFilter.GaussianBlur(3 * S)) for t in TEX]

# chaos cards
R = random.Random(42)
CARDS = []
NC = 32
for i in range(NC):
    ang = R.uniform(0, 2 * math.pi)
    rad = R.uniform(0.25, 1.0)
    z = R.uniform(0.45, 1.35)
    CARDS.append(dict(
        tex=i % len(TEX),
        tx=960 + math.cos(ang) * rad * 1050 * (0.8 + 0.4 * z), ty=540 + math.sin(ang) * rad * 620 * (0.8 + 0.4 * z),
        vx=R.uniform(-60, 60) + math.cos(ang) * 40, vy=R.uniform(-40, 40) + math.sin(ang) * 30,
        r0=R.uniform(-45, 45), rs=R.uniform(-40, 40), z=z, delay=R.uniform(0, 0.25),
        gi=i))
# organized grid 8x4
GC, GR = 8, 4
GW, GH = 176, 110
GSX, GSY = 200, 132
for i, c in enumerate(CARDS):
    col, row = i % GC, i // GC
    c['gx'] = 960 - (GC - 1) * GSX / 2 + col * GSX
    c['gy'] = 540 - (GR - 1) * GSY / 2 + row * GSY
ORDER = sorted(range(NC), key=lambda i: CARDS[i]['z'])

def card_img(tex_i, sc, rot, blur=False, alpha=1.0, gold_edge=0.0):
    base = TEX_BLUR[tex_i] if blur else TEX[tex_i]
    im = scale_layer(base, sc)
    if gold_edge > 0.01:
        im = im.copy()
        dd = ImageDraw.Draw(im)
        dd.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(14 * S * sc), outline=rgba(GOLD, gold_edge), width=max(1, int(2.5 * S)))
    if abs(rot) > 0.2:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999: im = set_alpha(im, alpha)
    return im

def shadow_for(im, strength=0.6):
    a = im.split()[3].resize((im.width // 4 + 1, im.height // 4 + 1)).filter(ImageFilter.GaussianBlur(6))
    sh = Image.new('RGBA', a.size, (0, 0, 0, 0)); sh.putalpha(a.point(lambda v: int(v * strength)))
    return sh.resize((im.width + P(30), im.height + P(30)), Image.BILINEAR)

# ---------------- scene 1+2: chaos -> organized ----------------
def scene_12(t):
    base = canvas()
    shake = 0
    if t < 2.0:
        shake = (1 - prog(t, 0, 2.0)) * 0 + 4 * (0.4 + 0.6 * prog(t, 1.0, 2.0))
    sx = math.sin(t * 47) * shake + math.sin(t * 23) * shake * 0.6
    sy = math.cos(t * 39) * shake * 0.7
    base.alpha_composite(grid_layer(-t * 30 + sx, -t * 18 + sy, alpha=0.035 + 0.02 * prog(t, 2.0, 2.4)))

    snap = eo(prog(t, 2.0, 2.55))
    dim = lerp(1.0, 0.32, eio(prog(t, 2.35, 2.9)))
    for i in ORDER:
        c = CARDS[i]
        b = eo(prog(t, c['delay'], c['delay'] + 1.0))
        cx = lerp(960, c['tx'], b) + c['vx'] * t + sx * c['z']
        cy = lerp(540, c['ty'], b) + c['vy'] * t + sy * c['z']
        rot = c['r0'] * b + c['rs'] * t
        sc = c['z'] * 0.62 * (0.25 + 0.75 * b)
        # accelerate outward just before the cut
        acc = ei(prog(t, 1.75, 2.0))
        cx += (cx - 960) * 0.25 * acc; cy += (cy - 540) * 0.25 * acc
        # organized
        tw = TEX[c['tex']].width / S
        gsc = GW / tw
        cx = lerp(cx, c['gx'], snap); cy = lerp(cy, c['gy'], snap)
        rot = lerp(rot, 0, snap); sc = lerp(sc, gsc, snap)
        blur = (c['z'] < 0.7) and snap < 0.5
        a = lerp(lerp(0.55, 1.0, prog(c['z'], 0.45, 1.0)) * clamp(b * 3), 1.0, snap) * dim
        wave = 0.0
        if t > 2.5:
            ph = prog(t, 2.55 + (c['gx'] - 260) / 1400 * 0.6, 2.85 + (c['gx'] - 260) / 1400 * 0.6)
            wave = math.sin(ph * math.pi) * 0.9
        im = card_img(c['tex'], sc, rot, blur, a, wave / max(dim, 0.3))
        if snap < 0.95 and not blur:
            sh = shadow_for(im, 0.5 * a)
            comp(base, sh, cx * S - sh.width / 2 + P(10), cy * S - sh.height / 2 + P(16))
        comp(base, im, cx * S - im.width / 2, cy * S - im.height / 2)

    # scrim behind text
    sc_a = 0.75 if t < 2.0 else 0.6
    scrim = Image.new('RGBA', (P(2000), P(800)), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).ellipse([scrim.width*0.18, scrim.height*0.2, scrim.width*0.82, scrim.height*0.8], fill=(4, 5, 7, int(255 * sc_a)))
    scrim = scrim.resize((scrim.width // 8, scrim.height // 8)).filter(ImageFilter.GaussianBlur(14)).resize(scrim.size, Image.BILINEAR)
    comp(base, scrim, CW / 2 - scrim.width / 2, CH / 2 - scrim.height / 2)

    # ---- text: MEDIA CHAOS? ----
    if 0.25 <= t < 2.0:
        e = eo(prog(t, 0.3, 0.75))
        out = ei(prog(t, 1.82, 2.0))
        cols = [WHITE] * 11 + [GOLD]
        rr = random.Random(int(t * 30))
        def pc(i):
            jitter = 0
            if prog(t, 0.3, 0.6) < 1 or (1.2 < t < 1.3) or (1.62 < t < 1.68):
                jitter = rr.uniform(-6, 6)
            return (jitter, rr.uniform(-3, 3) if jitter else 0, 1.0)
        lay, anc, _, _ = text_layer('MEDIA CHAOS?', 'Black', 150, WHITE, tracking=lerp(40, 4, e), per_char=pc, colors=cols)
        sc = lerp(1.55, 1.0, e) * lerp(1, 1.12, out)
        amt = 0
        if t < 0.62: amt = 14 * (1 - prog(t, 0.3, 0.62))
        if 1.2 < t < 1.3 or 1.62 < t < 1.68: amt = 9
        if out > 0: amt = 18 * out
        g = glow(lay, 22, 0.35, GOLD)
        lay = rgb_split(lay, amt)
        lay = set_alpha(scale_layer(lay, sc), clamp(e * 1.5) * (1 - out))
        g = set_alpha(scale_layer(g, sc), clamp(e) * (1 - out))
        place_text(base, g, anc * sc, 960, 540)
        comp(base, lay, CW / 2 - lay.width / 2, 540 * S - anc * sc)

    # ---- text: MEET RENDER DOCK ----
    if t >= 2.05:
        ox = 0
        e1 = eo(prog(t, 2.1, 2.55))
        lay, anc, (ct, cb), _ = text_layer('MEET', 'Bold', 44, GOLD, tracking=lerp(60, 22, e1))
        lay = clip_rows(lay, ct - P(4), cb + P(4))
        # slide up within mask
        shift = (1 - e1) * (cb - ct + P(10))
        tmp = Image.new('RGBA', lay.size, (0, 0, 0, 0)); tmp.alpha_composite(lay, (0, int(shift)))
        tmp = clip_rows(tmp, ct - P(4), cb + P(4))
        place_text(base, tmp, anc, 960, 440)

        def pc(i):
            st = 2.22 + i * 0.035
            e = eo(prog(t, st, st + 0.5))
            return (0, (1 - e) * 150, clamp(e * 2))
        lay, anc, (ct, cb), _ = text_layer('RENDER DOCK', 'Black', 170, WHITE, tracking=8, per_char=pc,
                                           colors=[WHITE] * 7 + [GOLD] * 4)
        lay = clip_rows(lay, ct - P(14), cb + P(14))
        g = glow(lay, 26, 0.3, GOLD)
        place_text(base, g, anc, 960, 560)
        place_text(base, lay, anc, 960, 560)
        # gold rule
        lw = eo(prog(t, 2.5, 3.1)) * 620
        if lw > 1:
            rl = Image.new('RGBA', (P(lw) + 1, P(3)), GOLD + (255,))
            comp(base, glow(rl, 10, 1.2, GOLD), CW / 2 - rl.width / 2, P(680))
            comp(base, rl, CW / 2 - rl.width / 2, P(680))
    return base

# ---------------- scene 3: drag / organize / render ----------------
PX0, PY0, PX1, PY1 = 250, 400, 1670, 1000
BIN_X, BIN_Y = 290, 480
TW_, TH_ = 182, 114
GAP = 16
Q_X, Q_Y, Q_W, Q_RH = 930, 480, 700, 112
BIN_TEX = [0, 1, 2, 5, 6, 7, 10, 11, 3]
# reflow permutation (slots)
PERM_START = list(range(9))
PERM_END = [0, 2, 1, 5, 4, 3, 7, 8, 6]

def slot_xy(s):
    col, row = s % 3, s // 3
    return BIN_X + col * (TW_ + GAP) + TW_ / 2, BIN_Y + row * (TH_ + GAP) + TH_ / 2

def draw_cursor(base, x, y, pressed):
    k = 1.0 if not pressed else 0.88
    pts = [(0, 0), (0, 34), (9, 26), (15, 40), (21, 37), (15, 24), (27, 24)]
    lay = Image.new('RGBA', (P(60), P(60)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    pp = [(P(6 + px * k), P(6 + py * k)) for px, py in pts]
    d.polygon(pp, fill=(255, 255, 255, 255), outline=(10, 10, 12, 255), width=P(2))
    sh = shadow_for(lay, 0.7)
    comp(base, sh, x * S - P(4), y * S)
    comp(base, lay, x * S - P(6), y * S - P(6))

def rr(d, box, r, **kw):
    d.rounded_rectangle([P(box[0]), P(box[1]), P(box[2]), P(box[3])], radius=P(r), **kw)

def scene_3(t):
    u = t - 4.0
    base = canvas()
    base.alpha_composite(grid_layer(-t * 30, -t * 18, alpha=0.05))
    pe = eo(prog(u, 0.0, 0.55))
    oy = (1 - pe) * 120
    panel = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    rr(d, (PX0, PY0 + oy, PX1, PY1 + oy), 22, fill=(14, 15, 19, 240), outline=(50, 53, 60, 255), width=P(1.5))
    rr(d, (PX0, PY0 + oy, PX1, PY0 + 52 + oy), 22, fill=(20, 21, 26, 255))
    d.rectangle([P(PX0), P(PY0 + 30 + oy), P(PX1), P(PY0 + 52 + oy)], fill=(20, 21, 26, 255))
    for i, cc in enumerate([(70, 72, 78), (70, 72, 78), GOLD]):
        x = PX0 + 30 + i * 22
        d.ellipse([P(x - 6), P(PY0 + 26 - 6 + oy), P(x + 6), P(PY0 + 26 + 6 + oy)], fill=cc + (255,))
    d.line([(P(PX0), P(PY0 + 52 + oy)), (P(PX1), P(PY0 + 52 + oy))], fill=(44, 47, 54, 255), width=P(1.5))
    # divider
    d.line([(P(Q_X - 22), P(PY0 + 70 + oy)), (P(Q_X - 22), P(PY1 - 24 + oy))], fill=(40, 43, 50, 255), width=P(1.5))
    # title bars (abstract)
    rr(d, (BIN_X, PY0 + 18 + oy, BIN_X + 120, PY0 + 34 + oy), 6, fill=(46, 49, 56, 255))
    rr(d, (Q_X, PY0 + 18 + oy, Q_X + 160, PY0 + 34 + oy), 6, fill=(46, 49, 56, 255))
    panel = set_alpha(panel, pe)
    base.alpha_composite(panel)

    # queue rows
    drag_s, drag_e = 0.45, 1.05
    rows = []
    row_times = [drag_e, 1.18, 1.32, 1.46]
    for ri in range(4):
        st = row_times[ri]
        if u < st: continue
        e = eo(prog(u, st, st + 0.4))
        y = Q_Y + ri * (Q_RH + 10)
        x = Q_X + (1 - e) * (0 if ri == 0 else 220)
        lay = Image.new('RGBA', (P(Q_W) + 2, P(Q_RH) + 2), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        hl = 1 - prog(u, st, st + 0.6) if ri == 0 else 0
        dd.rounded_rectangle([0, 0, P(Q_W), P(Q_RH)], radius=P(14), fill=(22, 24, 29, 255),
                             outline=rgba(GOLD, 0.25 + 0.75 * hl) if ri == 0 else (50, 53, 60, 255), width=P(1.5))
        dd.rounded_rectangle([P(160), P(24), P(380), P(40)], radius=P(6), fill=(120, 124, 132, 255))
        dd.rounded_rectangle([P(160), P(50), P(300), P(62)], radius=P(5), fill=(64, 68, 76, 255))
        # progress
        ps = 1.55 + ri * 0.12
        pv = eio(prog(u, ps, ps + 0.75 + ri * 0.12))
        dd.rounded_rectangle([P(160), P(82), P(Q_W - 90), P(90)], radius=P(4), fill=(44, 47, 54, 255))
        if pv > 0.01:
            dd.rounded_rectangle([P(160), P(82), P(160 + (Q_W - 250) * pv), P(90)], radius=P(4), fill=GOLD + (255,))
        # status dot / check
        cxp, cyp = Q_W - 46, Q_RH / 2
        if pv >= 1:
            ce = eback(prog(u, ps + 0.75 + ri * 0.12, ps + 1.0 + ri * 0.12))
            rad = 17 * ce
            dd.ellipse([P(cxp - rad), P(cyp - rad), P(cxp + rad), P(cyp + rad)], fill=GOLD + (255,))
            if ce > 0.5:
                dd.line([(P(cxp - 7), P(cyp)), (P(cxp - 2), P(cyp + 6)), (P(cxp + 8), P(cyp - 6))], fill=(14, 14, 16, 255), width=P(3.5), joint='curve')
        else:
            spin = u * 6 + ri
            for k in range(8):
                a = spin + k * math.pi / 4
                al = 0.15 + 0.85 * (k / 7)
                px, py = cxp + math.cos(a) * 11, cyp + math.sin(a) * 11
                dd.ellipse([P(px - 2.5), P(py - 2.5), P(px + 2.5), P(py + 2.5)], fill=rgba((200, 202, 208), al * pe))
        thumb = card_img(BIN_TEX[[4, 0, 6, 2][ri]], 120 / (TEX[BIN_TEX[[4, 0, 6, 2][ri]]].width / S), 0)
        comp(lay, thumb, P(20), P(Q_RH / 2) - thumb.height / 2)
        lay = set_alpha(lay, e)
        if hl > 0:
            comp(base, glow(lay, 16, 0.6 * hl, GOLD), P(x), P(y))
        comp(base, lay, P(x), P(y))
    # drop zone (dashed) before first row lands
    if u < drag_e + 0.05:
        dz = Image.new('RGBA', (P(Q_W) + 2, P(Q_RH) + 2), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dz)
        hot = prog(u, 0.7, 1.0)
        col = tuple(int(lerp(a, b, hot)) for a, b in zip((70, 74, 82), GOLD))
        for k in range(0, Q_W, 24):
            dd.line([(P(k), 0), (P(min(k + 12, Q_W)), 0)], fill=col + (255,), width=P(2))
            dd.line([(P(k), P(Q_RH)), (P(min(k + 12, Q_W)), P(Q_RH))], fill=col + (255,), width=P(2))
        for k in range(0, Q_RH, 24):
            dd.line([(0, P(k)), (0, P(min(k + 12, Q_RH)))], fill=col + (255,), width=P(2))
            dd.line([(P(Q_W), P(k)), (P(Q_W), P(min(k + 12, Q_RH)))], fill=col + (255,), width=P(2))
        comp(base, set_alpha(dz, pe), P(Q_X), P(Q_Y + oy))

    # bin thumbnails with reflow
    re = eio(prog(u, 1.15, 1.6))
    drag_card = 4
    for ci in range(9):
        if ci == drag_card and u >= drag_s - 0.08:
            continue
        sx0, sy0 = slot_xy(PERM_START[ci]); sx1, sy1 = slot_xy(PERM_END[ci])
        # the dragged slot gets filled by reflow
        x, y = lerp(sx0, sx1, re), lerp(sy0, sy1, re) + oy
        lift = math.sin(re * math.pi) * 0.06
        tex = BIN_TEX[ci]
        sc = TW_ / (TEX[tex].width / S) * (1 + lift)
        im = card_img(tex, sc, 0, alpha=pe)
        if TEX[tex].height / TEX[tex].width < 0.6 or KINDS[tex] == 'folder':
            pass
        comp(base, im, x * S - im.width / 2, y * S - im.height / 2)
    # dragged card
    cx0, cy0 = slot_xy(PERM_START[drag_card])
    qx, qy = Q_X + 20 + 60, Q_Y + Q_RH / 2
    cur_x, cur_y = cx0 + 40, cy0 + 70
    if u >= drag_s - 0.08 and u < drag_e + 0.02:
        m = eio(prog(u, drag_s, drag_e))
        lift = eo(prog(u, drag_s - 0.08, drag_s + 0.1))
        x = lerp(cx0, qx, m); y = lerp(cy0, qy, m) - math.sin(m * math.pi) * 60
        tex = BIN_TEX[drag_card]
        base_sc = TW_ / (TEX[tex].width / S)
        sc = lerp(base_sc * (1 + 0.1 * lift), 120 / (TEX[tex].width / S), ei(prog(u, drag_e - 0.15, drag_e)))
        rot = math.sin(m * math.pi) * -6
        im = card_img(tex, sc, rot, gold_edge=lift)
        sh = shadow_for(im, 0.8)
        comp(base, sh, x * S - sh.width / 2 + P(18), y * S - sh.height / 2 + P(28))
        comp(base, glow(im, 14, 0.5 * lift, GOLD), x * S - im.width / 2, y * S - im.height / 2)
        comp(base, im, x * S - im.width / 2, y * S - im.height / 2)
        cur_x, cur_y = x + 30, y + 30
    # cursor path
    if u >= 0.2:
        if u < drag_s - 0.08:
            k = eio(prog(u, 0.2, drag_s - 0.08))
            cur_x, cur_y = lerp(cx0 + 240, cx0 + 30, k), lerp(cy0 + 220, cy0 + 30, k)
        elif u >= drag_e + 0.02:
            k = eo(prog(u, drag_e, drag_e + 0.6))
            cur_x, cur_y = lerp(qx + 30, qx + 260, k), lerp(qy + 30, qy + 380, k)
        ca = clamp((u - 0.2) * 5) * (1 - prog(u, 1.5, 1.8))
        if ca > 0:
            pressed = drag_s - 0.08 <= u < drag_e
            tmp = Image.new('RGBA', (P(70), P(70)), (0, 0, 0, 0))
            draw_cursor(tmp, 8, 8, pressed)
            comp(base, set_alpha(tmp, ca), cur_x * S - P(8), cur_y * S - P(8))

    # ---- text: DRAG. ORGANIZE. RENDER. ----
    words = ['DRAG.', 'ORGANIZE.', 'RENDER.']
    times = [0.12, 0.78, 1.45]
    size = 112
    f = font('Black', size)
    spacing = 46 * S
    widths = [f.getlength(w_) + 3 * S * (len(w_) - 1) for w_ in words]
    total = sum(widths) + spacing * 2
    x = CW / 2 - total / 2
    for wi, w_ in enumerate(words):
        e = eo(prog(u, times[wi], times[wi] + 0.45))
        if e > 0.001:
            cols = [WHITE] * (len(w_) - 1) + [GOLD]
            act = 1 - prog(u, times[wi], times[wi] + 0.6)
            lay, anc, (ct, cb), pad = text_layer(w_, 'Black', size, WHITE, tracking=3, colors=cols,
                                                 per_char=lambda i, e=e: (0, (1 - e) * 130, 1.0))
            lay = clip_rows(lay, ct - P(12), cb + P(12))
            g = glow(lay, 22, 0.25 + 0.7 * act, GOLD)
            comp(base, g, x - pad, 238 * S - anc)
            comp(base, lay, x - pad, 238 * S - anc)
        x += widths[wi] + spacing
    return base

# ---------------- scene 4: production control ----------------
TR = random.Random(9)
TRACKS = []
for k in range(6):
    clips = []
    x = TR.uniform(-300, 0)
    while x < 4200:
        w_ = TR.uniform(120, 420)
        clips.append((x, w_, TR.random() < 0.18))
        x += w_ + TR.uniform(12, 60)
    TRACKS.append(dict(clips=clips, speed=TR.uniform(520, 700)))

def scene_4(t):
    u = t - 6.5
    base = canvas()
    base.alpha_composite(grid_layer(-t * 120, 0, alpha=0.04))
    # pipeline line with nodes
    lay = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    ly = 640
    le = eo(prog(u, 0.0, 0.6))
    x0, x1 = 960 - 860 * le, 960 + 860 * le
    d.line([(P(x0), P(ly)), (P(x1), P(ly))], fill=(70, 74, 82, 255), width=P(2))
    nodes = [200, 580, 960, 1340, 1720]
    for ni, nx in enumerate(nodes):
        ne = eback(prog(u, 0.15 + ni * 0.07, 0.45 + ni * 0.07))
        if ne <= 0: continue
        r_ = 11 * ne
        lit = prog(u, 0.5 + ni * 0.2, 0.6 + ni * 0.2)
        d.ellipse([P(nx - r_), P(ly - r_), P(nx + r_), P(ly + r_)], fill=(14, 15, 19, 255),
                  outline=tuple(int(lerp(a, b, lit)) for a, b in zip((110, 114, 122), GOLD)) + (255,), width=P(2.5))
        if lit > 0:
            d.ellipse([P(nx - 4.5 * lit), P(ly - 4.5 * lit), P(nx + 4.5 * lit), P(ly + 4.5 * lit)], fill=GOLD + (255,))
    # gold progress along line
    pg = eio(prog(u, 0.35, 1.6))
    if pg > 0:
        gx1 = lerp(200, 1720, pg)
        gl = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
        ImageDraw.Draw(gl).line([(P(200), P(ly)), (P(gx1), P(ly))], fill=GOLD + (255,), width=P(3))
        # pulses
        for k in range(3):
            pp = ((u * 0.9 + k / 3) % 1.0)
            px = lerp(200, gx1, pp)
            ImageDraw.Draw(gl).ellipse([P(px - 4), P(ly - 4), P(px + 4), P(ly + 4)], fill=GOLD_L + (255,))
        lay.alpha_composite(glow(gl, 12, 1.2, GOLD))
        lay.alpha_composite(gl)
    base.alpha_composite(lay)

    # timeline tracks
    tl = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tl)
    ph = 960
    ty0 = 700
    te = eo(prog(u, 0.05, 0.6))
    for k, tr_ in enumerate(TRACKS):
        y = ty0 + k * 54 + (1 - eo(prog(u, 0.05 + k * 0.04, 0.55 + k * 0.04))) * 60
        ta = eo(prog(u, 0.05 + k * 0.04, 0.45 + k * 0.04))
        d.line([(0, P(y + 40)), (CW, P(y + 40))], fill=rgba((40, 43, 50), ta), width=P(1))
        off = u * tr_['speed'] + 900
        for (cx, cw_, hot) in tr_['clips']:
            xs = cx - off
            xe = xs + cw_
            if xe < -10 or xs > 1930: continue
            # done (left of playhead) parts become gold-tinted
            if xe <= ph:
                col = (176, 140, 52) if not hot else GOLD
                fa = 0.9
            elif xs >= ph:
                col = (54, 58, 66) if not hot else (90, 80, 50)
                fa = 1.0
            else:
                d.rounded_rectangle([P(xs), P(y), P(ph), P(y + 34)], radius=P(7), fill=rgba((176, 140, 52) if not hot else GOLD, ta * 0.9))
                xs = ph
                col = (54, 58, 66) if not hot else (90, 80, 50); fa = 1.0
            d.rounded_rectangle([P(xs), P(y), P(xe), P(y + 34)], radius=P(7), fill=rgba(col, ta * fa))
    # fade edges
    arr = np.asarray(tl).copy()
    xs_ = np.linspace(0, 1, CW, dtype=np.float32)
    edge = np.clip(np.minimum(xs_, 1 - xs_) / 0.18, 0, 1)
    arr[..., 3] = (arr[..., 3] * edge[None, :]).astype(np.uint8)
    tl = Image.fromarray(arr)
    base.alpha_composite(tl)
    # playhead
    pe = eo(prog(u, 0.2, 0.6))
    if pe > 0:
        phl = Image.new('RGBA', (P(40), P(400)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(phl)
        hh = 380 * pe
        dd.line([(P(20), P(10)), (P(20), P(10 + hh))], fill=GOLD + (255,), width=P(3))
        dd.polygon([(P(8), P(2)), (P(32), P(2)), (P(20), P(18))], fill=GOLD + (255,))
        comp(base, glow(phl, 14, 1.4, GOLD), P(ph - 20), P(ty0 - 20))
        comp(base, phl, P(ph - 20), P(ty0 - 20))

    # scrim
    scrim = Image.new('RGBA', (P(2100), P(900)), (0, 0, 0, 0))
    ImageDraw.Draw(scrim).ellipse([scrim.width*0.18, scrim.height*0.2, scrim.width*0.82, scrim.height*0.8], fill=(4, 5, 7, 200))
    scrim = scrim.resize((scrim.width // 8, scrim.height // 8)).filter(ImageFilter.GaussianBlur(14)).resize(scrim.size, Image.BILINEAR)
    comp(base, scrim, CW / 2 - scrim.width / 2, P(380) - scrim.height / 2)

    # text
    for li, (word, col, cy, st) in enumerate([('PRODUCTION', WHITE, 300, 0.02), ('CONTROL', GOLD, 465, 0.12)]):
        e = eo(prog(u, st, st + 0.9))
        a = clamp(prog(u, st, st + 0.25))
        lay, anc, (ct, cb), pad = text_layer(word, 'Black', 150, col, tracking=lerp(70, 6, e))
        g = glow(lay, 24, 0.3 if li == 0 else 0.6, GOLD)
        # sharpen in: start slightly blurred
        bl = (1 - e) * 10
        if bl > 0.5:
            lay = lay.filter(ImageFilter.GaussianBlur(bl * S * 0.5))
        lay = set_alpha(lay, a)
        g = set_alpha(g, a)
        place_text(base, g, anc, 960, cy)
        place_text(base, lay, anc, 960, cy)
    return base

# ---------------- scene 5: hero ----------------
PR = random.Random(3)
PARTS = [(PR.uniform(0, 1920), PR.uniform(0, 1080), PR.uniform(1, 3.2), PR.uniform(10, 40), PR.uniform(0, 6.28)) for _ in range(70)]

def logo_mark(size, e):
    k = 3
    s = int(size * S * k)
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = int(s * 0.045)
    d.rounded_rectangle([lw, lw, s - lw, s - lw], radius=int(s * 0.24), outline=GOLD + (255,), width=lw)
    # three dock bars
    bx = s * 0.24
    bars = [(0.30, 0.62, (235, 236, 240)), (0.47, 0.78, GOLD), (0.64, 0.50, (235, 236, 240))]
    for bi, (yy_, ln, col) in enumerate(bars):
        be = eo(clamp(e * 1.6 - bi * 0.2))
        h_ = s * 0.095
        d.rounded_rectangle([bx, s * yy_ - h_ / 2, bx + (s * 0.52) * ln * be + h_, s * yy_ + h_ / 2], radius=int(h_ / 2), fill=col + (255,))
    im = im.resize((int(size * S), int(size * S)), Image.LANCZOS)
    padded = Image.new('RGBA', (im.width + P(120), im.height + P(120)), (0, 0, 0, 0))
    padded.alpha_composite(im, (P(60), P(60)))
    return padded

def scene_5(t):
    u = t - 8.5
    base = canvas(BG_WARM)
    # soft gold glow center
    ge = eo(prog(u, 0.0, 0.8))
    gl = Image.new('RGBA', (P(2400), P(1100)), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse([gl.width*0.2, gl.height*0.22, gl.width*0.8, gl.height*0.78], fill=GOLD + (int(46 * ge),))
    gl = gl.resize((gl.width // 10, gl.height // 10)).filter(ImageFilter.GaussianBlur(12)).resize(gl.size, Image.BILINEAR)
    comp(base, gl, CW / 2 - gl.width / 2, P(520) - gl.height / 2)
    # horizon line
    hl = eo(prog(u, 0.0, 0.7))
    lay = Image.new('RGBA', (CW, P(6)), (0, 0, 0, 0))
    arr = np.zeros((P(6), CW, 4), np.uint8)
    xs_ = np.linspace(-1, 1, CW)
    fade = np.clip(1 - np.abs(xs_) / max(hl, 1e-3), 0, 1) ** 1.5
    arr[P(2):P(4), :, :3] = GOLD
    arr[P(2):P(4), :, 3] = (fade * 120).astype(np.uint8)
    lay = Image.fromarray(arr)
    comp(base, lay, 0, P(860))
    # particles
    pl = Image.new('RGBA', (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(pl)
    for (px, py, r_, sp, ph_) in PARTS:
        y = py - sp * (u + 1)
        a = (0.25 + 0.75 * (0.5 + 0.5 * math.sin(ph_ + u * 5))) * ge * 0.55
        d.ellipse([P(px - r_), P(y - r_), P(px + r_), P(y + r_)], fill=rgba(GOLD_L, a))
    base.alpha_composite(pl)

    # logo mark
    le = prog(u, 0.08, 0.6)
    if le > 0:
        sc = eback(le, 1.4)
        m = logo_mark(132, prog(u, 0.15, 0.75))
        m = scale_layer(m, max(sc, 0.01))
        m = set_alpha(m, clamp(le * 3))
        comp(base, glow(m, 20, 0.6, GOLD), CW / 2 - m.width / 2, P(330) - m.height / 2)
        comp(base, m, CW / 2 - m.width / 2, P(330) - m.height / 2)

    # RENDER DOCK
    def pc(i):
        st = 0.18 + abs(i - 5) * 0.03
        e = eo(prog(u, st, st + 0.6))
        return (0, (1 - e) * 170, clamp(e * 2))
    lay, anc, (ct, cb), pad = text_layer('RENDER DOCK', 'Black', 176, WHITE, tracking=lerp(30, 12, eo(prog(u, 0.18, 1.2))), per_char=pc)
    lay = clip_rows(lay, ct - P(14), cb + P(14))
    # shine sweep
    sw = prog(u, 0.75, 1.25)
    if 0 < sw < 1:
        a = np.asarray(lay.split()[3], np.float32) / 255.0
        hgt, wid = a.shape
        X = np.arange(wid)[None, :] + np.arange(hgt)[:, None] * 0.35
        cpos = lerp(-0.2, 1.3, sw) * wid
        band = np.exp(-((X - cpos) / (wid * 0.06)) ** 2)
        sh = np.zeros((hgt, wid, 4), np.uint8)
        sh[..., 0] = 255; sh[..., 1] = 226; sh[..., 2] = 140
        sh[..., 3] = (a * band * 255).astype(np.uint8)
        lay = lay.copy(); lay.alpha_composite(Image.fromarray(sh))
    g = glow(lay, 30, 0.35, GOLD)
    place_text(base, g, anc, 960, 560)
    place_text(base, lay, anc, 960, 560)
    # rule
    rw = eo(prog(u, 0.45, 1.0)) * 560
    if rw > 1:
        rl = Image.new('RGBA', (P(rw) + 1, P(3)), GOLD + (255,))
        comp(base, glow(rl, 10, 1.2, GOLD), CW / 2 - rl.width / 2, P(676))
        comp(base, rl, CW / 2 - rl.width / 2, P(676))
    # By BKE
    be = eo(prog(u, 0.6, 1.1))
    if be > 0:
        f1 = font('Medium', 38); f2 = font('Bold', 38)
        tr = lerp(30, 12, be) * S
        segs = [('By', f1, (205, 207, 212)), (' ', f1, WHITE), ('BKE', f2, GOLD)]
        chars = []
        for s_, f_, c_ in segs:
            for ch in s_: chars.append((ch, f_, c_))
        total = sum(f_.getlength(ch) for ch, f_, _ in chars) + tr * (len(chars) - 1)
        tlay = Image.new('RGBA', (int(total) + P(20), P(70)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(tlay)
        x = P(10)
        for ch, f_, c_ in chars:
            dd.text((x, P(10)), ch, font=f_, fill=rgba(c_, be))
            x += f_.getlength(ch) + tr
        comp(base, tlay, CW / 2 - tlay.width / 2, P(728 + (1 - be) * 24))
    return base

# ---------------- compositor ----------------
def to1x(img):
    return np.asarray(img.convert('RGB').resize((W, H), Image.LANCZOS), np.float32)

def zoom(arr, sc):
    if abs(sc - 1) < 1e-3: return arr
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    w, h = int(W * sc), int(H * sc)
    im = im.resize((w, h), Image.BICUBIC)
    if sc > 1:
        l, t_ = (w - W) // 2, (h - H) // 2
        return np.asarray(im.crop((l, t_, l + W, t_ + H)), np.float32)
    out = Image.fromarray(np.zeros((H, W, 3), np.uint8)); out.paste(im, ((W - w) // 2, (H - h) // 2))
    return np.asarray(out, np.float32)

def hblur(arr, px):
    px = int(px)
    if px < 2: return arr
    acc = np.zeros_like(arr); n = 0
    for k in range(-px, px + 1, max(1, px // 6)):
        acc += np.roll(arr, k, axis=1); n += 1
    return acc / n

def shift(arr, dx):
    dx = int(dx)
    out = np.zeros_like(arr) + BG
    if dx > 0: out[:, dx:] = arr[:, :W - dx]
    elif dx < 0: out[:, :W + dx] = arr[:, -dx:]
    else: out = arr
    return out

def frame(i):
    t = i / FPS
    flash = 0.0
    if t < 4.0:
        if t >= 3.86:
            k = ei(prog(t, 3.86, 4.0))
            a = to1x(scene_12(t))
            arr = hblur(shift(a, -k * 1400), k * 90)
        else:
            arr = to1x(scene_12(t))
        flash = max(0, 1 - (t - 2.0) / 0.2) * 0.5 if t >= 2.0 else 0
        flash += max(0, 1 - abs(t - 0.32) / 0.08) * 0.18
    elif t < 6.5:
        if t < 4.18:
            k = 1 - eo(prog(t, 4.0, 4.18))
            arr = hblur(shift(to1x(scene_3(t)), k * 1400), k * 90)
        elif t >= 6.36:
            k = ei(prog(t, 6.36, 6.5))
            arr = zoom(to1x(scene_3(t)), 1 + 0.35 * k) * (1 - 0.7 * k)
        else:
            arr = to1x(scene_3(t))
    elif t < 8.5:
        if t < 6.75:
            k = eo(prog(t, 6.5, 6.75))
            arr = zoom(to1x(scene_4(t)), lerp(1.18, 1.0, k))
        elif t >= 8.38:
            k = ei(prog(t, 8.38, 8.5))
            arr = zoom(to1x(scene_4(t)), 1 + 0.12 * k)
        else:
            arr = to1x(scene_4(t))
        flash = max(0, 1 - (t - 6.5) / 0.15) * 0.35
        if t >= 8.38: flash = ei(prog(t, 8.38, 8.5)) * 0.85
    else:
        arr = to1x(scene_5(t))
        arr = zoom(arr, 1 + 0.035 * prog(t, 8.5, 10.0))
        flash = max(0, 1 - (t - 8.5) / 0.3) ** 2 * 0.85
    if flash > 0:
        fc = np.array([255, 236, 190], np.float32)
        arr = arr + (fc - arr) * flash
    arr = arr * VIG
    arr = arr + GRAIN[i % 6] * 3.2
    return np.clip(arr, 0, 255).astype(np.uint8)

def work(i):
    p = OUT + f'f{i:04d}.png'
    if os.path.exists(p): return
    Image.fromarray(frame(i)).save(p, compress_level=1)

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.makedirs('test', exist_ok=True)
        for tt in sys.argv[2:]:
            i = int(float(tt) * FPS)
            Image.fromarray(frame(i)).save(f'test/t{float(tt):05.2f}.png')
    else:
        a, b = int(sys.argv[1]), int(sys.argv[2])
        from multiprocessing import Pool
        with Pool(2) as pool:
            pool.map(work, range(a, b), chunksize=4)
