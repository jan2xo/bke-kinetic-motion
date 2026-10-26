#!/usr/bin/env python3
"""preview.py - temporal QA: short motion previews of the moments that stills can't judge.

  python3 preview.py out.mp4 --manifest timeline.json --motion qa/motion_report.json --out qa/previews
  python3 preview.py out.mp4 --at 3.8:4.3 --at 8.4:9.4 --out qa/previews      # manual windows

It picks the windows that matter automatically:
  entrance   - the first 0.6 s of every scene
  transition - 0.35 s either side of every impact / transition event
  hold       - every hold motion_energy flagged (WARN/FAIL), so you can judge if the stillness works
  reveal     - the whole final scene
For each window it writes
  <id>_1x.mp4 and <id>_half.mp4   real-time and half-speed clip with a timecode   -> WATCH these
  <id>_strip.jpg                  every frame (up to 18) with time and an activity bar -> spacing/easing
  <id>_onion.jpg                  onion skin: earlier frames fainter -> trajectory, arcs, overlaps
and index.md: the windows, their measured easing signature, and the questions to answer for each.

EASING SIGNATURE (measured, a hint, not a verdict): share of the window's motion in its first vs last third.
  front-loaded (ratio > 1.5)  ~ ease-out: fast arrival, soft landing      (good for entrances)
  even         (0.67 .. 1.5)  ~ linear or sustained motion                (good for machines, bad for type)
  back-loaded  (ratio < 0.67) ~ ease-in: accelerating                     (good for exits / builds into a cut)
"""
import argparse, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FONT = os.path.join(HERE, '..', 'fonts', 'Montserrat-Medium.ttf')

QUESTIONS = {
    'entrance': ['Does ONE element clearly lead (the dominant motion in the beat sheet)?',
                 'Arrival: fast start, long soft settle? Any element that just appears or stops dead?',
                 'Is the stagger readable as a sequence rather than a crowd?'],
    'transition': ['Does motion build INTO the cut (anticipation) and release after it?',
                   'Is the hit on the exact frame of the sound? Any frame where nothing reads?',
                   'Does the direction of the transition match the story (sideways = next topic, in = deeper)?'],
    'hold': ['Is this stillness planned (a rest the viewer needs) or dead air?',
             'If dead: what should still be alive here (ambient drift, a supporting move, the next element arriving)?',
             'Is the text on screen long enough to read and no longer?'],
    'reveal': ['Is the payoff the largest moment of the piece and visibly resolved (symmetry, stillness at the end)?',
               'Does the end card hold long enough to read the brand, and does everything come to rest?',
               'Any motion still running at the last frame that makes it feel cut off?'],
    'camera': ['3D (v2.1): is this the ONLY camera move in the shot, and does it start and settle softly (no jolt, no overshoot)?',
               'Does the move carry meaning (into the mess, settling into order) or is it decoration?',
               'Is any type tilted more than 20 deg while it should be read? Does focus sit on what reads first?'],
    'manual': ['What is the dominant motion and does it read first?', 'Easing and velocity: does it feel weighted?'],
}


