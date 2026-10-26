import numpy as np, wave
SR = 48000
D = 10.0
n = int(SR * D)
L = np.zeros(n); Rr = np.zeros(n)
rng = np.random.default_rng(1)
t_all = np.arange(n) / SR

def add(sig, start, gain=1.0, pan=0.0):
    i = int(start * SR)
    if i >= n: return
    sig = sig[: n - i]
    l = gain * np.sqrt(0.5 * (1 - pan)); r = gain * np.sqrt(0.5 * (1 + pan))
    L[i:i + len(sig)] += sig * l
    Rr[i:i + len(sig)] += sig * r

def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(X * g, len(x))

def note(m): return 440 * 2 ** ((m - 69) / 12)

def kick(dur=0.45, big=False):
    t = np.arange(int(dur * SR)) / SR
    f = 45 + (150 if not big else 200) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-t * (7 if not big else 3.2))
    click = rng.normal(0, 1, len(t)) * np.exp(-t * 300) * 0.25
    return np.tanh((np.sin(ph) * env + click) * 1.6)

def hat(dur=0.06, open_=False):
    t = np.arange(int((0.22 if open_ else dur) * SR)) / SR
    x = rng.normal(0, 1, len(t))
    x = fft_filter(x, lo=7000)
    return x * np.exp(-t * (18 if open_ else 70))

def clap():
    t = np.arange(int(0.25 * SR)) / SR
    x = fft_filter(rng.normal(0, 1, len(t)), lo=900, hi=5000)
    env = np.exp(-t * 22)
    for d in (0.0, 0.011, 0.022):
        env = env + (t >= d) * np.exp(-np.maximum(t - d, 0) * 160) * 0.6
    return x * env

def pad(midis, dur, amp=1.0, bright=8):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros(len(t))
    for m in midis:
        for det in (-0.08, 0.08):
            f0 = note(m + det)
            for h in range(1, bright + 1):
                out += np.sin(2 * np.pi * f0 * h * t + h) / h * (0.85 ** h)
    env = np.minimum(1, t / 0.08) * np.minimum(1, (dur - t) / 0.15)
    return out * env * amp / len(midis)

def pluck(m, dur=0.22):
    t = np.arange(int(dur * SR)) / SR
    f0 = note(m)
    out = np.zeros(len(t))
    for h in range(1, 9):
        out += np.sin(2 * np.pi * f0 * h * t) / h * np.exp(-t * (14 + h * 9))
    return out

def bass(m, dur):
    t = np.arange(int(dur * SR)) / SR
    f0 = note(m)
    x = np.sin(2 * np.pi * f0 * t) + 0.35 * np.sin(2 * np.pi * f0 * 2 * t) + 0.12 * np.sin(2 * np.pi * f0 * 3 * t)
    env = np.minimum(1, t / 0.005) * np.exp(-t * 6)
    return np.tanh(x * env * 1.4)

def riser(dur, lo=300, hi=6000):
    t = np.arange(int(dur * SR)) / SR
    x = rng.normal(0, 1, len(t))
    # sweep via chunked band filtering
    out = np.zeros(len(t))
    ch = 2400
    for i in range(0, len(t), ch):
        k = i / len(t)
        fc = lo * (hi / lo) ** k
        seg = rng.normal(0, 1, ch + 1200)
        seg = fft_filter(seg, lo=fc * 0.6, hi=fc * 1.6)[600:600 + ch]
        out[i:i + ch] = seg[: len(out[i:i + ch])]
    env = (t / dur) ** 2.2
    return out * env

def impact(dur=1.6):
    t = np.arange(int(dur * SR)) / SR
    boom = kick(dur, big=True)
    noise = fft_filter(rng.normal(0, 1, len(t)), hi=2500) * np.exp(-t * 6) * 0.5
    return boom + noise

def whoosh(dur=0.3):
    t = np.arange(int(dur * SR)) / SR
    x = fft_filter(rng.normal(0, 1, len(t)), lo=500, hi=4000)
    env = np.sin(np.pi * t / dur) ** 2
    return x * env

def glitch(dur=0.04):
    t = np.arange(int(dur * SR)) / SR
    f = rng.uniform(800, 3000)
    return np.sign(np.sin(2 * np.pi * f * t)) * np.exp(-t * 60) * 0.5

