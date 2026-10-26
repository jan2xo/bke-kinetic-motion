#!/usr/bin/env python3
"""motion_energy.py - measure the motion in a RENDERED video and judge its pacing.

  python3 motion_energy.py out.mp4 --manifest timeline.json --out qa/      # full report
  python3 motion_energy.py frames/ --fps 30 --out qa/                      # PNG frame folder
  python3 motion_energy.py out.mp4 --scenes 0,2,4,6.5,8.5,10 --style kinetic --out qa/

Writes  qa/motion_report.json   machine-readable: per-frame series, scenes, peaks, holds, gaps, checks
        qa/motion_graph.png     energy curve with thresholds, holds, scenes, peaks and declared events
        qa/motion_summary.txt   compact PASS / WARN / FAIL lines (also printed)
Exit code: 0 = PASS or WARN, 2 = FAIL  (--strict: WARN exits 1).

WHAT IS MEASURED (per frame i vs i-1, at a fixed analysis width so resolution does not change the numbers)
  luma     mean |dY| (0..255)                 -> the main "energy" series, scaled to a 30 fps reference
  edge     mean |d gradient magnitude|        -> structural change; a flash moves luma but barely moves edges
  chroma   mean |dCb| + |dCr|                 -> colour change that luma misses (gold lighting up on grey)
  extent   fraction of pixels with |dY| > 12  -> how much of the frame changed (a cut is ~everything)
  local    mean |dY| of the busiest 1/16 x 1/9 block -> a small moving object (cursor, one card) still counts
  grain    Immerkaer noise estimate of the difference image -> the floor that grain alone explains
  dmean    signed change of mean luma         -> flashes and fades
  camera   global (dx, dy) by phase correlation + residual after compensating it
  zoom     (v2.1) global scale about the centre (camera dolly / push-in), searched on a half-size copy;
           counts as camera motion (corner travel in px) and is compensated in the residual
           -> separates camera moves (pan/whip) from choreography inside the frame

LIMITS (read before trusting a number)
  Frame difference is a proxy, not perception. It over-counts grain, flicker and full-frame flashes, and
  under-counts small high-contrast motion (a cursor) and slow zooms. Treat energy as "how much changed",
  not "how good it feels". That is why holds require ALL channels to be quiet, flashes are classified
  separately, and the temporal previews (preview.py) are mandatory for judging easing and rhythm.

THRESHOLDS are relative to a measured noise floor (grain), scaled to fps, and set per style preset;
override any value with --set key=value or a "motion_qa" block in the manifest.
"""
import argparse, glob, json, os, subprocess, sys
import numpy as np

STYLES = {
    # hold_abs: activity below this (30fps-ref, 320px) = nothing alive. floor_mult: hold threshold relative to
    # the grain floor. hold_warn/hold_fail: seconds. gap: max seconds between significant events.
    'kinetic':     dict(hold_abs=0.80, floor_mult=1.6, hold_warn=0.45, hold_fail=0.80, gap_warn=2.5,
                        peak_mult=4.0, peak_abs=6.0, sag_ratio=1.0, end_card_max=2.0, camera_only_warn=1.2),
    'calm':        dict(hold_abs=0.50, floor_mult=1.4, hold_warn=1.2, hold_fail=2.5, gap_warn=5.0,
                        peak_mult=4.0, peak_abs=4.0, sag_ratio=0.7, end_card_max=4.0, camera_only_warn=4.0),
    'documentary': dict(hold_abs=0.40, floor_mult=1.3, hold_warn=3.0, hold_fail=6.0, gap_warn=10.0,
                        peak_mult=5.0, peak_abs=4.0, sag_ratio=0.6, end_card_max=5.0, camera_only_warn=10.0),
}
BASE = dict(analysis_width=320, smooth_frames=5, peak_min_sep=0.2, event_search_frames=3,
            edge_hold_mult=1.8, extent_hold=0.02, flash_dmean=5.0, cut_extent=0.55, camera_px=6.0,
            pop_mult=4.0, noise_floor_pct=10, noise_floor_cap=1.6, local_hold_abs=3.0, local_hold_mult=2.5, rank_margin=0.05, boundary_pad=0.25)


