#!/usr/bin/env python3
"""music_synth.py - procedural premium-tech music bed in pure NumPy (no samples, royalty-free by construction).

  python3 music_synth.py --manifest timeline.json --out music.wav --cue-log audio_cues.json      # v2: preferred
  python3 music_synth.py --duration 10 --bpm 120 --hits 2.0,4.0,6.5,8.5 --groove-from 2.0 --hats-from 4.0 --out music.wav

MANIFEST MODE (v2): every sync sound comes from timeline.json and nothing else. Impacts, whooshes, risers and
glitch/tick accents are placed at each event's audio_time (t + audio_offset); there are NO random ticks.
Duration, BPM and the bed structure (music.groove_from / music.hats_from) are read from the manifest too.
--cue-log writes every placed sound as JSON ({t, cue, gain, event_id}) for sync_check.py.
Legacy flag mode still works but scatters random tension ticks; sync_check will report those as orphans.

Pick BPM so every scene cut is on a beat (cut_time / (60/bpm) is an integer). 120 BPM = 0.5 s beats.
Structure: tension (drone + riser + glitch ticks) until the first hit -> impact -> four-on-the-floor groove with
bass, pads, hats, claps and plucked arps -> big final impact + resolving chord on the last hit -> fade.
"""
import argparse, json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 48000
rng = np.random.default_rng(1)

def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); g = np.ones_like(f)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(X * g, len(x))
def note(m): return 440 * 2 ** ((m - 69) / 12)
def tt(d): return np.arange(int(d * SR)) / SR

def kick(d=0.45, big=False):
    t = tt(d); f = 45 + (200 if big else 150) * np.exp(-t * 28)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (3.2 if big else 7)) + rng.normal(0, 1, len(t)) * np.exp(-t * 300) * .25
    return np.tanh(x * 1.6)
def hat(open_=False):
    t = tt(.22 if open_ else .06); return fft_filter(rng.normal(0, 1, len(t)), lo=7000) * np.exp(-t * (18 if open_ else 70))
def clap():
    t = tt(.25); x = fft_filter(rng.normal(0, 1, len(t)), lo=900, hi=5000); env = np.exp(-t * 22)
    for dl in (0, .011, .022): env = env + (t >= dl) * np.exp(-np.maximum(t - dl, 0) * 160) * .6
    return x * env
def pad(ms, d, bright=7):
    t = tt(d); out = np.zeros(len(t))
    for m in ms:
        for det in (-.08, .08):
            for h in range(1, bright + 1): out += np.sin(2 * np.pi * note(m + det) * h * t + h) / h * .85 ** h
    return out * np.minimum(1, t / .08) * np.minimum(1, (d - t) / .15) / len(ms)
def strings(ms, d):
    """Deterministic softly bowed synth-string layer, no external samples."""
    t = tt(d); out = np.zeros(len(t))
    env = (1 - np.exp(-t * 7)) * np.minimum(1, np.maximum(0, d - t) / .28)
    for m in ms:
        vibrato = .0025 * np.sin(2 * np.pi * 5.1 * t)
        phase = 2 * np.pi * note(m) * np.cumsum(1 + vibrato) / SR
        for h in range(1, 7):
            out += (np.sin(h * phase + h * .24) / h**1.55) * (.91**h)
    return out * env / max(1, len(ms))

def pluck(m, d=.22):
    t = tt(d); return sum(np.sin(2 * np.pi * note(m) * h * t) / h * np.exp(-t * (14 + h * 9)) for h in range(1, 9))
def bass(m, d):
    t = tt(d); f = note(m)
    x = np.sin(2 * np.pi * f * t) + .35 * np.sin(4 * np.pi * f * t) + .12 * np.sin(6 * np.pi * f * t)
    return np.tanh(x * np.minimum(1, t / .005) * np.exp(-t * 6) * 1.4)
def riser(d, lo=300, hi=6000):
    n = int(d * SR); out = np.zeros(n); ch = 2400
    for i in range(0, n, ch):
        fc = lo * (hi / lo) ** (i / n); seg = fft_filter(rng.normal(0, 1, ch + 1200), lo=fc * .6, hi=fc * 1.6)[600:600 + ch]
        out[i:i + ch] = seg[:len(out[i:i + ch])]
    return out * (np.arange(n) / n) ** 2.2
def impact(d=1.6):
    t = tt(d); return kick(d, True) + fft_filter(rng.normal(0, 1, len(t)), hi=2500) * np.exp(-t * 6) * .5