beat = 0.5
# --- Section A 0-2: tension
add(pad([45, 52, 57], 2.05, 0.9, bright=5), 0.0, 0.10)
add(fft_filter(rng.normal(0, 1, int(2 * SR)), lo=60, hi=200) * np.linspace(0.2, 1, int(2 * SR)), 0, 0.05)
add(riser(1.95, 250, 7000), 0.05, 0.12)
for k in range(10):
    tt = rng.uniform(0.3, 1.9)
    add(glitch(), tt, 0.06, pan=rng.uniform(-0.8, 0.8))
add(glitch(0.06), 0.32, 0.12)
for k in range(4):  # heartbeat pulse
    add(kick(0.3), k * 0.5, 0.35)
# --- impacts
add(impact(1.8), 2.0, 0.9)
add(impact(2.2), 8.5, 1.0)
add(whoosh(0.28), 3.75, 0.14, pan=-0.3)
add(whoosh(0.32), 6.2, 0.14, pan=0.3)
add(riser(0.9, 400, 9000), 7.6, 0.13)
add(riser(0.6, 300, 6000), 1.45, 0.06)
# --- groove 2-8.5
chords = {2.0: [45, 52, 57, 60, 64], 4.0: [41, 53, 57, 60, 65], 6.0: [48, 55, 60, 64, 67], 8.0: [43, 55, 59, 62, 67]}
for st, ch in chords.items():
    dur = 2.0 if st < 8 else 0.5
    add(pad(ch, dur + 0.05, 1.0, bright=7), st, 0.09)
bass_notes = {2.0: 33, 4.0: 29, 6.0: 36, 8.0: 31}
for st, bn in bass_notes.items():
    dur = 2.0 if st < 8 else 0.5
    for k in range(int(dur / 0.25)):
        if k % 2 == 1 or st >= 4.0:
            add(bass(bn + (12 if k % 4 == 3 else 0), 0.24), st + k * 0.25, 0.22)
for k in range(int(2.0 / beat), int(8.5 / beat)):
    tt = k * beat
    add(kick(), tt, 0.55)
    if tt >= 4.0:
        add(hat(open_=True), tt + 0.25, 0.09, pan=0.2)
        for s16 in (0.125, 0.375):
            add(hat(), tt + s16, 0.05, pan=-0.2)
    if tt >= 4.0 and (k % 2 == 1):
        add(clap(), tt, 0.2)
# arps 4-8.5
arp = {4.0: [65, 69, 72, 77], 6.0: [67, 72, 76, 79], 8.0: [67, 71, 74, 79]}
for st, ns in arp.items():
    dur = 2.0 if st < 8 else 0.5
    for k in range(int(dur / 0.125)):
        add(pluck(ns[k % 4] + (12 if (k // 4) % 2 else 0)), st + k * 0.125, 0.08, pan=0.4 * np.sin(k))
# UI ticks for drag/drop and queue
for tt in (4.45, 5.05, 5.18, 5.32, 5.46):
    add(glitch(0.03), tt, 0.05)
# --- final chord 8.5
add(pad([45, 57, 64, 69, 71, 76], 1.5, 1.0, bright=9), 8.5, 0.16)
for k, m in enumerate([81, 76, 72, 69, 76, 81]):
    add(pluck(m, 0.6), 8.55 + k * 0.12, 0.06, pan=(-1) ** k * 0.4)

# reverb: convolution with decaying noise
def reverb(x, dec=1.2, wet=0.18, seed=3):
    r = np.random.default_rng(seed)
    ir_n = int(dec * SR)
    tt = np.arange(ir_n) / SR
    ir = r.normal(0, 1, ir_n) * np.exp(-tt * 5.0)
    ir = fft_filter(ir, hi=5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    m = len(x) + ir_n
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[: len(x)]
    return x + y * wet
L = reverb(L, seed=3); Rr = reverb(Rr, seed=4)
# master: gentle saturation, fade
st = np.stack([L, Rr], 1)
st = np.tanh(st * 1.2) / 1.2
fade = np.minimum(1, (D - t_all) / 0.45)[:, None]
fin = np.minimum(1, t_all / 0.01)[:, None]
st = st * fade * fin
st = st / np.max(np.abs(st)) * 0.89
with wave.open('music.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print('ok')