# ------------------------------------------------------------------ decoding
def probe(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=width,height,r_frame_rate', '-of', 'json', path], capture_output=True, text=True)
    s = json.loads(p.stdout)['streams'][0]
    n, d = s['r_frame_rate'].split('/')
    return int(s['width']), int(s['height']), float(n) / float(d)


def read_frames(src, width, fps=None):
    """Yield (H, W, 3) uint8 frames at analysis width. Returns fps, source size via first yield of meta."""
    if os.path.isdir(src) or any(ch in src for ch in '*?'):
        from PIL import Image
        files = sorted(glob.glob(os.path.join(src, '*.png')) if os.path.isdir(src) else glob.glob(src))
        if not files: raise SystemExit(f'no PNG frames in {src}')
        im = Image.open(files[0]); sw, sh = im.size
        h = int(round(sh * width / sw / 2) * 2)
        yield dict(fps=fps or 30.0, src_w=sw, src_h=sh, w=width, h=h, n=len(files))
        for f in files:
            yield np.asarray(Image.open(f).convert('RGB').resize((width, h), Image.BOX))
        return
    sw, sh, vfps = probe(src)
    h = int(round(sh * width / sw / 2) * 2)
    yield dict(fps=fps or vfps, src_w=sw, src_h=sh, w=width, h=h, n=None)
    cmd = ['ffmpeg', '-v', 'error', '-i', src, '-vf', f'scale={width}:{h}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    sz = width * h * 3
    while True:
        b = p.stdout.read(sz)
        if len(b) < sz: break
        yield np.frombuffer(b, np.uint8).reshape(h, width, 3)
    p.stdout.close(); p.wait()


# ------------------------------------------------------------------ per-frame metrics
def ycc(rgb):
    f = rgb.astype(np.float32)
    y = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    cb = 128 - 0.168736 * f[..., 0] - 0.331264 * f[..., 1] + 0.5 * f[..., 2]
    cr = 128 + 0.5 * f[..., 0] - 0.418688 * f[..., 1] - 0.081312 * f[..., 2]
    return y, cb, cr


def gradmag(y):
    gx = np.zeros_like(y); gy = np.zeros_like(y)
    gx[:, 1:-1] = y[:, 2:] - y[:, :-2]; gy[1:-1, :] = y[2:, :] - y[:-2, :]
    return np.sqrt(gx * gx + gy * gy) * 0.5


_WIN = {}
def phase_shift(a, b):
    """Global translation of b relative to a, and a confidence (peak / mean of correlation surface)."""
    h, w = a.shape
    if (h, w) not in _WIN:
        _WIN[(h, w)] = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    win = _WIN[(h, w)]
    A = np.fft.rfft2((a - a.mean()) * win); B = np.fft.rfft2((b - b.mean()) * win)
    Rr = A * np.conj(B); Rr /= np.abs(Rr) + 1e-6
    c = np.fft.irfft2(Rr, s=(h, w))
    k = int(np.argmax(c)); py, px = divmod(k, w)
    conf = float(c.flat[k] / (np.abs(c).mean() + 1e-9))
    dy = py if py <= h // 2 else py - h
    dx = px if px <= w // 2 else px - w
    return -dx, -dy, conf


def _scale_about_centre(img, s):
    """Bilinear resample of img scaled by s about its centre (s > 1 = zoom in)."""
    h, w = img.shape; cy, cx = (h - 1) / 2, (w - 1) / 2
    ys = (np.arange(h, dtype=np.float32) - cy) / s + cy; xs = (np.arange(w, dtype=np.float32) - cx) / s + cx
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 2); x0 = np.clip(np.floor(xs).astype(int), 0, w - 2)
    fy = np.clip(ys - y0, 0, 1)[:, None]; fx = np.clip(xs - x0, 0, 1)[None, :]
    a = img[y0][:, x0]; b = img[y0][:, x0 + 1]; c = img[y0 + 1][:, x0]; d = img[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def zoom_shift(a, b, max_scale=0.06):
    """v2.1: global scale change of b relative to a about the frame centre (a camera dolly / push-in / zoom).
    Coarse search on a 2x2 box-averaged copy, refined at analysis resolution; error measured on the central 70 %.
    Returns (scale, residual, residual_at_scale_1); scale 1.0 when no zoom explains the change."""
    def box(x):
        h, w = (x.shape[0] // 2) * 2, (x.shape[1] // 2) * 2; x = x[:h, :w]
        return (x[0::2, 0::2] + x[1::2, 0::2] + x[0::2, 1::2] + x[1::2, 1::2]) * 0.25
    def mk(A, B):
        h, w = A.shape; my, mx = int(h * 0.15), int(w * 0.15)
        return lambda s: float(np.abs(B[my:h - my, mx:w - mx] - _scale_about_centre(A, s)[my:h - my, mx:w - mx]).mean())
    def soft(x):                      # 3x3 box blur: resampling and grain errors should not hide a real zoom
        y = x.copy(); y[1:-1] = (x[:-2] + x[1:-1] + x[2:]) / 3; z = y.copy(); z[:, 1:-1] = (y[:, :-2] + y[:, 1:-1] + y[:, 2:]) / 3; return z
    a, b = soft(a), soft(b)
    ec = mk(box(a), box(b)); best = min(np.linspace(1 - max_scale, 1 + max_scale, 13), key=lambda s: ec(float(s)))
    ef = mk(a, b); step = 2 * max_scale / 12
    e1 = ef(1.0); s_best, e_best = 1.0, e1
    for s in np.linspace(best - step, best + step, 11):
        e = ef(float(s))
        if e < e_best: s_best, e_best = float(s), e
    return s_best, e_best, e1


def analyse(src, width=320, fps=None):
    it = read_frames(src, width, fps)
    meta = next(it)
    rows = []
    prev = None
    for i, rgb in enumerate(it):
        y, cb, cr = ycc(rgb); g = gradmag(y)
        small = y
        if prev is None:
            rows.append(dict(i=0, luma=0.0, edge=0.0, chroma=0.0, extent=0.0, dmean=0.0, cam_dx=0, cam_dy=0, cam_conf=0.0, residual=0.0,
                             local=0.0, grain=0.0, mean=float(y.mean())))
        else:
            py, pcb, pcr, pg, psmall = prev
            dy_ = np.abs(y - py)
            dx_, dyy, conf = phase_shift(psmall, small)
            sd = y - py
            # grain: Immerkaer noise estimate on the signed difference (white noise survives the Laplacian, smooth motion mostly doesn't)
            lap = (sd[:-2, :-2] - 2 * sd[:-2, 1:-1] + sd[:-2, 2:] - 2 * sd[1:-1, :-2] + 4 * sd[1:-1, 1:-1] - 2 * sd[1:-1, 2:]
                   + sd[2:, :-2] - 2 * sd[2:, 1:-1] + sd[2:, 2:])
            sig_d = float(np.sqrt(np.pi / 2) * np.median(np.abs(lap)) / 6 * 1.4826 / 1.2533)
            grain = sig_d * np.sqrt(2 / np.pi)          # expected mean |dY| if the frame were pure grain
            # local: the busiest 1/16 x 1/9 block, so a small object (cursor, a single card) still counts as motion
            hh, ww = dy_.shape; bh, bw = max(1, hh // 9), max(1, ww // 16)
            blocks = dy_[:bh * 9, :bw * 16].reshape(9, bh, 16, bw).mean(axis=(1, 3))
            local = float(blocks.max())
            if conf > 8 and (dx_ or dyy) and abs(dx_) < y.shape[1] // 2 and abs(dyy) < y.shape[0] // 2:
                sh = np.roll(np.roll(py, dyy, 0), dx_, 1)
                m = np.ones_like(y, bool)
                if dyy > 0: m[:dyy] = False
                elif dyy < 0: m[dyy:] = False
                if dx_ > 0: m[:, :dx_] = False
                elif dx_ < 0: m[:, dx_:] = False
                resid = float(np.abs(y - sh)[m].mean()) if m.any() else float(dy_.mean())
            else:
                resid = float(dy_.mean())
            # v2.1: camera dolly / zoom (pure scale about the centre), which phase correlation cannot see
            zs, zres = 1.0, None
            if dy_.mean() > 0.5:
                s_, e_s, e_1 = zoom_shift(py, y)
                if abs(s_ - 1) >= 0.002 and e_s < 0.8 * e_1:
                    zs, zres = s_, e_s * float(dy_.mean()) / max(e_1, 1e-6)   # rescale central-crop error to full-frame units
            if zres is not None and zres < resid: resid = zres
            rows.append(dict(cam_zoom=round(zs, 4), i=i, luma=float(dy_.mean()), edge=float(np.abs(g - pg).mean()),
                             chroma=float(np.abs(cb - pcb).mean() + np.abs(cr - pcr).mean()),
                             extent=float((dy_ > 12).mean()), dmean=float(y.mean() - py.mean()),
                             cam_dx=int(dx_), cam_dy=int(dyy), cam_conf=round(conf, 1), residual=resid, local=local, grain=grain,
                             mean=float(y.mean())))
        prev = (y, cb, cr, g, small)
    meta['n'] = len(rows)
    return meta, rows


# ------------------------------------------------------------------ judgement
def runs(mask, min_len):
    out = []; st = None
    for i, m in enumerate(list(mask) + [False]):
        if m and st is None: st = i
        if not m and st is not None:
            if i - st >= min_len: out.append((st, i))
            st = None
    return out


def medfilt(x, k):
    if k <= 1: return x.copy()
    p = k // 2; xp = np.pad(x, p, mode='edge')
    return np.array([np.median(xp[i:i + k]) for i in range(len(x))])


def judge(meta, rows, cfg, manifest=None, scenes=None):
    fps = meta['fps']; n = len(rows)
    ref = fps / 30.0                       # diff per frame shrinks at higher fps: normalise to 30 fps
    L = np.array([r['luma'] for r in rows]) * ref
    E = np.array([r['edge'] for r in rows]) * ref
    C = np.array([r['chroma'] for r in rows]) * ref
    X = np.array([r['extent'] for r in rows])
    DM = np.array([r['dmean'] for r in rows])
    RES = np.array([r['residual'] for r in rows]) * ref
    CAM = np.array([np.hypot(r['cam_dx'], r['cam_dy']) for r in rows]) * ref
    # v2.1: a dolly/zoom counts as camera motion: |scale - 1| x half-diagonal = pixels the frame corners travel
    hd = 0.5 * float(np.hypot(meta['w'], meta['h']))
    ZPX = np.array([abs(r.get('cam_zoom', 1.0) - 1) * hd for r in rows]) * ref
    CAM = np.maximum(CAM, ZPX)
    t = np.arange(n) / fps
    LOC = np.array([r.get('local', 0.0) for r in rows]) * ref
    G = np.array([r.get('grain', 0.0) for r in rows]) * ref      # same units as activity (scaled to 30 fps)
    act = L + 0.5 * C                      # activity: luma plus colour-only change
    body = act[1:] if n > 1 else act
    # noise floor: the quietest frames, but never above what grain alone explains (when everything moves, the
    # quietest frames are still motion). Grain is estimated per frame from the difference image itself.
    gfloor = float(np.median(G[1:])) * 1.5 if n > 1 else 0.0      # x1.5 covers the chroma share of activity
    pfloor = float(np.percentile(body, cfg['noise_floor_pct']))
    floor = float(min(pfloor, max(gfloor, 0.05), cfg['noise_floor_cap']))
    efloor = float(min(np.percentile(E[1:] if n > 1 else E, cfg['noise_floor_pct']), max(gfloor, 0.05) * 1.2, cfg['noise_floor_cap']))
    hold_thr = max(cfg['hold_abs'], floor * cfg['floor_mult'])
    edge_thr = max(cfg['hold_abs'] * 0.8, efloor * cfg['edge_hold_mult'])
    loc_thr = max(cfg['local_hold_abs'], float(np.median(G[1:])) * cfg['local_hold_mult'] if n > 1 else 0)
    sm = medfilt(act, cfg['smooth_frames']); sme = medfilt(E, cfg['smooth_frames'])
    quiet = ((sm < hold_thr) & (sme < edge_thr) & (medfilt(X, cfg['smooth_frames']) < cfg['extent_hold'])
             & (medfilt(LOC, cfg['smooth_frames']) < loc_thr))
    quiet[0] = quiet[1] if n > 1 else quiet[0]

    checks = []
    def chk(level, code, msg, **kw):
        checks.append(dict(level=level, code=code, message=msg, **kw))

    mq = manifest
    declared_quiet = [(q['start'], q['end'], q.get('reason', '')) for q in (mq.data.get('quiet', []) if mq else [])]
    ranked = sorted([e for e in mq.events() if e.rank is not None], key=lambda e: e.t) if mq else []
    last_impact = max([e.t for e in ranked], default=None)

    # ---- peaks
    w1 = max(3, int(fps))
    roll = np.array([np.median(act[max(0, i - w1 // 2): i + w1 // 2 + 1]) for i in range(n)])
    peak_thr = np.maximum(cfg['peak_abs'], roll * cfg['peak_mult'])
    cand = [i for i in range(1, n) if act[i] >= peak_thr[i] and act[i] >= act[max(0, i - 1)] and act[i] >= (act[i + 1] if i + 1 < n else 0)]
    peaks = []
    sep = int(cfg['peak_min_sep'] * fps)
    for i in sorted(cand, key=lambda i: -act[i]):
        if all(abs(i - p) > sep for p in peaks): peaks.append(i)
    peaks.sort()
    def classify(i):
        if abs(DM[i]) >= cfg['flash_dmean'] and X[i] > 0.4: return 'flash'
        if X[i] >= cfg['cut_extent'] and E[i] > 3 * max(efloor, 0.1): return 'cut'
        if CAM[i] >= cfg['camera_px'] and RES[i] < 0.6 * L[i]: return 'camera'
        return 'content'
    peak_list = [dict(t=round(i / fps, 3), frame=i, energy=round(float(act[i]), 2), kind=classify(i)) for i in peaks]
    for r, p in enumerate(sorted(peak_list, key=lambda p: -p['energy'])):
        p['rank'] = r + 1

    # ---- holds
    min_len = max(2, int(round(cfg['hold_warn'] * fps * 0.6)))
    holds = []
    for a, b in runs(quiet, min_len):
        s0, s1 = a / fps, b / fps; dur = s1 - s0
        cover = max([max(0, min(s1, qe) - max(s0, qs)) for qs, qe, _ in declared_quiet], default=0)
        reason = None
        if dur > 0 and cover / dur >= 0.8:
            status = 'INTENTIONAL'; reason = 'declared quiet: ' + next(r for qs, qe, r in declared_quiet if min(s1, qe) - max(s0, qs) > 0)
        elif b >= n - 1 and dur <= cfg['end_card_max'] and (last_impact is None or s0 >= last_impact):
            status = 'INTENTIONAL'; reason = 'end-card hold after the final impact'
        elif dur >= cfg['hold_fail']: status = 'FAIL'
        elif dur >= cfg['hold_warn']: status = 'WARN'
        else: continue
        mean_act = float(act[a:b].mean())
        holds.append(dict(start=round(s0, 3), end=round(s1, 3), duration=round(dur, 3), mean_activity=round(mean_act, 2),
                          status=status, reason=reason))
        if status == 'INTENTIONAL':
            chk('PASS', 'hold', f'stillness {s0:.2f}-{s1:.2f}s ({dur:.2f}s) accepted: {reason}', start=s0, end=s1)
        else:
            chk(status, 'hold', f'low-motion hold {s0:.2f}-{s1:.2f}s ({dur:.2f}s, activity {mean_act:.2f} < {hold_thr:.2f}) not declared as quiet', start=s0, end=s1)

    # ---- camera-only stretches (motion exists but it is all camera, no choreography)
    camonly = (CAM >= 1.0 * ref) & (RES < np.maximum(hold_thr, 0.5 * L)) & (sm >= hold_thr)
    for a, b in runs(camonly, int(cfg['camera_only_warn'] * fps)):
        chk('WARN', 'camera_only', f'{a / fps:.2f}-{b / fps:.2f}s: movement is camera-only (no element moves within the frame)', start=a / fps, end=b / fps)

    # ---- scenes
    sc = []
    if mq and mq.scenes: sc = [(s.id, s.start, s.end, s.energy) for s in mq.scenes]
    elif scenes:
        sc = [(f's{k + 1}', scenes[k], scenes[k + 1], None) for k in range(len(scenes) - 1)]
    else:
        cuts = [0.0] + [p['t'] for p in peak_list if p['kind'] in ('cut', 'flash')] + [n / fps]
        cuts = sorted(set(round(c, 3) for c in cuts))
        sc = [(f's{k + 1}', cuts[k], cuts[k + 1], None) for k in range(len(cuts) - 1) if cuts[k + 1] - cuts[k] > 0.2]
    pad = cfg['boundary_pad']
    scene_stats = []
    for sid, s0, s1, lvl in sc:
        a, b = int(round(s0 * fps)), int(round(s1 * fps))
        ab, bb = int(round((s0 + pad) * fps)), int(round((s1 - pad) * fps))
        seg = act[a:b]; bseg = act[ab:bb] if bb - ab >= 3 else seg
        wins = []
        for w0 in np.arange(s0, s1 - 1e-6, 0.5):
            i0, i1 = int(round(w0 * fps)), int(round(min(w0 + 0.5, s1) * fps))
            if i1 > i0: wins.append(dict(start=round(float(w0), 2), end=round(float(min(w0 + 0.5, s1)), 2), mean=round(float(act[i0:i1].mean()), 2)))
        scene_stats.append(dict(id=sid, start=s0, end=s1, target=lvl, mean=round(float(seg.mean()), 3), body_mean=round(float(bseg.mean()), 3),
                                median=round(float(np.median(seg)), 3), p90=round(float(np.percentile(seg, 90)), 3), max=round(float(seg.max()), 3),
                                hold_frac=round(float(quiet[a:b].mean()), 3), windows=wins))

    # ---- energy targets: ordering and sag
    lv = {'rest': 0, 'low': 1, 'medium': 2, 'high': 3}
    tgt = [s for s in scene_stats if s['target'] in lv]
    for x in tgt:
        for y in tgt:
            if lv[x['target']] > lv[y['target']] and x['body_mean'] < y['body_mean']:
                chk('WARN', 'energy_order', f"scene {x['id']} is planned {x['target']} but its body energy {x['body_mean']:.2f} is below "
                    f"{y['id']} ({y['target']}, {y['body_mean']:.2f})", scene=x['id'])
    def inner_windows(s):
        return [w for w in s['windows'] if w['start'] >= s['start'] + pad - 1e-6 and w['end'] <= s['end'] - pad + 1e-6]
    # reference = the typical inner half-second of the scenes planned one level lower (medium for high)
    med_ref = [w['mean'] for s in tgt if s['target'] == 'medium' for w in inner_windows(s)]
    for s in tgt:
        if s['target'] != 'high': continue
        ref_v = float(np.median(med_ref)) if med_ref else s['median']
        for w in inner_windows(s):
            if w['mean'] < cfg['sag_ratio'] * ref_v:
                chk('WARN', 'energy_sag', f"scene {s['id']} (planned high) sags {w['start']:.1f}-{w['end']:.1f}s: {w['mean']:.2f} vs "
                    f"{cfg['sag_ratio']:.2f} x medium reference {ref_v:.2f}", scene=s['id'], start=w['start'], end=w['end'])

    # ---- declared impacts: present and in rank order
    k = cfg['event_search_frames']
    meas = []
    for e in ranked:
        fi = int(round(e.t * fps)); lo, hi = max(0, fi - k), min(n, fi + k + 1)
        j = lo + int(np.argmax(act[lo:hi])); v = float(act[j])
        is_peak = any(abs(p['frame'] - j) <= 1 for p in peak_list)
        meas.append(dict(id=e.id, rank=e.rank, t=e.t, measured_t=round(j / fps, 3), offset_frames=j - fi, energy=round(v, 2), is_peak=is_peak))
        if not is_peak:
            chk('FAIL', 'impact_missing', f'declared impact {e.id!r} at {e.t:.2f}s has no motion peak within +-{k} frames (max {v:.2f})', event=e.id)
        elif abs(j - fi) > 1:
            chk('WARN', 'impact_offset', f'impact {e.id!r} peaks {j - fi:+d} frames from its declared time', event=e.id)
    if meas:
        bad = []
        for x in meas:
            for y in meas:
                if x['rank'] < y['rank'] and x['energy'] < y['energy'] * (1 + cfg['rank_margin']):
                    bad.append((x['id'], y['id']))
        if bad:
            chk('WARN', 'impact_rank', 'measured hit size disagrees with narrative rank: ' +
                ', '.join(f'{a} should exceed {b}' for a, b in bad))
        else:
            chk('PASS', 'impact_rank', 'hit sizes follow narrative rank: ' + ' > '.join(f"{m['id']}({m['energy']})" for m in sorted(meas, key=lambda m: m['rank'])))

    # ---- pacing gaps between significant peaks (ignoring declared quiet)
    sig = [0.0] + [p['t'] for p in peak_list] + [n / fps]
    for a_, b_ in zip(sig, sig[1:]):
        if b_ - a_ > cfg['gap_warn']:
            if any(qs <= a_ + 0.1 and qe >= b_ - 0.1 for qs, qe, _ in declared_quiet): continue
            if b_ >= n / fps - 1e-6 and last_impact is not None and a_ >= last_impact - 0.05: continue
            chk('WARN', 'pacing_gap', f'{b_ - a_:.2f}s between significant motion events ({a_:.2f}-{b_:.2f}s)', start=a_, end=b_)

    # ---- unexplained single-frame discontinuities (pops)
    expl = [e.t for e in mq.events()] if mq else []
    for i in range(2, n - 2):
        nb = np.median(np.r_[act[max(0, i - 3):i], act[i + 1:i + 4]])
        if act[i] > cfg['pop_mult'] * max(nb, floor) and act[i] > cfg['peak_abs'] and act[i + 1] < act[i] * 0.4:
            near_e = any(abs(i / fps - et) <= 3 / fps for et in expl)
            near_cut = any(abs(i / fps - s[1]) <= 3 / fps for s in sc)
            if not (near_e or near_cut):
                chk('WARN', 'pop', f'single-frame spike at {i / fps:.2f}s (energy {act[i]:.1f}) with no declared event: possible jump/glitch', t=i / fps)

    if not any(c['code'] == 'hold' and c['level'] != 'PASS' for c in checks):
        chk('PASS', 'holds', f'no undeclared hold >= {cfg["hold_warn"]:.2f}s')

    series = dict(t=[round(float(x), 4) for x in t], activity=[round(float(x), 3) for x in act], luma=[round(float(x), 3) for x in L],
                  edge=[round(float(x), 3) for x in E], chroma=[round(float(x), 3) for x in C], extent=[round(float(x), 4) for x in X],
                  dmean=[round(float(x), 2) for x in DM], camera_px=[round(float(x), 2) for x in CAM], zoom=[r.get('cam_zoom', 1.0) for r in rows], residual=[round(float(x), 3) for x in RES], local=[round(float(x), 2) for x in LOC],
                  smoothed=[round(float(x), 3) for x in sm], quiet=[bool(x) for x in quiet])
    nf = sum(c['level'] == 'FAIL' for c in checks); nw = sum(c['level'] == 'WARN' for c in checks)
    result = 'FAIL' if nf else ('WARN' if nw else 'PASS')
    return dict(tool='bke-kinetic-motion/motion_energy', version='2.1.0', result=result, fails=int(nf), warns=int(nw),
                meta=meta, config=cfg, thresholds=dict(noise_floor=round(floor, 3), grain_floor=round(gfloor, 3), hold=round(hold_thr, 3), edge_hold=round(edge_thr, 3), local_hold=round(loc_thr, 3)),
                peaks=peak_list, holds=holds, scenes=scene_stats, impacts=meas, checks=checks, series=series,
                caveat='Frame difference approximates "how much changed", not perceived quality. Confirm easing and rhythm with preview.py.')


# ------------------------------------------------------------------ outputs
def summary_text(rep, name):
    m = rep['meta']
    L = [f"MOTION QA  {name}  {m['n'] / m['fps']:.2f}s @ {m['fps']:g}fps  src {m['src_w']}x{m['src_h']}  analysis {m['w']}px  "
         f"floor {rep['thresholds']['noise_floor']:.2f}  hold<{rep['thresholds']['hold']:.2f}"]
    top = sorted(rep['peaks'], key=lambda p: -p['energy'])[:5]
    L.append('INFO  top peaks: ' + ', '.join(f"{p['t']:.2f}s {p['energy']:.0f} ({p['kind']})" for p in top))
    L.append('INFO  scenes: ' + ', '.join(f"{s['id']} {s['body_mean']:.2f}" + (f"[{s['target']}]" if s['target'] else '') for s in rep['scenes']))
    order = {'FAIL': 0, 'WARN': 1, 'PASS': 2}
    for c in sorted(rep['checks'], key=lambda c: order[c['level']]):
        L.append(f"{c['level']:4s}  [{c['code']}] {c['message']}")
    L.append(f"RESULT: {rep['result']} ({rep['fails']} fail, {rep['warns']} warn)")
    return '\n'.join(L)


def graph(rep, path, manifest=None, title=''):
    from PIL import Image, ImageDraw, ImageFont
    s = rep['series']; t = np.array(s['t']); a = np.array(s['activity']); sm = np.array(s['smoothed']); ed = np.array(s['edge'])
    W, H = 1800, 760; ml, mr, mt, mb = 80, 30, 70, 170
    im = Image.new('RGB', (W, H), (12, 13, 16)); d = ImageDraw.Draw(im)
    fd = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts')
    try:
        F = ImageFont.truetype(os.path.join(fd, 'Montserrat-Medium.ttf'), 15); FB = ImageFont.truetype(os.path.join(fd, 'Montserrat-Bold.ttf'), 20)
    except Exception:
        F = FB = ImageFont.load_default()
    dur = t[-1] + (t[1] - t[0] if len(t) > 1 else 0.033)
    ymax = max(5.0, float(a.max()) * 1.05)
    def X(x): return ml + (W - ml - mr) * x / dur
    def Y(v): return H - mb - (H - mt - mb) * np.sqrt(max(0.0, min(v, ymax)) / ymax)   # sqrt axis: holds stay visible next to big hits
    # scenes
    cols = [(24, 26, 32), (18, 20, 25)]
    for k, sc in enumerate(rep['scenes']):
        d.rectangle([X(sc['start']), mt, X(sc['end']), H - mb], fill=cols[k % 2])
        d.text((X(sc['start']) + 6, mt + 4), f"{sc['id']} {sc['body_mean']:.2f}" + (f" [{sc['target']}]" if sc['target'] else ''), font=F, fill=(150, 154, 162))
    # holds
    hc = {'FAIL': (120, 30, 36), 'WARN': (120, 90, 20), 'INTENTIONAL': (24, 80, 52)}
    for h in rep['holds']:
        d.rectangle([X(h['start']), mt + 24, X(h['end']), H - mb], fill=hc[h['status']])
        d.text((X(h['start']) + 4, H - mb - 22), h['status'].lower(), font=F, fill=(235, 235, 235))
    # grid
    for v in [x for x in (0, 1, 2, 5, 10, 20, 50, 100, 200, 500) if x <= ymax]:
        d.line([ml, Y(v), W - mr, Y(v)], fill=(34, 36, 42)); d.text((10, Y(v) - 8), f'{v:g}', font=F, fill=(110, 114, 122))
    for sec in range(int(dur) + 1):
        d.line([X(sec), H - mb, X(sec), H - mb + 6], fill=(110, 114, 122)); d.text((X(sec) - 6, H - mb + 8), f'{sec}s', font=F, fill=(150, 154, 162))
    # thresholds
    th = rep['thresholds']['hold']
    d.line([ml, Y(th), W - mr, Y(th)], fill=(220, 90, 90), width=1); d.text((ml + 6, Y(th) + 2), f'hold < {th:.2f}', font=F, fill=(220, 90, 90))
    # curves
    pts = [(X(x), Y(v)) for x, v in zip(t, ed)]; d.line(pts, fill=(70, 120, 170), width=1)
    pts = [(X(x), Y(v)) for x, v in zip(t, a)]; d.line(pts, fill=(255, 194, 40), width=2)
    pts = [(X(x), Y(v)) for x, v in zip(t, sm)]; d.line(pts, fill=(244, 245, 247), width=1)
    # peaks
    for p in rep['peaks'][:]:
        if p['rank'] > 8: continue
        x, y = X(p['t']), Y(p['energy'])
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 255, 255), width=2)
        d.text((x + 7, max(mt + 26, y - 20)), f"#{p['rank']} {p['energy']:.0f} {p['kind']}", font=F, fill=(255, 255, 255))
    # declared events strip
    if manifest:
        yb = H - mb + 40
        d.text((10, yb), 'events', font=F, fill=(150, 154, 162))
        for k, e in enumerate(manifest.events()):
            x = X(e.t); c = (255, 194, 40) if e.rank else ((120, 200, 255) if e.kind in ('accent', 'transition') else (170, 174, 182))
            d.polygon([(x - 5, yb + 2), (x + 5, yb + 2), (x, yb + 12)], fill=c)
            d.text((x - 10, yb + 16 + (k % 5) * 16), str(e.id)[:16], font=F, fill=c)
    d.text((ml, 18), title or 'motion energy', font=FB, fill=(244, 245, 247))
    d.text((ml + 520, 22), 'gold = activity (luma + 0.5 chroma)   white = smoothed   blue = edge change   shaded = holds   y axis = sqrt', font=F, fill=(150, 154, 162))
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('--manifest'); ap.add_argument('--scenes', help='comma list of scene boundaries incl. 0 and end')
    ap.add_argument('--fps', type=float); ap.add_argument('--style', default=None, choices=list(STYLES))
    ap.add_argument('--set', action='append', default=[], help='override a threshold, e.g. --set hold_fail=1.0')
    ap.add_argument('--out', default='qa'); ap.add_argument('--name'); ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import timeline as TL
    mq = TL.load(a.manifest) if a.manifest else None
    style = a.style or ((mq.data.get('motion_qa') or {}).get('style') if mq else None) or 'kinetic'
    cfg = dict(BASE); cfg.update(STYLES[style]); cfg['style'] = style
    if mq: cfg.update({k: v for k, v in (mq.data.get('motion_qa') or {}).items() if k != 'style'})
    for kv in a.set:
        k, v = kv.split('='); cfg[k] = type(cfg.get(k, 1.0))(v)
    meta, rows = analyse(a.src, cfg['analysis_width'], a.fps or (mq.fps if mq and os.path.isdir(a.src) else None))
    scenes = [float(x) for x in a.scenes.split(',')] if a.scenes else None
    rep = judge(meta, rows, cfg, mq, scenes)
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.basename(a.src.rstrip('/'))
    rep['source'] = name
    with open(os.path.join(a.out, 'motion_report.json'), 'w') as f: json.dump(rep, f, indent=1)
    graph(rep, os.path.join(a.out, 'motion_graph.png'), mq, f'Motion energy - {name}')
    txt = summary_text(rep, name)
    with open(os.path.join(a.out, 'motion_summary.txt'), 'w') as f: f.write(txt + '\n')
    print(txt)
    sys.exit(2 if rep['result'] == 'FAIL' else (1 if a.strict and rep['result'] == 'WARN' else 0))


if __name__ == '__main__':
    main()
