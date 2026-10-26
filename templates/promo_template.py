"""
promo_template.py - data-driven kinetic promo using mglib.

v2: TIMING LIVES IN timeline.json (the shared manifest), not here. CONFIG only says what each scene LOOKS like.
Scene start/end, transitions, glitch bursts and the impacts all come from the manifest, and the music code reads
the same file, so picture and sound cannot drift apart.

  python3 ../scripts/timeline.py check timeline.json   # creative plan must pass first
  python3 promo_template.py stills 0.8 2.6 4.6        # QA stills -> stills/
  python3 promo_template.py render                     # all frames -> frames/ (+ visual_log.json)
  python3 promo_template.py render --preview           # no supersampling (~3x faster draft)
  python3 promo_template.py vlog                       # only write visual_log.json
Then: python3 ../scripts/music_synth.py --manifest timeline.json --out music.wav --cue-log audio_cues.json
      bash ../scripts/encode.sh frames music.wav out.mp4 <duration>
      (full QA loop: see SKILL.md "Temporal QA")

Beat types:
  glitch_headline : burst of floating media cards + slam-in headline with RGB-split glitch
  rise_headline   : cards snap into an ordered grid, small kicker + letters rising from a mask, gold rule
  hero            : logo-less end card: gold glow, particles, staggered title, shine sweep, rule, subtext
Transitions between beats: 'cut_flash', 'whip', 'zoom'.
"""
import sys, os, math, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import mglib as M
import timeline as TL

MANIFEST = os.environ.get('BKE_MANIFEST', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'timeline.json'))
TLM = TL.load(MANIFEST)

CONFIG = {
    # LOOK only. Times come from the manifest scene with the same id.
    'beats': [
        {'scene': 'chaos',  'type': 'glitch_headline', 'text': 'TOO MANY FILES?', 'accent_last': True},
        {'scene': 'reveal', 'type': 'rise_headline', 'kicker': 'INTRODUCING', 'text': 'YOUR PRODUCT', 'accent_words': 1},
        {'scene': 'hero',   'type': 'hero', 'text': 'YOUR PRODUCT', 'sub': 'By YOUR BRAND'},
    ],
}
CONFIG['fps'] = TLM.fps; CONFIG['duration'] = TLM.duration
for _b in CONFIG['beats']:
    _s = TLM.scene(_b['scene']); _b['start'], _b['end'] = _s.start, _s.end
    _ev = [e for e in TLM.events() if abs(e.t - _s.start) < 1e-6 and e.style in ('cut_flash', 'whip', 'zoom')]
    if _ev and _s.start > 0: _b['transition_in'] = _ev[0].style
# glitch bursts the visuals must perform: accent events with a glitch sound inside a glitch_headline scene
GLITCHES = [e for e in TLM.events(kind='accent') if e.audio == 'glitch']
VISUAL_EVENTS = []   # what this renderer actually implements (written to visual_log.json for sync_check)

# ---------------------------------------------------------------- assets (built once per process)
KINDS = ['video', 'image', 'audio', 'folder', 'video', 'image', 'video', 'audio']
TEX = None; CARDS = None
def assets():
    global TEX, CARDS
    if TEX is not None: return
    TEX = [M.media_card(k, i * 13 + 5) for i, k in enumerate(KINDS)]
    R = random.Random(42); CARDS = []
    for i in range(24):
        ang = R.uniform(0, 2 * math.pi); rad = R.uniform(.25, 1); z = R.uniform(.45, 1.35)
        col, row = i % 8, i // 8
        CARDS.append(dict(tex=i % len(TEX), z=z, delay=R.uniform(0, .25),
                          tx=960 + math.cos(ang) * rad * 1050 * (.8 + .4 * z), ty=540 + math.sin(ang) * rad * 620 * (.8 + .4 * z),
                          vx=R.uniform(-60, 60), vy=R.uniform(-40, 40), r0=R.uniform(-45, 45), rs=R.uniform(-40, 40),
                          gx=960 - 3.5 * 200 + col * 200, gy=540 - 132 + row * 132))
    CARDS.sort(key=lambda c: c['z'])

def beat_pulse(t, bpm, decay=7.0):
    """1 on each beat, decaying exponentially until the next: the 'system in rhythm' signal."""
    beat = 60.0 / bpm; ph = (t % beat) / beat
    return math.exp(-decay * ph * beat)

