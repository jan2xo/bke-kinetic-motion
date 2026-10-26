#!/usr/bin/env python3
"""sync_check.py - audio/visual synchronisation against the shared manifest.

Two levels of evidence, never mixed:

  DECLARED  - the manifest vs what the code says it scheduled.
              Inputs: timeline.json + the audio cue log the music code wrote (+ optional visual log).
              Proves the PLAN and the CODE agree. Does not prove the rendered file plays in sync.
  VERIFIED  - the manifest vs what is measurable in the rendered MP4.
              Audio onsets come from spectral flux of the decoded soundtrack; visual hits come from
              motion_energy peaks. Only events that stand out in both are counted as verified;
              the rest are reported as "not measurable", not as passes.

  python3 sync_check.py timeline.json --audio-log cues.json                       # declared only
  python3 sync_check.py timeline.json --audio-log cues.json --video out.mp4 \\
                        --motion qa/motion_report.json --out qa/                   # declared + verified
Exit 2 on any FAIL (--strict: WARN exits 1).

Audio cue log format (written by music_synth.py --cue-log, or by any audio code):
  [{"t": 2.0, "cue": "impact", "gain": 0.9, "event_id": "reveal"}, {"t": 2.0, "cue": "kick"}, ...]
  event_id is optional; without it, cues are matched to events by cue name and nearest time.
Visual log format (optional, written by the renderer): [{"event_id": "reveal", "t": 2.0}, ...]

Checks
  missing_sfx     required event with no matching sound              FAIL
  drift           matched, but |offset| > tolerance                  FAIL (WARN when within 2x tol on VERIFIED)
  orphan_audio    a non-bed sound no event accounts for              FAIL
  unrendered      manifest event absent from the visual log          FAIL  (only with --visual-log)
  undeclared      visual-log event not in the manifest               WARN
  overlap         two transient cues < 60 ms apart (masking), double triggers, overlapping hit windows   WARN
  drift_trend     offsets grow over time (|slope x duration| > tol)  WARN
"""
import argparse, json, os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as TL

SWELL = {'whoosh', 'riser', 'swell', 'reverse', 'sweep'}
TRANSIENT = {'impact', 'glitch', 'tick', 'whoosh', 'hit', 'click', 'snap', 'boom', 'clap', 'kick'}


def declared(T, cues, vlog=None):
    out = []; matches = []
    def add(level, code, msg, **kw): out.append(dict(level=level, code=code, message=msg, **kw))
    used = set()
    evs = [e for e in T.events() if (e.sync or 'required') in ('required', 'audio_only') and e.audio]
    # match: explicit event_id first, then nearest same-cue entry (greedy by distance)
    pairs = []
    for e in evs:
        for k, c in enumerate(cues):
            if c.get('event_id') == e.id: pairs.append((0.0, e.id, k))
    for e in evs:
        for k, c in enumerate(cues):
            if c.get('event_id') in (None, '') and c.get('cue') == e.audio:
                pairs.append((abs(c['t'] - e.audio_time), e.id, k))
    pairs.sort(key=lambda p: p[0])
    got = {}
    for dist, eid, k in pairs:
        if eid in got or k in used: continue
        e = T.event(eid)
        if dist > max(3 * e.tol, 0.15) and cues[k].get('event_id') != eid: continue
        got[eid] = k; used.add(k)
    for e in evs:
        if e.id not in got:
            near = [c for c in cues if c.get('cue') == e.audio]
            nearest = min(near, key=lambda c: abs(c['t'] - e.audio_time)) if near else None
            hint = f" (nearest {e.audio} at {nearest['t']:.3f}s, {1000 * (nearest['t'] - e.audio_time):+.0f} ms)" if nearest else ''
            add('FAIL', 'missing_sfx', f"{e.id} @ {e.t:.2f}s expects '{e.audio}' at {e.audio_time:.3f}s; none scheduled{hint}", event=e.id)
            continue
        c = cues[got[e.id]]; off = c['t'] - e.audio_time
        matches.append(dict(event=e.id, t=e.t, expected=round(e.audio_time, 4), scheduled=c['t'], offset_ms=round(off * 1000, 1)))
        if abs(off) > e.tol + 1e-9:
            add('FAIL', 'drift', f"{e.id}: '{e.audio}' scheduled {off * 1000:+.0f} ms from its event (tolerance {e.tol * 1000:.0f} ms)", event=e.id)
        else:
            add('PASS', 'synced', f"{e.id} @ {e.t:.2f}s <- '{e.audio}' {off * 1000:+.0f} ms", event=e.id)
    # visual-only events must not have sounds claiming them
    for e in T.events(sync='visual_only'):
        for c in cues:
            if c.get('event_id') == e.id:
                add('WARN', 'visual_only_has_audio', f'{e.id} is declared visual_only but a {c["cue"]} cue claims it', event=e.id)
    # orphans
    for k, c in enumerate(cues):
        if k in used or c.get('cue') in T.audio_bed: continue
        add('FAIL', 'orphan_audio', f"'{c.get('cue')}' at {c['t']:.3f}s has no visual event in the manifest", t=c['t'])
    # double triggers / masking among transient non-bed cues
    tr = sorted([c for c in cues if c.get('cue') in TRANSIENT and c.get('cue') not in T.audio_bed], key=lambda c: c['t'])
    for a, b in zip(tr, tr[1:]):
        if b['t'] - a['t'] < 0.06:
            same = a.get('cue') == b.get('cue')
            add('WARN', 'overlap', f"{'double trigger' if same else 'masking'}: '{a['cue']}' {a['t']:.3f}s and '{b['cue']}' {b['t']:.3f}s are "
                f"{1000 * (b['t'] - a['t']):.0f} ms apart", t=a['t'])
    hits = [e for e in T.events() if e.kind in ('impact', 'transition') and e.duration]
    for i, a in enumerate(hits):
        for b in hits[i + 1:]:
            if a.t < b.t + b.duration and b.t < a.t + a.duration:
                add('WARN', 'overlap', f'hit windows overlap: {a.id} [{a.t}, {a.t + a.duration}] and {b.id} [{b.t}, {b.t + b.duration}]')
    # trend
    if len(matches) >= 3:
        x = np.array([m['t'] for m in matches]); y = np.array([m['offset_ms'] for m in matches]) / 1000
        slope = np.polyfit(x, y, 1)[0]
        if abs(slope * T.duration) > T.tolerance:
            add('WARN', 'drift_trend', f'offsets drift {slope * 1000:+.1f} ms per second (sample-rate or fps mismatch?)')
    # visual log
    if vlog is not None:
        vid = {v['event_id']: v for v in vlog}
        for e in T.events():
            if (e.sync or 'required') == 'audio_only': continue
            if e.id not in vid:
                add('FAIL', 'unrendered', f'{e.id} is in the manifest but the renderer did not log it', event=e.id)
            elif abs(vid[e.id]['t'] - e.t) > e.tol + 1e-9:
                add('FAIL', 'drift', f"{e.id}: renderer placed it {1000 * (vid[e.id]['t'] - e.t):+.0f} ms from the manifest", event=e.id)
        for k in vid:
            try: T.event(k)
            except KeyError: add('WARN', 'undeclared', f'renderer logged {k!r}, which the manifest does not declare')
    return out, matches


