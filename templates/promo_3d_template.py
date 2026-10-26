"""
promo_3d_template.py - 6 s 2.5D promo: cards scattered in depth -> snap flat into one grid -> flat title. (v2.1)

TIMING LIVES IN timeline_3d.json (its own manifest). This file only says what things LOOK like and how 3D is staged.
Read docs/3D_DECISIONS.md first: here space carries the meaning (depth = disorder, one plane = order), which is
the only reason this piece uses real 3D.

  python3 ../scripts/timeline.py check timeline_3d.json     # plan must pass first (includes the 3D rules)
  python3 promo_3d_template.py lint                          # camera + readability + end-state rules -> lint3d.txt
  python3 promo_3d_template.py stills 0.8 2.0 2.6 3.3 4.6    # QA stills -> stills/
  python3 promo_3d_template.py render [--preview]            # frames/ + visual_log.json
  python3 promo_3d_template.py bench                         # seconds per frame at the current S
Then music_synth.py --manifest timeline_3d.json, encode.sh, and the full QA loop (SKILL.md, section 3D).

Phases (all times from the manifest):
  1 scatter  0 -> snap      30 cards scattered in depth and tumbling; ONE camera move: a slow dolly (40 mm, cubic in-out)
                            that settles frontal; the headline card arrives frontal and holds focus while it is read.
  2 align    snap -> title  rank-2 impact: every card snaps flat into a 6x5 grid on one frame; the gold key light
                            sweeps the grid; the grid recedes in depth into the cut.
  3 title    title -> end   rank-1 impact: flat, frontal, still title and end card (2D), receded grid dim behind it.
"""
import sys, os, math, random, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import mglib as M
import mg3d as G
import timeline as TL

MANIFEST = os.environ.get('BKE_MANIFEST', os.path.join(HERE, 'timeline_3d.json'))
TLM = TL.load(MANIFEST)
FPS, DUR = TLM.fps, TLM.duration

# ---------------------------------------------------------------- times (all from the manifest)
E_DOLLY, E_HEAD, E_SNAP, E_SWEEP, E_RECEDE, E_TITLE = (TLM.event(i) for i in ('cam_dolly', 'headline', 'snap', 'rim_sweep', 'recede', 'title'))
T_SNAP, T_TITLE = E_SNAP.t, E_TITLE.t
SNAP_START = T_SNAP - 1 / FPS                     # expo-out: the largest step lands on the declared frame
SNAP_DUR = 0.55
HEAD_IN = E_HEAD.t - 0.10                          # expo-out entrance peaks ~3 frames after it starts
HEAD_OUT = (T_SNAP - 0.50, T_SNAP - 0.15)          # departs expo-in before the snap
FOCUS_PULL = (T_SNAP - 0.50, T_SNAP - 0.05)
SWEEP = (E_SWEEP.t - 0.10, E_SWEEP.t - 0.10 + float(E_SWEEP.duration or 0.7))
RECEDE = (E_RECEDE.t - 0.26, T_TITLE)
MV = E_DOLLY.move3d
LENS = TLM.data['camera3d']['lens_mm']
RIG = G.CameraRig('dolly', E_DOLLY.t, MV['end'], lens_mm=LENS, ease='eio', **{'from': MV['from'], 'to': MV['to']})
D0 = G.Camera.design_distance(lens_mm=LENS)

# ---------------------------------------------------------------- look
KINDS = ['video', 'image', 'audio', 'folder', 'video', 'image', 'video', 'audio']
N, COLS, CELL = 30, 6, (262, 170)
GROUND = -900
LIGHT_A, LIGHT_B = np.array([-1700.0, 600, 900]), np.array([1700.0, 240, 380])
TEX = None; CARDS = None; SCAT = None; GRID = None; HEAD = None; CROSS = None