def cards_layer(base, u, snap, breathe=0.0, t=0.0):
    """u = local time since chaos start; snap 0..1 morphs chaos -> ordered grid (the 'chaos to control' move).
    breathe 0..1: after the snap, the grid pulses on the beat (scale + brightness), a ripple running left to right.
    v2 fix: without it the reveal had a 1.1 s dead hold (motion_energy FAIL 2.83-3.93 s)."""
    for c in CARDS:
        b = M.eo(M.prog(u, c['delay'], c['delay'] + 1))
        x = M.lerp(960, c['tx'], b) + c['vx'] * u; y = M.lerp(540, c['ty'], b) + c['vy'] * u
        rot = c['r0'] * b + c['rs'] * u; sc = c['z'] * .62 * (.25 + .75 * b)
        gsc = 176 / (TEX[c['tex']].width / M.Cfg.S)
        x, y = M.lerp(x, c['gx'], snap), M.lerp(y, c['gy'], snap)
        rot, sc = M.lerp(rot, 0, snap), M.lerp(sc, gsc, snap)
        a = M.lerp(M.lerp(.55, 1, M.prog(c['z'], .45, 1)) * M.clamp(b * 3), 1, snap) * M.lerp(1, .32, M.prog(snap, .6, 1))
        if breathe > 0:
            p = beat_pulse(t - (c['gx'] - 260) / 1400 * 0.18, TLM.bpm or 120) * breathe   # ripple: left columns first
            sc *= 1 + .07 * p; a = min(1, a + .35 * p)
        im = M.transform_card(TEX[c['tex']], sc, rot, a)
        if snap < .9:
            sh = M.shadow_for(im, .5 * a); M.comp_center(base, sh, x + 10, y + 16)
        M.comp_center(base, im, x, y)

# ---------------------------------------------------------------- beat renderers (return supersampled RGBA)
def r_glitch_headline(beat, t):
    assets(); u = t - beat['start']; dur = beat['end'] - beat['start']
    base = M.canvas(); base.alpha_composite(M.grid(-t * 30, -t * 18, .035))
    cards_layer(base, u, 0.0)
    M.comp_center(base, M.soft_scrim(2000, 800, .75), 960, 540)
    e = M.eo(M.prog(u, .3, .75)); out = M.ei(M.prog(u, dur - .18, dur))
    txt = beat['text']; cols = [M.WHITE] * (len(txt) - 1) + [M.GOLD] if beat.get('accent_last') else None
    rr = random.Random(int(t * 30))
    burst = any(g.t <= t < g.t + float(g.duration or .08) for g in GLITCHES if beat['start'] <= g.t < beat['end'] and g.t - beat['start'] > .5)
    jit = M.prog(u, .3, .6) < 1 or burst
    T = M.Text(txt, 'Black', 150, M.WHITE, tracking=M.lerp(40, 4, e), colors=cols,
               per_char=lambda i: ((rr.uniform(-6, 6), rr.uniform(-3, 3), 1) if jit else (0, 0, 1)))
    split = 14 * (1 - M.prog(u, .3, .62)) if u < .62 else (9 if burst else 18 * out)
    T.draw(base, 960, 540, scale=M.lerp(1.55, 1, e) * M.lerp(1, 1.12, out), alpha=M.clamp(e * 1.5) * (1 - out),
           glow_strength=.35, rgb_split_px=split)
    return base

def r_rise_headline(beat, t):
    assets(); u = t - beat['start']
    base = M.canvas(); base.alpha_composite(M.grid(-t * 30, -t * 18, .05))
    # breathe fades in once the title has landed (~0.8 s), so the hold after the reveal stays alive on the beat
    cards_layer(base, u + 2.0, M.eo(M.prog(u, 0, .55)), breathe=M.eio(M.prog(u, .7, 1.0)), t=t)
    M.comp_center(base, M.soft_scrim(2000, 800, .6), 960, 540)
    e1 = M.eo(M.prog(u, .1, .55))
    if beat.get('kicker'):
        K = M.Text(beat['kicker'], 'Bold', 44, M.GOLD, tracking=M.lerp(60, 22, e1)).mask(4)
        K.draw(base, 960, 440 + (1 - e1) * 40, alpha=e1, glow_strength=0)
    txt = beat['text']; words = txt.split(' '); n_acc = beat.get('accent_words', 0)
    acc_from = len(' '.join(words[:len(words) - n_acc])) if n_acc else len(txt)
    cols = [M.WHITE if i < acc_from else M.GOLD for i in range(len(txt))]
    T = M.Text(txt, 'Black', 170, M.WHITE, tracking=8, colors=cols, per_char=M.stagger_rise(t, beat['start'] + .22)).mask(14)
    T.draw(base, 960, 560)
    M.rule(base, 960, 680, M.eo(M.prog(u, .5, 1.1)) * 620)
    return base