def extract(video, t0, t1, width=480):
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'json', video],
                       capture_output=True, text=True)
    s = json.loads(p.stdout)['streams'][0]; n_, d_ = s['r_frame_rate'].split('/'); fps = float(n_) / float(d_)
    h = int(round(s['height'] * width / s['width'] / 2) * 2)
    cmd = ['ffmpeg', '-v', 'error', '-ss', f'{max(0, t0):.3f}', '-i', video, '-t', f'{t1 - t0:.3f}', '-vf', f'scale={width}:{h}:flags=area',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    fr = [np.frombuffer(raw[i:i + width * h * 3], np.uint8).reshape(h, width, 3) for i in range(0, len(raw) - width * h * 3 + 1, width * h * 3)]
    return fr, fps


def clips(video, t0, t1, out_base):
    esc = FONT.replace(':', r'\:')
    dt = f"drawtext=fontfile='{esc}':text='%{{pts\\:hms}}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
    for tag, setpts in (('1x', 'PTS-STARTPTS'), ('half', '2*(PTS-STARTPTS)')):
        vf = f'scale=960:-2,setpts={setpts},{dt}'
        cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', f'{max(0, t0):.3f}', '-i', video, '-t', f'{t1 - t0:.3f}', '-vf', vf, '-an',
               '-c:v', 'libx264', '-crf', '22', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', f'{out_base}_{tag}.mp4']
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:  # drawtext unavailable: retry without timecode
            cmd[cmd.index('-vf') + 1] = f'scale=960:-2,setpts={setpts}'
            subprocess.run(cmd, capture_output=True)


def strip(frames, t0, fps, act, path, title):
    try: F = ImageFont.truetype(FONT, 14); FB = ImageFont.truetype(FONT, 18)
    except Exception: F = FB = ImageFont.load_default()
    n = len(frames)
    idx = list(range(n)) if n <= 18 else [int(round(k * (n - 1) / 17)) for k in range(18)]
    h0, w0 = frames[0].shape[:2]; tw = 300; th = int(h0 * tw / w0)
    cols = 6; rows = (len(idx) + cols - 1) // cols
    W = cols * (tw + 8) + 8; H = 44 + rows * (th + 34) + 110
    im = Image.new('RGB', (W, H), (12, 13, 16)); d = ImageDraw.Draw(im)
    d.text((8, 10), title, font=FB, fill=(244, 245, 247))
    amax = max([act[int(round(t0 * fps)) + k] for k in range(n) if act is not None and int(round(t0 * fps)) + k < len(act)] or [1])
    for k, i in enumerate(idx):
        x = 8 + (k % cols) * (tw + 8); y = 44 + (k // cols) * (th + 34)
        im.paste(Image.fromarray(frames[i]).resize((tw, th), Image.BILINEAR), (x, y))
        ft = t0 + i / fps
        d.text((x + 2, y + th + 3), f'{ft:.3f}s  f{int(round(ft * fps))}', font=F, fill=(180, 184, 190))
        if act is not None:
            gi = int(round(ft * fps))
            if 0 <= gi < len(act):
                bw = int((tw - 120) * act[gi] / amax)
                d.rectangle([x + 118, y + th + 8, x + 118 + bw, y + th + 16], fill=(255, 194, 40))
    if act is not None:  # activity sparkline across the window
        gy = H - 100; gx0, gx1 = 8, W - 8
        a0 = int(round(t0 * fps)); seg = np.array(act[a0:a0 + n]) if a0 < len(act) else np.zeros(1)
        if len(seg) > 1:
            mx = max(seg.max(), 1e-6)
            pts = [(gx0 + (gx1 - gx0) * k / (len(seg) - 1), gy + 80 - 75 * v / mx) for k, v in enumerate(seg)]
            d.rectangle([gx0, gy, gx1, gy + 82], outline=(40, 43, 50)); d.line(pts, fill=(255, 194, 40), width=2)
            d.text((gx0 + 4, gy + 2), 'activity in window (frame to frame change)', font=F, fill=(150, 154, 162))
    im.save(path, quality=88)


def onion(frames, path):
    if not frames: return
    n = len(frames); acc = np.zeros_like(frames[0], np.float32)
    for k, f in enumerate(frames):
        w = 0.25 + 0.75 * (k / max(1, n - 1))
        acc = np.maximum(acc, f.astype(np.float32) * w)
    Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8)).save(path, quality=88)


def _seg(act, t0, t1, fps):
    a, b = max(0, int(round(t0 * fps))), int(round(t1 * fps))
    return np.array(act[a:b], float)


