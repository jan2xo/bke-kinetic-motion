"""synth.py - deterministic synthetic test videos (NumPy -> FFmpeg). No assets needed."""
import subprocess
import numpy as np


def render(path, duration, fps, size, scene_fn, grain=3.0, seed=0, crf=16):
    """scene_fn(t, frame_rgb_float, rng) draws into a dark frame. Grain is per-frame random, like the kit's finish."""
    w, h = size
    rng = np.random.default_rng(seed)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
           '-c:v', 'libx264', '-crf', str(crf), '-preset', 'veryfast', '-pix_fmt', 'yuv420p', path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(duration * fps))
    for i in range(n):
        t = i / fps
        f = np.full((h, w, 3), 14.0, np.float32)
        scene_fn(t, f, rng)
        if grain: f += rng.normal(0, grain, (h, w, 1)).astype(np.float32)
        p.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return path


def square(f, cx, cy, s, col=(240, 240, 240)):
    h, w = f.shape[:2]
    x0, x1 = int((cx - s / 2) * w), int((cx + s / 2) * w)
    y0, y1 = int((cy - s / 2 * w / h) * h), int((cy + s / 2 * w / h) * h)
    f[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = col


def mover(segments, flash_at=(), size=0.08):
    """segments: list of (t0, t1, moving: bool). The square oscillates while moving and freezes otherwise."""
    def fn(t, f, rng):
        x = 0.5
        acc = 0.0
        for t0, t1, mv in segments:
            if t >= t0:
                acc += (min(t, t1) - t0) if mv else 0.0
        x = 0.5 + 0.35 * np.sin(acc * 2.2)
        square(f, x, 0.5, size)
        for fa in flash_at:
            if 0 <= t - fa < 0.2:
                f += (255 - f) * (0.8 * (1 - (t - fa) / 0.2))
    return fn


def texture_pan(speed_px_per_s, size):
    w, h = size
    r = np.random.default_rng(5)
    tex = (r.random((h // 8 + 2, (w * 3) // 8 + 2)) * 120 + 20).astype(np.float32)
    tex = np.kron(tex, np.ones((8, 8), np.float32))
    def fn(t, f, rng):
        off = int(t * speed_px_per_s) % (tex.shape[1] - w)
        f[:, :, :] = tex[:h, off:off + w, None]
    return fn