def assets():
    global TEX, CARDS, SCAT, GRID, HEAD, CROSS
    if TEX is not None: return
    TEX = [M.media_card(k, i * 13 + 5) for i, k in enumerate(KINDS)]
    GRID = G.card_wall(N, COLS, CELL, (0, 0, 0))
    rng = np.random.default_rng(11); SCAT = []
    while len(SCAT) < N:                          # scatter in depth, keeping the headline's window clear
        p = np.array([rng.uniform(-1350, 1350), rng.uniform(-720, 720), rng.uniform(-1800, 700)])
        if abs(p[0]) < 940 and abs(p[1]) < 400 and p[2] > -900: continue
        if math.hypot(p[0], p[1]) < 360: continue
        SCAT.append(dict(pos=p, rot=rng.uniform([-35, -55, -25], [35, 55, 25]), drift=rng.uniform(-1, 1, 3), spin=rng.uniform(-1, 1, 3), delay=rng.uniform(0, 1.3)))
    CARDS = []
    for i in range(N):
        tex = TEX[i % len(TEX)]; w, h = tex.width / M.Cfg.S, tex.height / M.Cfg.S
        k = min(222 / w, 140 / h)                   # fit the grid cell, keep the texture's aspect
        CARDS.append(G.Card(tex, (w * k, h * k), name=f'card{i}'))
    # crossers: extra files streaming SIDEWAYS behind the headline (0.5-2.35 s). A dolly only scales the frame about its
    # centre, so lateral travel is choreography the camera can't explain; it keeps phase 1 busy while the type stays clear.
    CROSS = []
    for j in range(8):
        tex = TEX[(j * 3 + 1) % len(TEX)]; w, h = tex.width / M.Cfg.S, tex.height / M.Cfg.S; k = min(222 / w, 140 / h)
        d = 1 if j % 2 == 0 else -1; t0 = 0.45 + j * 0.17
        CROSS.append(dict(card=G.Card(tex, (w * k, h * k), name=f'cross{j}'), dir=d, t0=t0, t1=t0 + 1.25,
                          y=rng.uniform(-330, 330), z=rng.uniform(-1500, -1050), rot=rng.uniform([-20, -35, -15], [20, 35, 15])))
    txt = 'TOO MANY FILES?'
    T = M.Text(txt, 'Black', 150, M.WHITE, tracking=4, colors=[M.WHITE] * (len(txt) - 1) + [M.GOLD], pad=40)
    HEAD = G.Card(T.img, None, is_text=True, shadow=False, rim=False, name='headline', layer=1)   # read-first type is never crossed


def scattered_xf(i, t):
    """Phase-1 state of card i at time t: scattered position + slow drift, tumbling rotation (from-pole vocabulary)."""
    s = SCAT[i]
    b = M.eo(M.prog(t, s['delay'], s['delay'] + 1.1))            # files keep arriving out of the depth (expo-out, delays 0-1.3 s: pressure builds)
    origin = np.array([0.0, 0.0, -400.0])
    pos = origin + (s['pos'] - origin) * b + s['drift'] * np.array([90, 50, 30]) * t
    rot = s['rot'] * (0.3 + 0.7 * b) + s['spin'] * np.array([36, 46, 24]) * t
    return dict(pos=pos, rot=rot, alpha=M.clamp(b * 4))


def crosser_states(t):
    out = []
    for c in CROSS:
        if not (c['t0'] <= t <= c['t1']): continue
        u = M.prog(t, c['t0'], c['t1']); x = c['dir'] * M.lerp(-2300, 2300, M.eio(u))
        rot = c['rot'] + np.array([0, 25, 10]) * c['dir'] * u
        a = M.clamp(min(u, 1 - u) * 6) * M.lerp(1, 0, M.prog(t, SNAP_START - 0.15, SNAP_START))
        if a > 0.01: out.append(c['card'].with_xf(pos=(x, c['y'], c['z']), rot=rot, alpha=a))
    return out


def light_pos(t):
    return LIGHT_A + (LIGHT_B - LIGHT_A) * M.eio(M.prog(t, *SWEEP))


def sweep_lift(x, t):
    """rim_sweep choreography: as the key light passes a column, its cards lift toward the lens and settle back
    (a ripple running left to right). Zero outside the sweep, so the grid is flat and still before and after."""
    if not (SWEEP[0] <= t <= SWEEP[1] + 0.3): return 0.0
    lx = float(light_pos(t)[0]) * 0.8
    return math.exp(-((x - lx) / 260.0) ** 2) * M.clamp((SWEEP[1] + 0.3 - t) / 0.3)