def signature(act, t0, t1, fps, kind='entrance', hit=None, dmean=None):
    """Measured hint about the motion shape inside a window. Cut frames are excluded so a hard cut
    does not masquerade as an ease-out."""
    if act is None: return None, None
    if kind == 'transition' and hit is not None:
        pre_a = _seg(act, hit - 0.35, hit - 0.2, fps); pre_b = _seg(act, hit - 0.15, hit - 0.02, fps)
        post = _seg(act, hit + 0.1, hit + 0.35, fps)
        if len(pre_a) and len(pre_b) and len(post):
            build = float(pre_b.mean() / (pre_a.mean() + 1e-6)); rel = float(post.mean() / (pre_b.mean() + 1e-6))
            lab = ('builds into the hit' if build > 1.2 else ('flat before the hit (no anticipation)' if build > 0.8 else 'drops before the hit'))
            return round(build, 2), f'{lab}; after/before = {rel:.2f}'
        return None, None
    seg = _seg(act, t0, t1, fps)
    if kind in ('entrance', 'reveal', 'camera'):
        skip = 3                                                # skip the cut frame ...
        if dmean is not None:                                   # ... and any flash still fading (global brightness moving)
            dm = np.abs(_seg(dmean, t0, t1, fps))
            while skip < len(dm) and dm[skip] > 1.0: skip += 1
        seg = seg[skip:]
    if len(seg) < 6: return None, None
    seg = np.clip(seg - np.percentile(seg, 10), 0, None); k = len(seg) // 3
    f, l = seg[:k].sum(), seg[-k:].sum()
    r = float(min(99.0, (f + 1e-3) / (l + 1e-3)))
    lab = 'front-loaded (ease-out-like)' if r > 1.5 else ('back-loaded (ease-in-like)' if r < 0.67 else 'even (linear/sustained)')
    if kind == 'hold':
        lab = f'mean activity {float(_seg(act, t0, t1, fps).mean()):.2f}; ' + lab
    return round(r, 2), lab


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video'); ap.add_argument('--manifest'); ap.add_argument('--motion'); ap.add_argument('--out', default='qa/previews')
    ap.add_argument('--at', action='append', default=[], help='manual window start:end (s)'); ap.add_argument('--no-clips', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rep = json.load(open(a.motion)) if a.motion else None
    act = rep['series']['activity'] if rep else None
    import timeline as TL
    T = TL.load(a.manifest) if a.manifest else None
    dur = (rep['meta']['n'] / rep['meta']['fps']) if rep else (T.duration if T else None)
    W = []
    if T:
        for s in T.scenes:
            W.append(('entrance', f'enter_{s.id}', s.start, min(s.end, s.start + 0.6), None))
        for e in T.events():
            if e.kind in ('impact', 'transition'):
                W.append(('transition', f'hit_{e.id}', max(0, e.t - 0.35), min(T.duration, e.t + 0.35), e.t))
            if e.kind == 'camera' and e.move3d:            # v2.1: 3D camera move: its start and its settle
                end = float(e.move3d.get('end', e.t + float(e.duration or 1)))
                W.append(('camera', f'cam_{e.id}_start', e.t, min(T.duration, e.t + 0.6), None))
                W.append(('camera', f'cam_{e.id}_settle', max(0, end - 0.5), min(T.duration, end + 0.3), None))
        last = T.scenes[-1]; W.append(('reveal', f'reveal_{last.id}', last.start, last.end, None))
    if rep:
        for h in rep['holds']:
            if h['status'] in ('WARN', 'FAIL'):
                W.append(('hold', f"hold_{h['start']:.2f}".replace('.', '_'), max(0, h['start'] - 0.2), min(dur, h['end'] + 0.2), None))
    for m in a.at:
        s0, s1 = [float(x) for x in m.split(':')]; W.append(('manual', f'at_{s0:.2f}'.replace('.', '_'), s0, s1, None))
    lines = ['# Temporal QA previews', '', 'Watch the `_1x` clip first, then the `_half` clip. Use the strip to read spacing frame by frame '
             '(big gaps then small gaps = ease-out). The onion skin shows paths and overlaps.', '',
             '| Window | Type | Time | Measured motion shape | Files |', '|---|---|---|---|---|']
    details = []
    for kind, wid, t0, t1, hit in W:
        frames, fps = extract(a.video, t0, t1)
        if not frames: continue
        base = os.path.join(a.out, wid)
        strip(frames, t0, fps, act, base + '_strip.jpg', f'{wid}  {t0:.2f}-{t1:.2f}s  ({kind})')
        onion(frames, base + '_onion.jpg')
        if not a.no_clips: clips(a.video, t0, t1, base)
        r, lab = signature(act, t0, t1, fps, kind, hit, rep['series']['dmean'] if rep else None)
        lines.append(f'| {wid} | {kind} | {t0:.2f}-{t1:.2f}s | {lab or "n/a"}{(" (>10)" if r and r > 10 else f" ({r})") if r else ""} | {wid}_1x.mp4, {wid}_half.mp4, {wid}_strip.jpg, {wid}_onion.jpg |')
        details.append(f'\n## {wid}\n' + '\n'.join(f'- [ ] {q}' for q in QUESTIONS[kind]))
    lines += details
    lines += ['', '## Record your verdict', 'For each window write: PASS / FIX, and for FIX the change (e.g. "hold 2.8-3.9: add supporting motion: '
              'cards breathe +2% scale, gold wave repeats on the beat at 3.0/3.5").']
    open(os.path.join(a.out, 'index.md'), 'w').write('\n'.join(lines) + '\n')
    print(f'{len(W)} preview windows -> {a.out}/index.md')


if __name__ == '__main__':
    main()