def whoosh(d=.3):
    t = tt(d); return fft_filter(rng.normal(0, 1, len(t)), lo=500, hi=4000) * np.sin(np.pi * t / d) ** 2
def tick(d=.04):
    t = tt(d); return np.sign(np.sin(2 * np.pi * rng.uniform(800, 3000) * t)) * np.exp(-t * 60) * .5

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', help='timeline.json: the shared event manifest (v2)')
    ap.add_argument('--cue-log', help='write every placed cue as JSON for sync_check.py')
    ap.add_argument('--duration', type=float, default=10); ap.add_argument('--bpm', type=float, default=120)
    ap.add_argument('--hits', default='2.0,8.5', help='impact times; first = drop, last = final resolve')
    ap.add_argument('--whooshes', default='', help='transition whoosh END times, e.g. 4.0,6.5')
    ap.add_argument('--groove-from', type=float, default=None); ap.add_argument('--hats-from', type=float, default=None)
    ap.add_argument('--out', default='music.wav')
    a = ap.parse_args()
    T = None
    if a.manifest:
        import timeline as TL
        T = TL.load(a.manifest)
        a.duration = T.duration; a.bpm = float(T.bpm or a.bpm)
        mus = T.data.get('music') or {}
        a.groove_from = mus.get('groove_from', a.groove_from); a.hats_from = mus.get('hats_from', a.hats_from)
    D, beat = a.duration, 60 / a.bpm; n = int(SR * D)
    L = np.zeros(n); R = np.zeros(n); LOG = []
    def add(sig, start, gain=1, pan=0, cue=None, eid=None):
        i = int(round(start * SR))
        if i >= n or i < 0: return
        LOG.append(dict(t=round(start, 4), cue=cue, gain=round(float(gain), 3), **({'event_id': eid} if eid else {})))
        sig = sig[:n - i]; L[i:i + len(sig)] += sig * gain * np.sqrt(.5 * (1 - pan)); R[i:i + len(sig)] += sig * gain * np.sqrt(.5 * (1 + pan))
    if T:
        imps = [e for e in T.events() if e.audio == 'impact' and (e.sync or 'required') != 'visual_only']
        hits = sorted(e.t for e in imps) or [D]
    else:
        hits = [float(x) for x in a.hits.split(',') if x]
    first, last = hits[0], hits[-1]
    g0 = first if a.groove_from is None else a.groove_from
    h0 = (first + (last - first) / 3) if a.hats_from is None else a.hats_from
    # tension bed (pad + heartbeat) up to the first hit
    add(pad([45, 52, 57], first + .05, 5), 0, .10, cue='pad')
    for k in range(int(first / beat)): add(kick(.3), k * beat, .35, cue='kick')
    if T:
        # every sync sound comes from the manifest, at its audio_time, tagged with its event id
        for e in T.events():
            if (e.sync or 'required') == 'visual_only' or not e.audio: continue
            at, g = e.audio_time, e.get('gain')
            if e.audio == 'impact':
                fin = abs(e.t - last) < 1e-6
                add(impact(2.2 if fin else 1.8), at, g or (1.0 if fin else .9), cue='impact', eid=e.id)
            elif e.audio == 'whoosh': add(whoosh(float(e.duration or .3)), at, g or .14, rng.uniform(-.4, .4), cue='whoosh', eid=e.id)
            elif e.audio == 'riser': add(riser(float(e.duration or .9), 300, 8000), at, g or .12, cue='riser', eid=e.id)
            elif e.audio in ('glitch', 'tick'): add(tick(), at, g or .07, rng.uniform(-.6, .6), cue=e.audio, eid=e.id)
            elif e.audio == 'kick':
                if g0 is None or at < g0 or abs(((at - g0) / beat) - round((at - g0) / beat)) > 1e-3:
                    add(kick(), at, g or .55, cue='kick', eid=e.id)   # off-grid kick: place it explicitly
                else:
                    LOG.append(dict(t=round(at, 4), cue='kick', gain=.55, event_id=e.id, note='bed downbeat'))
    else:
        add(riser(max(.3, first - .05), 250, 7000), .05, .12, cue='riser')
        for _ in range(int(first * 5)): add(tick(), rng.uniform(.3, first - .1), .06, rng.uniform(-.8, .8), cue='tick')   # legacy: unsynced
        for h in hits: add(impact(1.8 if h != last else 2.2), h, .9 if h != last else 1.0, cue='impact')
        for w in [float(x) for x in a.whooshes.split(',') if x]: add(whoosh(.3), w - .28, .14, rng.uniform(-.4, .4), cue='whoosh')
        add(riser(min(.9, last - g0), 400, 9000), last - min(.9, last - g0), .13, cue='riser')
    # groove: Am - F - C - G, 4 beats per chord
    prog_ = [([45, 52, 57, 60, 64], 33, [69, 72, 76, 81]), ([41, 53, 57, 60, 65], 29, [65, 69, 72, 77]),
             ([48, 55, 60, 64, 67], 36, [67, 72, 76, 79]), ([43, 55, 59, 62, 67], 31, [67, 71, 74, 79])]
    bar = 4 * beat; t0 = g0; ci = 0
    while t0 < last - 1e-6:
        d = min(bar, last - t0); chord, bn, arp = prog_[ci % 4]
        add(pad(chord, d + .05), t0, .09, cue='pad')
        for k in range(int(round(d / (beat / 2)))): add(bass(bn + (12 if k % 4 == 3 else 0), beat / 2 - .01), t0 + k * beat / 2, .22, cue='bass')
        if t0 >= h0:
            for k in range(int(round(d / (beat / 4)))): add(pluck(arp[k % 4] + (12 if (k // 4) % 2 else 0)), t0 + k * beat / 4, .08, .4 * np.sin(k), cue='pluck')
        t0 += d; ci += 1
    k = 0
    while g0 + k * beat < last - 1e-6:
        tb = g0 + k * beat; add(kick(), tb, .55, cue='kick')
        if tb >= h0:
            add(hat(True), tb + beat / 2, .09, .2, cue='hat')
            for s_ in (beat / 4, 3 * beat / 4): add(hat(), tb + s_, .05, -.2, cue='hat')
            if k % 2 == 1: add(clap(), tb, .2, cue='clap')
        k += 1
    add(pad([45, 57, 64, 69, 71, 76], D - last + .05, 9), last, .16, cue='pad')
    for j, m in enumerate([81, 76, 72, 69, 76, 81]): add(pluck(m, .6), last + .05 + j * .12, .06, (-1) ** j * .4, cue='pluck')
    # Optional score direction is specified inside the shared timeline.
    # Additional warm string harmonics enrich the original synth material.
    if T:
        score = T.data.get('music') or {}
        if score.get('strings_from') is not None:
            start=float(score['strings_from'])
            ti=start
            j=0
            while ti < last - .15:
                d=min(bar,last-ti)
                chord=[(57,60,64),(53,57,60),(60,64,67),(55,59,62)][j%4]
                add(strings(chord,d+.2),ti,.037,cue='strings')
                ti+=d
                j+=1
    if a.cue_log:
        with open(a.cue_log, 'w') as f: json.dump(sorted(LOG, key=lambda c: c['t']), f, indent=0)
    # convolution reverb + master
    def verb(x, seed):
        r = np.random.default_rng(seed); m = int(1.2 * SR); ir = fft_filter(r.normal(0, 1, m) * np.exp(-tt(1.2) * 5), hi=5000)
        ir /= np.sqrt((ir ** 2).sum()); M_ = len(x) + m
        return x + np.fft.irfft(np.fft.rfft(x, M_) * np.fft.rfft(ir, M_), M_)[:len(x)] * .18
    st = np.stack([verb(L, 3), verb(R, 4)], 1); st = np.tanh(st * 1.2) / 1.2
    t = np.arange(n) / SR; st *= (np.minimum(1, (D - t) / .45) * np.minimum(1, t / .01))[:, None]
    if T:
        # Narrative vacuum is a musical decision, not a random SFX mute.
        # Apply after reverb so the pause is genuinely negative space.
        for window in (T.data.get('music') or {}).get('vacuum', []):
            a0,b0=map(float,window)
            gate=np.ones(n,dtype=np.float32)
            fade=.035
            falling=(t>=a0-fade)&(t<a0)
            gate[falling]=np.maximum(0,(a0-t[falling])/fade)
            gate[(t>=a0)&(t<=b0)]=0
            rising=(t>b0)&(t<b0+fade)
            gate[rising]=np.minimum(1,(t[rising]-b0)/fade)
            st*=gate[:,None]
    st = st / np.max(np.abs(st)) * .89
    with wave.open(a.out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype(np.int16).tobytes())
    print('wrote', a.out)

if __name__ == '__main__':
    main()