def card_states(t):
    out = []
    recede_k = M.ei(M.prog(t, *RECEDE))
    for i, c in enumerate(CARDS):
        a = scattered_xf(i, min(t, SNAP_START + SNAP_DUR))
        g = dict(alpha=1.0, pos=np.array(GRID[i]['pos'], float) + np.array([0, 0, -900 * recede_k + 50 * sweep_lift(GRID[i]['pos'][0], t)]), rot=(0, 0, 0))
        xf = G.lerp_xf(a, g, M.eo(M.prog(t, SNAP_START, SNAP_START + SNAP_DUR)))
        alpha = M.lerp(a['alpha'], 1.0, M.prog(t, SNAP_START, SNAP_START + .1)) * M.lerp(1.0, 0.42, M.prog(t, RECEDE[0], T_TITLE + 0.2))
        out.append(c.with_xf(pos=xf['pos'], rot=xf['rot'], alpha=alpha))
    return out


def headline_state(t):
    e = M.eo(M.prog(t, HEAD_IN, HEAD_IN + 0.5)); x = M.ei(M.prog(t, *HEAD_OUT))
    z = M.lerp(-1150, -620, e) + 700 * x
    return HEAD.with_xf(pos=(0, 30, z), rot=(0, 0, 0), scale=1.6, alpha=M.clamp(e * 1.4) * (1 - x))


def renderer(t, cam):
    hd = headline_state(t)
    f_head = float(cam.to_camera(hd.pos[None])[0, 2]); f_grid = float(cam.pos[2] - 0)
    focus = M.lerp(f_head, f_grid, M.eio(M.prog(t, *FOCUS_PULL))) if t < T_TITLE else D0
    lp = light_pos(t)
    rim = M.lerp(0.42, 0.95, M.prog(t, SWEEP[0] - 0.2, SWEEP[0])) * M.lerp(1, 0.5, M.prog(t, RECEDE[0], T_TITLE))
    return G.Renderer(cam, dof=dict(focus=focus, max_px=9, bands=5, aperture=1.0, full_at=0.55),
                      fog=dict(near=2300, far=6200, max=0.75, color=(9, 10, 13)),
                      light=dict(pos=tuple(lp), color=M.GOLD, ambient=0.74, key=0.36, rim=rim),
                      shadow=dict(ground_y=GROUND, dir=(0.2, -1, -0.3), strength=0.38, blur=12)), hd


def scene3d(t):
    assets()
    cam = RIG.at(t); R, hd = renderer(t, cam)
    base = M.canvas(); cards = card_states(t) + crosser_states(t)
    if hd.alpha > 0.01: cards = cards + [hd]
    R.render(base, cards, floor=dict(ground_y=GROUND, step=260, alpha=0.07 * (1 - M.prog(t, RECEDE[0], T_TITLE))))
    return base


