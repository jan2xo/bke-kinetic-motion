"""
render.py - Render Dock by BKE, 15 s vertical (1080x1920) showcase. Built on bke-kinetic-motion v2.1.

TIMING LIVES IN timeline.json. This file only says what things look like.
  python3 render.py lint | stills 0.8 3.2 ... | render [--preview] | bench | vlog

Story (product facts from github.com/jan2xo/BKE_RENDER_DOCK):
  scatter 0-3   photos, clips, audio and folders scattered in depth, one slow dolly; TOO MANY FILES?
  drop    3-6   every card collapses into the drop zone; three folders are dragged in and queue up
  queue   6-9   each folder renders to its own MP4 (slideshow / videos joined / slideshow + videos), output D:\\BKE_RENDER_DOCK
  output  9-12  the finished 1080p30 MP4 plays as a Ken Burns slideshow; tray toast: render complete
  title  12-15  BKE bolt + RENDER DOCK, DRAG. DROP. DONE., for Windows
"""
import sys, os, math, random, time, json
KIT = os.environ.get('BKE_KIT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(KIT, 'scripts'))
HERE = os.path.dirname(os.path.abspath(__file__))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import mglib as M
import mg3d as G
import timeline as TL

M.configure(W=1080, H=1920)
CY = (60, 200, 240); CY_L = (150, 230, 255); BLUE = (40, 110, 214)
M.GOLD, M.GOLD_L = CY, CY_L              # media_card accents read the module global at call time
W, H = 1080, 1920
BG = M.radial_bg(inner=(20, 27, 38), outer=(5, 7, 11), cy=0.45)

TLM = TL.load(os.path.join(HERE, 'timeline.json'))
FPS, DUR = TLM.fps, TLM.duration
ev = TLM.event
T_DROP, T_OUT, T_TITLE = ev('drop').t, ev('output').t, ev('title').t
T_WHIP = ev('whip_queue').t
LANDS = [ev(f'land{i}').t for i in (1, 2, 3)]
DONES = [ev(f'done{i}').t for i in (1, 2, 3)]
T_TOAST = ev('toast').t
E_HEAD, E_DTITLE, E_REC = ev('headline'), ev('drop_title'), ev('recede')
MV = ev('cam_dolly').move3d
LENS = TLM.data['camera3d']['lens_mm']
RIG = G.CameraRig('dolly', ev('cam_dolly').t, MV['end'], lens_mm=LENS, ease='eio', **{'from': MV['from'], 'to': MV['to']})
D0 = G.Camera.design_distance(lens_mm=LENS)
SNAP_START = T_DROP - 1 / FPS; SNAP_DUR = 0.45
HEAD_IN = E_HEAD.t - 0.10
HEAD_OUT = (T_DROP - 0.55, T_DROP - 0.15)
FOCUS_PULL = (T_DROP - 0.55, T_DROP - 0.05)
END3D = T_DROP + 0.5
ZONE_C = (540, 1010); ZONE_WH = (820, 560)


def cam_scale_at_z0(t):
    return D0 / float(RIG.at(t).pos[2])


# ---------------------------------------------------------------- assets
KINDS = ['image', 'video', 'image', 'folder', 'video', 'audio', 'image', 'video']
N = 30
A = {}


def photo(seed, w=1600, h=900):
    """Procedural landscape photo (sky, sun, layered hills): stands in for the user's pictures."""
    r = random.Random(seed)
    skies = [((255, 170, 110), (60, 70, 140)), ((120, 190, 240), (230, 240, 250)), ((250, 120, 90), (40, 30, 80)), ((90, 160, 200), (20, 50, 90))]
    top, bot = skies[seed % len(skies)]
    t_ = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(bot, np.float32) + (1 - t_) * (np.array(top, np.float32) - np.array(bot, np.float32))
    arr = arr[::-1] if seed % 2 else arr
    im = Image.fromarray(np.repeat(arr, w, 1).astype(np.uint8)).convert('RGBA'); d = ImageDraw.Draw(im)
    sx, sy = r.uniform(.25, .75) * w, r.uniform(.25, .45) * h
    sun = Image.new('RGBA', (w, h), (0, 0, 0, 0)); ImageDraw.Draw(sun).ellipse([sx - 90, sy - 90, sx + 90, sy + 90], fill=(255, 240, 200, 230))
    im.alpha_composite(sun.filter(ImageFilter.GaussianBlur(6)))
    for k in range(4):
        base_y = h * (0.55 + 0.11 * k); col = tuple(int(c * (0.75 - 0.17 * k)) for c in bot)
        pts = [(0, h)] + [(x, base_y - r.uniform(0, h * (0.22 - 0.04 * k))) for x in np.linspace(0, w, 9)] + [(w, h)]
        d.polygon(pts, fill=col + (255,))
    return im.filter(ImageFilter.GaussianBlur(1.2))


def recolor(alpha_img, size_w):
    """BKE logo alpha -> cyan-to-blue gradient (the brand look), at supersample."""
    a = alpha_img.resize((M.P(size_w), int(M.P(size_w) * alpha_img.height / alpha_img.width)), Image.LANCZOS)
    w, h = a.size
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    k = np.clip(0.65 * xx + 0.35 * yy, 0, 1)
    rgb = np.array(CY_L, np.float32) * (1 - k) + np.array(BLUE, np.float32) * k
    rgb = np.broadcast_to(rgb, (h, w, 3))
    out = np.dstack([rgb, np.asarray(a, np.float32)]).astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def rrect(w, h, r, fill, outline=None, width=0):
    im = Image.new('RGBA', (M.P(w), M.P(h)), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=M.P(r), fill=fill, outline=outline, width=M.P(width) if width else 0)
    return im


def assets():
    if A: return
    A['tex'] = [M.media_card(k, i * 13 + 5) for i, k in enumerate(KINDS)]
    A['folder'] = M.media_card('folder', 3)
    rng = np.random.default_rng(21); sc = []
    while len(sc) < N:
        p = np.array([rng.uniform(-1150, 1150), rng.uniform(-1650, 1650), rng.uniform(-2600, 900)])
        if abs(p[0]) < 760 and abs(p[1]) < 420 and p[2] > -1500: continue      # headline window
        if math.hypot(p[0], p[1]) < 300: continue                             # dolly axis
        sc.append(dict(pos=p, rot=rng.uniform([-35, -55, -25], [35, 55, 25]), drift=rng.uniform(-1, 1, 3), spin=rng.uniform(-1, 1, 3), delay=rng.uniform(0, 1.6)))
    A['scat'] = sc
    cards = []
    for i in range(N):
        tex = A['tex'][i % len(A['tex'])]; w, h = tex.width / M.Cfg.S, tex.height / M.Cfg.S
        k = min(300 / w, 190 / h)
        cards.append(G.Card(tex, (w * k, h * k), name=f'card{i}'))
    A['cards'] = cards
    cross = []
    for j in range(16):
        tex = A['tex'][(j * 3 + 1) % len(A['tex'])]; w, h = tex.width / M.Cfg.S, tex.height / M.Cfg.S; k = min(300 / w, 190 / h)
        d = 1 if j % 2 == 0 else -1; t0 = 0.35 + j * 0.13
        cross.append(dict(card=G.Card(tex, (w * k, h * k), name=f'cross{j}'), dir=d, t0=t0, t1=t0 + 1.3,
                          y=rng.uniform(-1300, 1300) if j % 3 else rng.uniform(-700, 700), z=rng.uniform(-1500, -900), rot=rng.uniform([-20, -35, -15], [20, 35, 15])))
    A['cross'] = cross
    l1 = M.Text('TOO MANY', 'Black', 150, M.WHITE, tracking=4, pad=40)
    l2 = M.Text('FILES?', 'Black', 150, M.WHITE, tracking=4, colors=[M.WHITE] * 5 + [CY], pad=40)
    A['head'] = [G.Card(l1.img, None, is_text=True, shadow=False, rim=False, name='head1', layer=1),
                 G.Card(l2.img, None, is_text=True, shadow=False, rim=False, name='head2', layer=1)]
    A['photos'] = [photo(s) for s in (2, 5, 7, 4)]
    A['logo'] = recolor(Image.open(os.path.join(HERE, 'bke_logo_alpha.png')), 560)
    A['logo_small'] = recolor(Image.open(os.path.join(HERE, 'bke_logo_alpha.png')), 120)


# ---------------------------------------------------------------- scene 1: 3D scatter -> drop collapse
def scattered_xf(i, t):
    s = A['scat'][i]
    b = M.eo(M.prog(t, s['delay'], s['delay'] + 1.1))
    origin = np.array([0.0, 0.0, -600.0])
    pos = origin + (s['pos'] - origin) * b + s['drift'] * np.array([90, 60, 30]) * t
    rot = s['rot'] * (0.3 + 0.7 * b) + s['spin'] * np.array([36, 46, 24]) * t
    return dict(pos=pos, rot=rot, alpha=M.clamp(b * 4), scale=1.0)


def drop_target(t):
    """World point that projects onto the drop zone centre at the camera's settled position."""
    s = cam_scale_at_z0(t)
    return np.array([(ZONE_C[0] - W / 2) / s, -(ZONE_C[1] - H / 2) / s, 0.0])


def card_states(t):
    out = []; k = M.eo(M.prog(t, SNAP_START, SNAP_START + SNAP_DUR))
    tgt = drop_target(t)
    for i, c in enumerate(A['cards']):
        a = scattered_xf(i, min(t, SNAP_START))
        g = dict(pos=tgt + np.array([(i % 6 - 2.5) * 22, (i // 6 - 2) * 16, 0]), rot=(0, 0, 0), scale=0.22, alpha=0.0)
        xf = G.lerp_xf(a, g, k)
        out.append(c.with_xf(pos=xf['pos'], rot=xf['rot'], scale=xf['scale'], alpha=xf['alpha'] if t >= SNAP_START else a['alpha']))
    return out


def crosser_states(t):
    out = []
    for c in A['cross']:
        if not (c['t0'] <= t <= c['t1']): continue
        u = M.prog(t, c['t0'], c['t1']); x = c['dir'] * M.lerp(-2100, 2100, M.eio(u))
        rot = c['rot'] + np.array([0, 25, 10]) * c['dir'] * u
        a = M.clamp(min(u, 1 - u) * 6) * M.lerp(1, 0, M.prog(t, SNAP_START - 0.15, SNAP_START))
        if a > 0.01: out.append(c['card'].with_xf(pos=(x, c['y'], c['z']), rot=rot, alpha=a))
    return out


def headline_states(t):
    e = M.eo(M.prog(t, HEAD_IN, HEAD_IN + 0.5)); x = M.ei(M.prog(t, *HEAD_OUT))
    z = M.lerp(-900, 400, e) + 900 * x
    a = M.clamp(e * 1.4) * (1 - x)
    h1, h2 = A['head']
    return [h1.with_xf(pos=(0, 95, z), rot=(0, 0, 0), scale=1.0, alpha=a), h2.with_xf(pos=(0, -95, z), rot=(0, 0, 0), scale=1.0, alpha=a)]


def scene3d(t):
    cam = RIG.at(t); hd = headline_states(t)
    f_head = float(cam.to_camera(hd[0].pos[None])[0, 2]); f_zone = float(cam.pos[2])
    focus = M.lerp(f_head, f_zone, M.eio(M.prog(t, *FOCUS_PULL)))
    R = G.Renderer(cam, dof=dict(focus=focus, max_px=9, bands=5, aperture=1.0, full_at=0.55),
                   fog=dict(near=3600, far=8200, max=0.75, color=(7, 9, 13)),
                   light=dict(pos=(-1700.0, 1400, 1200), color=CY, ambient=0.74, key=0.36, rim=0.5),
                   shadow=None)
    base = M.canvas(BG)
    cards = card_states(t) + crosser_states(t) + [h for h in hd if h.alpha > 0.01]
    cards = [c for c in cards if c.alpha > 0.01]
    R.render(base, cards)
    return base


# ---------------------------------------------------------------- 2D helpers
def dashed_rrect(base, cx, cy, w, h, r, color, a, dash=26, gap=16, width=4):
    lay = Image.new('RGBA', (M.P(w + 40), M.P(h + 40)), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    o = M.P(20); x0, y0, x1, y1 = o, o, o + M.P(w), o + M.P(h); rr = M.P(r)
    d.rounded_rectangle([x0, y0, x1, y1], radius=rr, fill=color + (int(255 * 0.06 * a),))
    pts = []                                   # perimeter as straight runs (corners drawn as arcs below)
    segs = [((x0 + rr, y0), (x1 - rr, y0)), ((x1, y0 + rr), (x1, y1 - rr)), ((x1 - rr, y1), (x0 + rr, y1)), ((x0, y1 - rr), (x0, y0 + rr))]
    col = color + (int(255 * a),); D, Gp = M.P(dash), M.P(gap)
    for (ax, ay), (bx, by) in segs:
        L = math.hypot(bx - ax, by - ay); n = int(L // (D + Gp)) + 1
        for k in range(n):
            s0 = k * (D + Gp); s1 = min(L, s0 + D)
            d.line([(ax + (bx - ax) * s0 / L, ay + (by - ay) * s0 / L), (ax + (bx - ax) * s1 / L, ay + (by - ay) * s1 / L)], fill=col, width=M.P(width))
    for (cx_, cy_, st) in ((x0 + rr, y0 + rr, 180), (x1 - rr, y0 + rr, 270), (x1 - rr, y1 - rr, 0), (x0 + rr, y1 - rr, 90)):
        d.arc([cx_ - rr, cy_ - rr, cx_ + rr, cy_ + rr], st + 20, st + 70, fill=col, width=M.P(width))
    M.comp_center(base, M.glow(lay, 14, 0.6 * a, color), cx, cy); M.comp_center(base, lay, cx, cy)


def arrow_icon(base, cx, cy, a, s=1.0):
    lay = Image.new('RGBA', (M.P(140), M.P(140)), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); P = M.P
    c = CY + (int(255 * a),)
    d.line([(P(70), P(18)), (P(70), P(88))], fill=c, width=P(10))
    d.polygon([(P(38), P(64)), (P(102), P(64)), (P(70), P(102))], fill=c)
    d.rounded_rectangle([P(22), P(112), P(118), P(122)], radius=P(5), fill=c)
    M.comp_center(base, M.scale_layer(lay, s), cx, cy)


def text(base, s, weight, size, cx, cy, color=M.WHITE, alpha=1.0, accent_idx=(), tracking=0, per_char=None, mask=False, glow=0.0, shine=None):
    cols = [CY if i in accent_idx else color for i in range(len(s))]
    T = M.Text(s, weight, size, color, tracking=tracking, colors=cols, per_char=per_char)
    if mask: T.mask(14)
    if shine is not None: T.shine(shine, color=(200, 245, 255))
    T.draw(base, cx, cy, alpha=alpha, glow_color=CY, glow_strength=glow, glow_radius=26)
    return T


def dots_idx(s): return tuple(i for i, c in enumerate(s) if c in '.?')


def bg2d(t):
    base = M.canvas(BG)
    base.alpha_composite(M.grid(offx=t * 14, offy=-t * 22, alpha=0.035, step=90))
    return base


# ---------------------------------------------------------------- scene 2: drag & drop
FOLDERS = [('Family_Trip', '48 photos'), ('Event_Highlights', '12 clips'), ('Product_Shoot', '36 photos + 4 clips')]
STARTS = [(-260, 1500), (1340, 1700), (-260, 720)]


def bez(p0, p1, p2, u):
    return ((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0], (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1])


def cursor(base, x, y, a=1.0):
    lay = Image.new('RGBA', (M.P(60), M.P(80)), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); P = M.P
    pts = [(P(4), P(4)), (P(4), P(62)), (P(19), P(48)), (P(30), P(72)), (P(40), P(67)), (P(29), P(44)), (P(48), P(44))]
    d.polygon(pts, fill=(255, 255, 255, int(255 * a)), outline=(10, 12, 16, int(255 * a)))
    M.comp(base, M.shadow_for(lay, 0.5), M.P(x) - M.P(8), M.P(y) + M.P(6)); M.comp(base, lay, M.P(x), M.P(y))


def chip(base, i, cx, cy, a):
    name, cnt = FOLDERS[i]
    lay = rrect(820, 74, 37, (28, 33, 42, int(235 * a)), outline=(70, 80, 96, int(255 * a)), width=2)
    M.comp_center(base, lay, cx, cy)
    d = ImageDraw.Draw(base); r = M.P(9); x0 = M.P(cx - 370); y0 = M.P(cy)
    d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=CY + (int(255 * a),))
    T = M.Text(name, 'Bold', 32, M.WHITE, pad=10); M.comp(base, M.set_alpha(T.img, a), M.P(cx - 340), y0 - T.anchor)
    T2 = M.Text(cnt, 'Medium', 28, (165, 172, 184), pad=10); M.comp(base, M.set_alpha(T2.img, a), M.P(cx + 380) - T2.img.width + T2.pad, y0 - T2.anchor)


def scene_drop(t):
    base = bg2d(t)
    u = t - T_DROP
    pulse = 1 + 0.08 * (1 - M.eo(M.prog(u, 0, 0.5)))
    land_pulse = max([math.exp(-((t - L) / 0.08) ** 2) * (t >= L - 0.05) for L in LANDS] + [0])
    za = M.clamp(M.eo(M.prog(u, -0.05, 0.25)))
    dashed_rrect(base, ZONE_C[0], ZONE_C[1], ZONE_WH[0] * pulse, ZONE_WH[1] * pulse, 44, CY, za * (0.85 + 0.15 * land_pulse))
    if u < 0.4:   # drop flash fill
        fl = Image.new('RGBA', (M.P(ZONE_WH[0]), M.P(ZONE_WH[1])), (0, 0, 0, 0))
        ImageDraw.Draw(fl).rounded_rectangle([0, 0, fl.width - 1, fl.height - 1], radius=M.P(44), fill=CY + (int(110 * (1 - u / 0.4)),))
        M.comp_center(base, fl, *ZONE_C)
    bob = 8 * math.sin(t * 4)
    arrow_icon(base, ZONE_C[0], ZONE_C[1] - 60 + bob * M.prog(u, .3, .6), za)
    text(base, 'Drop images, videos or folders', 'Medium', 34, ZONE_C[0], ZONE_C[1] + 120, color=(185, 192, 204), alpha=za * M.prog(u, 0.15, 0.5))
    s = 'DRAG. DROP.'
    text(base, s, 'Black', 124, 540, 430, accent_idx=dots_idx(s), tracking=4, mask=True, glow=0.25,
         per_char=M.stagger_rise(t, E_DTITLE.t, step=0.03, dur=0.55, dist=150))
    # folders dragged in, one at a time
    for i, L in enumerate(LANDS):
        t0 = L - 0.62
        if t < t0: continue
        uu = M.prog(t, t0, L); e = M.eio(uu)
        p0 = STARTS[i]; p2 = (ZONE_C[0] + (i - 1) * 150, ZONE_C[1] + 10); p1 = ((p0[0] + p2[0]) / 2, min(p0[1], p2[1]) - 260)
        x, y = bez(p0, p1, p2, e)
        if t < L + 0.25:
            sk = 1 - 0.55 * M.eo(M.prog(t, L, L + 0.25)); fa = 1 - M.prog(t, L + 0.05, L + 0.25)
            tilt = (1 - e) * (-14 if i % 2 else 12)
            f = M.transform_card(A['folder'], 0.7 * sk, tilt, fa)
            M.comp_center(base, M.shadow_for(f, 0.5), x + 10, y + 18); M.comp_center(base, f, x, y)
            if t < L + 0.05: cursor(base, x + 40, y + 30)
        if t >= L:
            ce = M.eo(M.prog(t, L, L + 0.45))
            chip(base, i, 540, 1400 + i * 96 + (1 - ce) * 40, ce)
    return base


# ---------------------------------------------------------------- scene 3: queue
ROWS = [('Family_Trip.mp4', 'Photos to slideshow'), ('Event_Highlights.mp4', 'Clips joined'), ('Product_Shoot.mp4', 'Slideshow + clips')]
ROW_Y = [820, 1040, 1260]
PROG0 = 6.65


def check_mark(base, cx, cy, s, a):
    if s <= 0.01: return
    r = 30 * s; lay = Image.new('RGBA', (M.P(80), M.P(80)), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); P = M.P
    d.ellipse([P(40 - r), P(40 - r), P(40 + r), P(40 + r)], fill=CY + (int(255 * a),))
    if s > 0.5:
        d.line([(P(40 - 13 * s), P(40)), (P(40 - 3 * s), P(40 + 10 * s)), (P(40 + 15 * s), P(40 - 11 * s))], fill=(10, 20, 30, int(255 * a)), width=P(6), joint='curve')
    M.comp_center(base, M.glow(lay, 12, 0.6, CY), cx, cy); M.comp_center(base, lay, cx, cy)


def scene_queue(t):
    base = bg2d(t)
    for k, (s, y) in enumerate((('EVERY FOLDER.', 360), ('ITS OWN MP4.', 480))):
        text(base, s, 'Black', 104, 540, y, accent_idx=dots_idx(s), tracking=2, mask=True, glow=0.2,
             per_char=M.stagger_rise(t, T_WHIP + 0.05 + k * 0.12, step=0.025, dur=0.55, dist=130))
    for i, (name, sub) in enumerate(ROWS):
        y = ROW_Y[i]; ein = M.eo(M.prog(t, T_WHIP + 0.12 + i * 0.12, T_WHIP + 0.67 + i * 0.12))
        if ein <= 0: continue
        oy = (1 - ein) * 80
        M.comp_center(base, rrect(920, 180, 28, (24, 28, 36, int(240 * ein)), outline=(56, 64, 78, int(255 * ein)), width=2), 540, y + oy)
        f = M.transform_card(A['folder'], 0.42, 0, ein); M.comp_center(base, f, 160, y - 18 + oy)
        T = M.Text(name, 'Bold', 36, M.WHITE, pad=10); M.comp(base, M.set_alpha(T.img, ein), M.P(240) - T.pad, M.P(y - 40 + oy) - T.anchor)
        T2 = M.Text(sub, 'Medium', 27, (160, 168, 182), pad=10); M.comp(base, M.set_alpha(T2.img, ein), M.P(240) - T2.pad, M.P(y + 2 + oy) - T2.anchor)
        p = M.eio(M.prog(t, PROG0 + i * 0.12, DONES[i]))
        bx0, bx1, by = 240, 900, y + 50 + oy
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([M.P(bx0), M.P(by - 6), M.P(bx1), M.P(by + 6)], radius=M.P(6), fill=(48, 54, 66, int(255 * ein)))
        if p > 0.005:
            bar = Image.new('RGBA', (max(1, M.P((bx1 - bx0) * p)), M.P(12)), (0, 0, 0, 0))
            ImageDraw.Draw(bar).rounded_rectangle([0, 0, bar.width - 1, bar.height - 1], radius=M.P(6), fill=CY + (255,))
            M.comp(base, M.glow(bar, 8, 0.8, CY), M.P(bx0), M.P(by - 6)); M.comp(base, bar, M.P(bx0), M.P(by - 6))
        if t < DONES[i]:
            pc = M.Text(f'{int(p * 100)}%', 'Bold', 30, CY_L, pad=10)
            M.comp(base, M.set_alpha(pc.img, ein), M.P(905) - pc.img.width + pc.pad, M.P(y - 40 + oy) - pc.anchor)
        else:
            s = M.eback(M.prog(t, DONES[i], DONES[i] + 0.32)); check_mark(base, 872, y - 38 + oy, s, 1.0)
    fa = M.eo(M.prog(t, T_WHIP + 0.9, T_WHIP + 1.4))
    text(base, 'Saved to  D:\\BKE_RENDER_DOCK', 'Medium', 32, 540, 1480 + (1 - fa) * 20, color=(170, 178, 192), alpha=fa)
    return base


# ---------------------------------------------------------------- scene 4: output
PL_W, PL_H, PL_C = 960, 540, (540, 960)


def player(base, t):
    u = max(0.0, t - T_OUT); seg = 1.0
    k = min(int(u // seg), len(A['photos']) - 1); fr = u - k * seg
    img = Image.new('RGBA', (M.P(PL_W), M.P(PL_H)), (0, 0, 0, 255))
    def kb(idx, local):
        ph = A['photos'][idx % len(A['photos'])]; z = 1.0 + 0.12 * (local / 1.6)        # zoompan: z = zoom + c, centred
        cw, ch = ph.width / z, ph.height / z; x0 = (ph.width - cw) / 2 + (8 if idx % 2 else -8) * local * 6; y0 = (ph.height - ch) / 2
        return ph.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize(img.size, Image.BILINEAR)
    cur = kb(k, fr + 0.35); img.alpha_composite(cur)
    if k + 1 < len(A['photos']) and fr > seg - 0.35:
        img = Image.blend(img, kb(k + 1, fr - seg + 0.35).convert('RGBA'), M.eio((fr - (seg - 0.35)) / 0.35))
    m = Image.new('L', img.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=M.P(24), fill=255)
    img.putalpha(m)
    M.comp_center(base, M.shadow_for(img, 0.7), PL_C[0], PL_C[1] + 24)
    M.comp_center(base, img, *PL_C)
    # playhead
    by = PL_C[1] + PL_H / 2 + 46; bx0, bx1 = PL_C[0] - PL_W / 2, PL_C[0] + PL_W / 2
    p = M.clamp(u / 12.0 * 3.2)
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([M.P(bx0), M.P(by - 4), M.P(bx1), M.P(by + 4)], radius=M.P(4), fill=(52, 58, 70, 255))
    d.rounded_rectangle([M.P(bx0), M.P(by - 4), M.P(bx0 + (bx1 - bx0) * p), M.P(by + 4)], radius=M.P(4), fill=CY + (255,))
    hx = bx0 + (bx1 - bx0) * p; d.ellipse([M.P(hx - 11), M.P(by - 11), M.P(hx + 11), M.P(by + 11)], fill=(255, 255, 255, 255))
    secs = int(u)
    T = M.Text(f'0:{secs:02d} / 0:12', 'Medium', 26, (170, 178, 192), pad=10); M.comp(base, T.img, M.P(bx0) - T.pad, M.P(by + 40) - T.anchor)
    T = M.Text('Family_Trip.mp4', 'Bold', 26, M.WHITE, pad=10); M.comp(base, T.img, M.P(bx1) - T.img.width + T.pad, M.P(by + 40) - T.anchor)


def scene_output(t):
    base = bg2d(t)
    for k, (s, y) in enumerate((('YOUR MP4.', 360), ('READY.', 480))):
        text(base, s, 'Black', 112, 540, y, accent_idx=dots_idx(s), tracking=2, mask=True, glow=0.2,
             per_char=M.stagger_rise(t, T_OUT + 0.12 + k * 0.12, step=0.03, dur=0.55, dist=130))
    player(base, t)
    for j, lab in enumerate(('1920 x 1080', '30 fps', 'H.264 MP4')):
        ce = M.eo(M.prog(t, T_OUT + 0.9 + j * 0.12, T_OUT + 1.4 + j * 0.12))
        if ce <= 0: continue
        cx = 540 + (j - 1) * 300; cy = 1390 + (1 - ce) * 30
        M.comp_center(base, rrect(270, 70, 35, (26, 32, 42, int(240 * ce)), outline=CY + (int(150 * ce),), width=2), cx, cy)
        text(base, lab, 'Bold', 30, cx, cy, color=CY_L if j == 0 else M.WHITE, alpha=ce)
    te = M.eo(M.prog(t, T_TOAST - 0.08, T_TOAST + 0.45))
    if te > 0:
        ty = 1640 + (1 - te) * 300
        M.comp_center(base, M.shadow_for(rrect(900, 150, 26, (0, 0, 0, 255)), 0.6), 540, ty + 16)
        M.comp_center(base, rrect(900, 150, 26, (30, 36, 47, 250), outline=(70, 82, 100, 255), width=2), 540, ty)
        M.comp_center(base, A['logo_small'], 190, ty)
        T = M.Text('Render Dock', 'Bold', 32, M.WHITE, pad=10); M.comp(base, T.img, M.P(275) - T.pad, M.P(ty - 26) - T.anchor)
        T = M.Text('Render complete  ·  3 videos', 'Medium', 28, (176, 184, 198), pad=10); M.comp(base, T.img, M.P(275) - T.pad, M.P(ty + 22) - T.anchor)
        check_mark(base, 920, ty, M.eback(M.prog(t, T_TOAST + 0.1, T_TOAST + 0.42)), 1.0)
    return base


# ---------------------------------------------------------------- scene 5: title
PR = random.Random(3); PARTS = [(PR.uniform(0, W), PR.uniform(0, H), PR.uniform(1, 3.2), PR.uniform(10, 40), PR.uniform(0, 6.28)) for _ in range(70)]


def particles(base, t, ge, fade=1.0):
    pl = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(pl)
    for (px, py, r_, sp, ph) in PARTS:
        y = (py - sp * (t + 1)) % H; a = (.25 + .75 * (.5 + .5 * math.sin(ph + t * 5))) * ge * .5 * fade
        d.ellipse([M.P(px - r_), M.P(y - r_), M.P(px + r_), M.P(y + r_)], fill=M.rgba(CY_L, a))
    base.alpha_composite(pl)


def scene_title(t):
    base = M.canvas(BG); u = t - T_TITLE; ge = M.eo(M.prog(u, 0, .8))
    gl = Image.new('RGBA', (M.P(1300), M.P(1300)), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse([gl.width * .15, gl.height * .15, gl.width * .85, gl.height * .85], fill=CY + (int(42 * ge),))
    gl = gl.resize((gl.width // 10, gl.height // 10)).filter(ImageFilter.GaussianBlur(12)).resize(gl.size, Image.BILINEAR)
    M.comp_center(base, gl, 540, 880)
    particles(base, t, ge, 1 - 0.75 * M.eio(M.prog(u, 1.4, 2.2)))
    le = M.eo(M.prog(u, 0.0, 0.7))
    lg = M.set_alpha(A['logo'], le)
    M.comp_center(base, M.glow(lg, 26, 0.55 * le, CY), 540, 780 + (1 - le) * 40); M.comp_center(base, lg, 540, 780 + (1 - le) * 40)
    s = 'RENDER DOCK'
    T = M.Text(s, 'Black', 118, M.WHITE, tracking=M.lerp(26, 8, M.eo(M.prog(u, .18, 1.2))),
               per_char=M.stagger_rise(t, T_TITLE + .18, step=.03, dur=.6, dist=150, order=lambda i: abs(i - len(s) // 2)))
    T.mask(14).shine(M.prog(u, .75, 1.25), color=(200, 245, 255)).draw(base, 540, 1010, glow_color=CY, glow_strength=.35, glow_radius=30)
    M.rule(base, 540, 1092, M.eo(M.prog(u, .45, 1)) * 520, color=CY)
    s2 = 'DRAG. DROP. DONE.'
    text(base, s2, 'Bold', 54, 540, 1175, accent_idx=dots_idx(s2), tracking=6, mask=True,
         per_char=M.stagger_rise(t, T_TITLE + 0.95, step=0.025, dur=0.5, dist=70))
    be = M.eo(M.prog(u, 1.45, 1.95))
    text(base, 'for Windows', 'Medium', 36, 540, 1262 + (1 - be) * 20, color=(170, 178, 192), alpha=be, tracking=M.lerp(16, 6, be))
    return base


# ---------------------------------------------------------------- frame
def render_scene(t):
    if t < T_DROP: return scene3d(t)
    if t < T_WHIP: 
        base = scene_drop(t)
        if t < END3D:          # the last collapsing cards finish over the zone
            ov = scene3d(t); a = 1 - M.prog(t, T_DROP, END3D)
            # draw only the 3D cards on top: diff against a clean background is overkill; fade the 3D frame in its card pixels
            arr = np.asarray(ov, np.float32); bg = np.asarray(M.canvas(BG), np.float32)
            m = np.clip(np.abs(arr[..., :3] - bg[..., :3]).max(-1, keepdims=True) / 40, 0, 1) * a
            out = np.asarray(base, np.float32); out[..., :3] = out[..., :3] * (1 - m) + arr[..., :3] * m
            base = Image.fromarray(out.astype(np.uint8), 'RGBA')
        return base
    if t < T_OUT: return scene_queue(t)
    if t < T_TITLE: return scene_output(t)
    return scene_title(t)


def frame(i):
    assets()
    t = i / FPS
    w_out = (T_WHIP - 0.15, T_WHIP); w_in = (T_WHIP, T_WHIP + 0.2)
    if w_out[0] <= t < T_WHIP:
        arr = M.whip_out(render_scene, t, *w_out, dist=1000, blur=80)
    elif T_WHIP <= t < w_in[1]:
        arr = M.whip_in(render_scene, t, *w_in, dist=1000, blur=80)
    elif T_OUT - 0.4 <= t < T_OUT:
        arr = M.zoom_through_out(render_scene, t, T_OUT - 0.4, T_OUT, amount=0.4)
    elif T_OUT <= t < T_OUT + 0.3:
        arr = M.zoom_in(render_scene, t, T_OUT, T_OUT + 0.3, start=1.25)
    elif E_REC.t - 0.3 <= t < T_TITLE:
        k = M.ei(M.prog(t, E_REC.t - 0.3, T_TITLE)); arr = M.zoom(M.to_output(render_scene(t)), 1 - 0.2 * k) * (1 - 0.6 * k)
    else:
        arr = M.to_output(render_scene(t))
        if T_TITLE <= t < T_TITLE + 0.3: arr = M.zoom(arr, M.lerp(1.15, 1.0, M.eo(M.prog(t, T_TITLE, T_TITLE + .3))))
    if arr.shape[0] != H:   # zoom < 1 leaves a smaller array: pad back to frame size
        im = Image.new('RGB', (W, H), tuple(int(c) for c in BG[0, 0])); sm = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        im.paste(sm, ((W - sm.width) // 2, (H - sm.height) // 2)); arr = np.asarray(im, np.float32)
    amt = {1: .85, 2: .45, 3: .3}; fl = 0.0
    for e in (ev('drop'), ev('output'), ev('title')):
        if e.t <= t < e.t + .22: fl = max(fl, (1 - (t - e.t) / .22) ** 1.5 * amt[e.rank])
    if E_REC.t <= t < T_TITLE: fl = M.ei(M.prog(t, E_REC.t, T_TITLE)) * .8
    return M.finish(M.flash(arr, fl), i)


def build_visual_log():
    done = {'cam_dolly': 'RIG dolly', 'headline': 'headline_states', 'drop': 'card_states collapse + flash', 'drop_title': 'scene_drop text',
            'land1': 'scene_drop folder 1', 'land2': 'scene_drop folder 2', 'land3': 'scene_drop folder 3', 'whip_queue': 'frame whip',
            'done1': 'scene_queue check 1', 'done2': 'scene_queue check 2', 'done3': 'scene_queue check 3', 'output': 'frame zoom + flash',
            'toast': 'scene_output toast', 'recede': 'frame recede', 'title': 'frame flash + zoom', 'title_text': 'scene_title'}
    return [dict(event_id=e.id, t=e.t, scene=TLM.scene_at(e.t).id, renderer=done[e.id]) for e in TLM.events() if e.id in done]


def lint():
    assets(); L = []
    L += [(lv, 'camera: ' + m) for lv, m in G.lint_rig([RIG])]
    for t in (E_HEAD.t + 0.45, 1.3, HEAD_OUT[0] - 0.05):
        L += [(lv, f'read @{t:.2f}s: ' + m) for lv, m in G.check_readable(headline_states(t), RIG.at(t))]
    L.append(('PASS' if MV['end'] <= T_DROP else 'FAIL', f'camera settles at {MV["end"]:.2f}s, before the drop at {T_DROP:.2f}s'))
    L.append(('PASS' if END3D <= T_WHIP else 'FAIL', f'3D ends at {END3D:.2f}s; queue, output and end card are flat and frontal'))
    L.append(('PASS' if 35 <= RIG.lens_mm <= 50 else 'FAIL', f'lens {RIG.lens_mm:.0f} mm = {G.fov_from_mm(RIG.lens_mm):.1f} deg vertical FOV'))
    res = 'FAIL' if any(l == 'FAIL' for l, _ in L) else 'PASS'
    return 'LINT 3D  render_dock_15s_vertical\n' + '\n'.join(f'{l:4s}  {m}' for l, m in L) + f'\nRESULT: {res}', res


if __name__ == '__main__':
    if '--preview' in sys.argv: M.configure(S=1, W=1080, H=1920); sys.argv.remove('--preview')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'render'
    n = int(round(DUR * FPS))
    if cmd in ('render', 'vlog'):
        json.dump(build_visual_log(), open('visual_log.json', 'w'), indent=1)
        if cmd == 'vlog': sys.exit(0)
    if cmd == 'lint':
        txt, res = lint(); print(txt); open('lint3d.txt', 'w').write(txt + '\n'); sys.exit(0 if res == 'PASS' else 2)
    elif cmd == 'stills':
        os.makedirs('stills', exist_ok=True)
        for s in sys.argv[2:]:
            Image.fromarray(frame(int(round(float(s) * FPS)))).save(f'stills/t{float(s):05.2f}.png')
    elif cmd == 'bench':
        ts = []
        for i in range(0, n, 30):
            t0 = time.perf_counter(); frame(i); ts.append((i, time.perf_counter() - t0))
        print('\n'.join(f'f{i:03d} {s:.3f}s' for i, s in ts))
        print(f'mean {np.mean([s for _, s in ts]):.3f} s/frame (S={M.Cfg.S})')
    else:
        M.render_all(frame, n, 'frames')