# ------------------------------------------------------------------ verified (rendered output)
def audio_onsets(video, sr=16000, hop=64, win=512):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True)
    x = np.frombuffer(p.stdout, np.float32)
    if len(x) < win: return None, None
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    S = np.abs(np.fft.rfft(x[idx] * np.hanning(win)[None, :], axis=1))
    S = np.log1p(S * 10)
    flux = np.maximum(S[1:] - S[:-1], 0).sum(1)
    flux = np.r_[0, flux]
    t = (np.arange(n) * hop + win / 2) / sr
    return t, flux


def verified(T, video, motion, search=0.08, salience_min=2.5):
    out, rows = [], []
    def add(level, code, msg, **kw): out.append(dict(level=level, code=code, message=msg, **kw))
    at, fl = audio_onsets(video)
    act = np.array(motion['series']['activity']) if motion else None
    fps = motion['meta']['fps'] if motion else T.fps
    for e in T.events():
        if (e.sync or 'required') != 'required' or not e.audio: continue
        r = dict(event=e.id, t=e.t, kind=e.kind, expected_audio=round(e.audio_time, 3))
        # audio
        if at is not None:
            if e.audio in SWELL:
                r.update(audio_note=f"'{e.audio}' is a swell; onset timing is not meaningful")
            else:
                ctx = (at >= e.audio_time - 1) & (at <= e.audio_time + 1)
                med = np.median(fl[ctx]) + 1e-9
                m = np.where((at >= e.audio_time - search) & (at <= e.audio_time + search))[0]
                # nearest salient local maximum, falling back to the strongest one in the window
                loc = [j for j in m if 0 < j < len(fl) - 1 and fl[j] >= fl[j - 1] and fl[j] >= fl[j + 1] and fl[j] / med >= salience_min]
                if m.size:
                    j = min(loc, key=lambda j: abs(at[j] - e.audio_time)) if loc else m[np.argmax(fl[m])]
                    r.update(audio_onset=round(float(at[j]), 3), audio_salience=round(float(fl[j] / med), 2))
        # visual
        if act is not None:
            fi = int(round(e.t * fps)); lo, hi = max(1, fi - 3), min(len(act) - 1, fi + 4)
            med = np.median(act[max(0, fi - int(fps)):fi + int(fps)]) + 1e-9
            loc = [j for j in range(lo, hi) if act[j] >= act[j - 1] and act[j] >= act[j + 1] and act[j] / med >= salience_min]
            j = min(loc, key=lambda j: abs(j - fi)) if loc else lo + int(np.argmax(act[lo:hi]))
            r.update(visual_peak=round(j / fps, 3), visual_salience=round(float(act[j] / med), 2))
        if e.audio in SWELL:
            r['status'] = 'not_measurable'
            add('INFO', 'not_measurable', f"{e.id} @ {e.t:.2f}s: '{e.audio}' is a swell, so its timing can't be measured from onsets", event=e.id)
            rows.append(r); continue
        a_ok = r.get('audio_salience', 0) >= salience_min
        v_ok = r.get('visual_salience', 0) >= salience_min
        if a_ok and v_ok:
            av = r['audio_onset'] - r['visual_peak']; exp = e.audio_time - e.t
            r['av_offset_ms'] = round(av * 1000, 1); r['expected_offset_ms'] = round(exp * 1000, 1)
            err = av - exp; tol = max(e.tol, 1.0 / fps + 0.004)
            if abs(err) <= tol:
                r['status'] = 'verified'; add('PASS', 'verified', f'{e.id}: sound {av * 1000:+.0f} ms vs picture (expected {exp * 1000:+.0f})', event=e.id)
            elif abs(err) <= 2 * tol:
                r['status'] = 'drift'; add('WARN', 'drift', f'{e.id}: measured A/V offset {av * 1000:+.0f} ms, expected {exp * 1000:+.0f} ms', event=e.id)
            else:
                r['status'] = 'drift'; add('FAIL', 'drift', f'{e.id}: measured A/V offset {av * 1000:+.0f} ms, expected {exp * 1000:+.0f} ms', event=e.id)
        else:
            why = []
            if not a_ok: why.append(f"audio onset not distinct (salience {r.get('audio_salience', 0):.1f})")
            if not v_ok: why.append(f"visual change not distinct (salience {r.get('visual_salience', 0):.1f})")
            r['status'] = 'not_measurable'
            add('INFO', 'not_measurable', f"{e.id} @ {e.t:.2f}s: " + '; '.join(why), event=e.id)
        rows.append(r)
    return out, rows