PR = random.Random(3); PARTS = [(PR.uniform(0, 1920), PR.uniform(0, 1080), PR.uniform(1, 3.2), PR.uniform(10, 40), PR.uniform(0, 6.28)) for _ in range(70)]
def r_hero(beat, t):
    u = t - beat['start']
    base = M.canvas(M.radial_bg(inner=(32, 29, 23)))
    ge = M.eo(M.prog(u, 0, .8))
    gl = Image.new('RGBA', (M.P(2400), M.P(1100)), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse([gl.width * .2, gl.height * .22, gl.width * .8, gl.height * .78], fill=M.GOLD + (int(46 * ge),))
    gl = gl.resize((gl.width // 10, gl.height // 10)).filter(ImageFilter.GaussianBlur(12)).resize(gl.size, Image.BILINEAR)
    M.comp_center(base, gl, 960, 520)
    pl = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(pl)
    for (px, py, r_, sp, ph) in PARTS:
        y = py - sp * (u + 1); a = (.25 + .75 * (.5 + .5 * math.sin(ph + u * 5))) * ge * .55
        d.ellipse([M.P(px - r_), M.P(y - r_), M.P(px + r_), M.P(y + r_)], fill=M.rgba(M.GOLD_L, a))
    base.alpha_composite(pl)
    T = M.Text(beat['text'], 'Black', 176, M.WHITE, tracking=M.lerp(30, 12, M.eo(M.prog(u, .18, 1.2))),
               per_char=M.stagger_rise(t, beat['start'] + .18, step=.03, dur=.6, dist=170, order=lambda i: abs(i - len(beat['text']) // 2)))
    T.mask(14).shine(M.prog(u, .75, 1.25)).draw(base, 960, 520, glow_strength=.35, glow_radius=30)
    M.rule(base, 960, 636, M.eo(M.prog(u, .45, 1)) * 560)
    if beat.get('sub'):
        be = M.eo(M.prog(u, .6, 1.1))
        S_ = M.Text(beat['sub'], 'Medium', 38, (205, 207, 212), tracking=M.lerp(30, 12, be))
        S_.draw(base, 960, 700 + (1 - be) * 24, alpha=be, glow_strength=0)
    return base

RENDER = {'glitch_headline': r_glitch_headline, 'rise_headline': r_rise_headline, 'hero': r_hero}

# ---------------------------------------------------------------- timeline / compositor
def beat_at(t):
    for b in CONFIG['beats']:
        if b['start'] <= t < b['end']: return b
    return CONFIG['beats'][-1]

def frame(i):
    t = i / CONFIG['fps']; b = beat_at(t); fn = lambda tt: RENDER[b['type']](b, tt)
    tr = b.get('transition_in'); u = t - b['start']
    nxt = [x for x in CONFIG['beats'] if x['start'] == b['end']]
    out_tr = nxt[0].get('transition_in') if nxt else None
    if tr == 'whip' and u < .18:        arr = M.whip_in(fn, t, b['start'], b['start'] + .18)
    elif tr == 'zoom' and u < .25:      arr = M.zoom_in(fn, t, b['start'], b['start'] + .25)
    elif out_tr == 'whip' and t >= b['end'] - .14: arr = M.whip_out(fn, t, b['end'] - .14, b['end'])
    elif out_tr == 'zoom' and t >= b['end'] - .12: arr = M.zoom_through_out(fn, t, b['end'] - .12, b['end'], .12)
    else: arr = M.to_output(fn(t))
    if b['type'] == 'rise_headline':                       # slow push-in keeps the held title alive (v2)
        arr = M.zoom(arr, 1 + .035 * M.eio(M.prog(u, .6, b['end'] - b['start'])))
    fl = 0
    # flash size follows narrative rank from the manifest: rank 1 (payoff) gets the biggest hit (v2)
    if tr in ('cut_flash', 'zoom'):
        ev = [e for e in TLM.events() if abs(e.t - b['start']) < 1e-6 and e.rank]
        amt = {1: .85, 2: .45, 3: .3}.get(ev[0].rank if ev else 3, .3)
        fl = max(0, 1 - u / (.2 if tr == 'cut_flash' else .3)) ** 1.5 * amt
    if out_tr == 'zoom' and t >= b['end'] - .12: fl = M.ei(M.prog(t, b['end'] - .12, b['end'])) * .85
    return M.finish(M.flash(arr, fl), i)

def build_visual_log():
    """Declare which manifest events this renderer performs, at which time. sync_check fails any it misses."""
    out = []
    for b in CONFIG['beats']:
        for e in TLM.events():
            if not (b['start'] - 1e-6 <= e.t < b['end'] - 1e-6) and not (e.kind == 'transition' and abs(e.t - (b['end'] - .12)) < 1e-6):
                continue
            ok = False
            if e.kind == 'accent' and e.audio == 'glitch' and b['type'] == 'glitch_headline': ok = True
            if e.kind in ('impact', 'transition') and e.style in ('cut_flash', 'whip', 'zoom', 'zoom_out'): ok = True
            if e.kind == 'text' and (b.get('text') or b.get('kicker')): ok = True
            if e.kind == 'reveal' and b['type'] == 'hero': ok = True
            if ok and all(v['event_id'] != e.id for v in out):
                out.append(dict(event_id=e.id, t=e.t, scene=b['scene'], renderer=b['type']))
    return out

if __name__ == '__main__':
    if '--preview' in sys.argv: M.configure(S=1); sys.argv.remove('--preview')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'render'
    n = int(round(CONFIG['duration'] * CONFIG['fps']))
    if cmd in ('render', 'vlog'):
        import json
        json.dump(build_visual_log(), open('visual_log.json', 'w'), indent=1)
        if cmd == 'vlog': sys.exit(0)
    if cmd == 'stills':
        os.makedirs('stills', exist_ok=True)
        for s in sys.argv[2:]:
            Image.fromarray(frame(int(float(s) * CONFIG['fps']))).save(f'stills/t{float(s):05.2f}.png')
    else:
        M.render_all(frame, n, 'frames')