PR = random.Random(3); PARTS = [(PR.uniform(0, 1920), PR.uniform(0, 1080), PR.uniform(1, 3.2), PR.uniform(10, 40), PR.uniform(0, 6.28)) for _ in range(60)]
def title_layer(base, t):
    """Phase 3: flat, frontal title (2D). Everything settles; particles fade before the last frame."""
    u = t - T_TITLE; ge = M.eo(M.prog(u, 0, .8))
    gl = Image.new('RGBA', (M.P(2400), M.P(1100)), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse([gl.width * .2, gl.height * .22, gl.width * .8, gl.height * .78], fill=M.GOLD + (int(40 * ge),))
    gl = gl.resize((gl.width // 10, gl.height // 10)).filter(ImageFilter.GaussianBlur(12)).resize(gl.size, Image.BILINEAR)
    M.comp_center(base, M.soft_scrim(2200, 900, .7), 960, 540)
    M.comp_center(base, gl, 960, 520)
    pl = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(pl)
    pfade = 1 - 0.75 * M.eio(M.prog(u, 1.2, 1.9))
    for (px, py, r_, sp, ph) in PARTS:
        y = py - sp * (u + 1); a = (.25 + .75 * (.5 + .5 * math.sin(ph + u * 5))) * ge * .5 * pfade
        d.ellipse([M.P(px - r_), M.P(y - r_), M.P(px + r_), M.P(y + r_)], fill=M.rgba(M.GOLD_L, a))
    base.alpha_composite(pl)
    txt = 'YOUR PRODUCT'
    T = M.Text(txt, 'Black', 176, M.WHITE, tracking=M.lerp(30, 12, M.eo(M.prog(u, .18, 1.2))),
               per_char=M.stagger_rise(t, T_TITLE + .18, step=.03, dur=.6, dist=170, order=lambda i: abs(i - len(txt) // 2)))
    T.mask(14).shine(M.prog(u, .75, 1.25)).draw(base, 960, 520, glow_strength=.35, glow_radius=30)
    M.rule(base, 960, 636, M.eo(M.prog(u, .45, 1)) * 560)
    be = M.eo(M.prog(u, .6, 1.1))
    S_ = M.Text('By YOUR BRAND', 'Medium', 38, (205, 207, 212), tracking=M.lerp(30, 12, be))
    S_.draw(base, 960, 700 + (1 - be) * 24, alpha=be, glow_strength=0)


def frame(i):
    t = i / FPS
    base = scene3d(t)
    if t >= T_TITLE: title_layer(base, t)
    arr = M.to_output(base)
    if t >= T_TITLE: arr = M.zoom(arr, M.lerp(1.18, 1.0, M.eo(M.prog(t, T_TITLE, T_TITLE + .25))))
    fl = 0.0
    amt = {1: .85, 2: .45, 3: .3}
    if T_SNAP <= t < T_SNAP + .2: fl = (1 - (t - T_SNAP) / .2) ** 1.5 * amt[E_SNAP.rank]
    if T_TITLE <= t < T_TITLE + .3: fl = (1 - (t - T_TITLE) / .3) ** 1.5 * amt[E_TITLE.rank]
    if E_RECEDE.t <= t < T_TITLE: fl = M.ei(M.prog(t, E_RECEDE.t, T_TITLE)) * .85
    return M.finish(M.flash(arr, fl), i)


def build_visual_log():
    """Events this renderer performs (sync_check fails any manifest event missing here)."""
    done = {'cam_dolly': 'RIG dolly', 'headline': 'headline_state', 'snap': 'card_states snap', 'rim_sweep': 'renderer light sweep',
            'recede': 'card_states recede', 'title': 'frame flash+zoom', 'title_text': 'title_layer'}
    return [dict(event_id=e.id, t=e.t, scene=TLM.scene_at(e.t).id, renderer=done[e.id]) for e in TLM.events() if e.id in done]


def lint():
    """The 3D decision rules checked on the actual staging (not only the plan)."""
    assets(); L = []
    L += [(lv, 'camera: ' + m) for lv, m in G.lint_rig([RIG])]
    for t in (E_HEAD.t + 0.4, 1.2, HEAD_OUT[0] - 0.05):           # moments the headline must be read
        L += [(lv, f'read @{t:.2f}s: ' + m) for lv, m in G.check_readable([headline_state(t)], RIG.at(t))]
    t_end = DUR - 1 / FPS; cam = RIG.at(t_end)
    tilts = [G.tilt_deg(c, cam) for c in card_states(t_end)]
    L.append(('PASS' if max(tilts) < 0.5 else 'FAIL', f'end state: max card tilt {max(tilts):.2f} deg (flat, frontal)'))
    a, b = card_states(T_TITLE + 0.3), card_states(t_end)
    mv = max(float(np.linalg.norm(x.pos - y.pos)) for x, y in zip(a, b))
    L.append(('PASS' if mv < 1e-6 else 'FAIL', f'end state: cards still after the title (max travel {mv:.3f})'))
    cam_mv = float(np.linalg.norm(RIG.at(T_TITLE).pos - RIG.at(t_end).pos))
    L.append(('PASS' if cam_mv < 1e-6 else 'FAIL', f'end state: camera still in the final scene (travel {cam_mv:.3f})'))
    L.append(('PASS' if 35 <= RIG.lens_mm <= 50 else 'FAIL', f'lens {RIG.lens_mm:.0f} mm = {G.fov_from_mm(RIG.lens_mm):.1f} deg vertical FOV'))
    res = 'FAIL' if any(l == 'FAIL' for l, _ in L) else 'PASS'
    txt = 'LINT 3D  promo_3d_template\n' + '\n'.join(f'{l:4s}  {m}' for l, m in L) + f'\nRESULT: {res}'
    return txt, res


if __name__ == '__main__':
    if '--preview' in sys.argv: M.configure(S=1); sys.argv.remove('--preview')
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
        frame(0); ts = []
        for i in range(0, n, 15):
            t0 = time.perf_counter(); frame(i); ts.append((i, time.perf_counter() - t0))
        print('\n'.join(f'f{i:03d} {s:.3f}s' for i, s in ts))
        print(f'mean {np.mean([s for _, s in ts]):.3f} s/frame, max {max(s for _, s in ts):.3f} s (single process, S={M.Cfg.S})')
    else:
        M.render_all(frame, n, 'frames')