def summarize(dec, ver, name):
    L = [f'SYNC QA  {name}']
    order = {'FAIL': 0, 'WARN': 1, 'INFO': 2, 'PASS': 3}
    L.append('-- DECLARED (manifest vs scheduled cues; proves plan and code agree)')
    for c in sorted(dec, key=lambda c: order[c['level']]): L.append(f"{c['level']:4s}  [{c['code']}] {c['message']}")
    if ver is not None:
        L.append('-- VERIFIED (manifest vs rendered MP4; only distinct events count)')
        for c in sorted(ver, key=lambda c: order[c['level']]): L.append(f"{c['level']:4s}  [{c['code']}] {c['message']}")
    allc = dec + (ver or [])
    nf = sum(c['level'] == 'FAIL' for c in allc); nw = sum(c['level'] == 'WARN' for c in allc)
    nv = sum(c['code'] == 'verified' for c in (ver or [])); nn = sum(c['code'] == 'not_measurable' for c in (ver or []))
    res = 'FAIL' if nf else ('WARN' if nw else 'PASS')
    tail = f'RESULT: {res} ({nf} fail, {nw} warn)'
    if ver is not None: tail += f'  verified in render: {nv}, not measurable: {nn}'
    L.append(tail)
    return '\n'.join(L), res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('manifest'); ap.add_argument('--audio-log'); ap.add_argument('--visual-log')
    ap.add_argument('--video'); ap.add_argument('--motion', help='motion_report.json for the same video')
    ap.add_argument('--out', default=None); ap.add_argument('--name', default=None); ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    T = TL.load(a.manifest)
    cues = json.load(open(a.audio_log)) if a.audio_log else []
    vlog = json.load(open(a.visual_log)) if a.visual_log else None
    dec, matches = declared(T, cues, vlog) if a.audio_log else ([dict(level='WARN', code='no_audio_log', message='no audio cue log: declared sync not checked')], [])
    ver = rows = None
    if a.video:
        motion = json.load(open(a.motion)) if a.motion else None
        ver, rows = verified(T, a.video, motion)
    name = a.name or os.path.basename(a.manifest)
    txt, res = summarize(dec, ver, name)
    print(txt)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        json.dump(dict(tool='bke-kinetic-motion/sync_check', version='2.1.0', result=res, declared=dict(checks=dec, matches=matches),
                       verified=None if ver is None else dict(checks=ver, events=rows),
                       note='DECLARED proves the manifest and the scheduled cues agree. VERIFIED measures the rendered file; '
                            '"not_measurable" means the event did not stand out enough to time, which is not a pass.'),
                  open(os.path.join(a.out, 'sync_report.json'), 'w'), indent=1)
        open(os.path.join(a.out, 'sync_summary.txt'), 'w').write(txt + '\n')
    sys.exit(2 if res == 'FAIL' else (1 if a.strict and res == 'WARN' else 0))


if __name__ == '__main__':
    main()
