#!/usr/bin/env python3
"""validate.py <video.mp4> <expected_duration_s> [--w 1920 --h 1080 --fps 30]

Checks a finished render and writes <video>_contact.png (one tile per 0.5 s) for visual QA.
Exit code 1 if any hard check fails.
  - container/stream durations within 1 frame of target
  - resolution, fps, yuv420p (plays everywhere)
  - frame count == duration * fps
  - no fully black frames except optional first/last frame
  - audio: integrated loudness and true peak (warn outside -18..-12 LUFS or peak > -1 dBTP)
"""
import json, subprocess, sys, re, os

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    a = sys.argv[1:]
    if len(a) < 2: print(__doc__); sys.exit(2)
    path, dur = a[0], float(a[1])
    opt = {k: v for k, v in zip(a[2::2], a[3::2])}
    W, H, FPS = int(opt.get('--w', 1920)), int(opt.get('--h', 1080)), float(opt.get('--fps', 30))
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + msg); ok &= bool(cond)

    p = sh(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-count_frames', '-of', 'json', path])
    if p.returncode: print('FAIL ffprobe:', p.stderr); sys.exit(1)
    info = json.loads(p.stdout)
    fmt_d = float(info['format']['duration'])
    v = [s for s in info['streams'] if s['codec_type'] == 'video'][0]
    au = [s for s in info['streams'] if s['codec_type'] == 'audio']
    num, den = map(int, v['r_frame_rate'].split('/'))
    fps = num / den
    tol = 1.0 / FPS + 1e-3
    check(abs(fmt_d - dur) <= tol, f'container duration {fmt_d:.3f}s (target {dur}s)')
    check((int(v['width']), int(v['height'])) == (W, H), f"resolution {v['width']}x{v['height']}")
    check(abs(fps - FPS) < 0.01, f'fps {fps:.3f}')
    check(v.get('pix_fmt') == 'yuv420p', f"pix_fmt {v.get('pix_fmt')}")
    nf = int(v.get('nb_read_frames', 0))
    check(abs(nf - round(dur * FPS)) <= 1, f'frame count {nf} (expected {round(dur * FPS)})')
    if au:
        ad = float(au[0].get('duration', fmt_d))
        check(abs(ad - dur) <= 0.05, f'audio duration {ad:.3f}s')
        e = sh(['ffmpeg', '-hide_banner', '-i', path, '-af', 'ebur128=peak=true', '-f', 'null', '-'])
        I = re.findall(r'I:\s+(-?[\d.]+) LUFS', e.stderr); pk = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', e.stderr)
        if I:
            Iv, pkv = float(I[-1]), float(pk[-1]) if pk else 0
            print(('PASS ' if -18 <= Iv <= -12 else 'WARN ') + f'loudness {Iv} LUFS')
            print(('PASS ' if pkv <= -1.0 else 'WARN ') + f'true peak {pkv} dBFS')
    else:
        print('INFO no audio stream')
    bd = sh(['ffmpeg', '-hide_banner', '-i', path, '-vf', 'blackdetect=d=0.05:pix_th=0.04', '-an', '-f', 'null', '-'])
    blacks = re.findall(r'black_start:([\d.]+) black_end:([\d.]+)', bd.stderr)
    blacks = [(float(s), float(e_)) for s, e_ in blacks if not (float(s) < 0.04 or float(e_) > dur - 0.04)]
    check(not blacks, f'no black gaps {blacks if blacks else ""}')
    out = os.path.splitext(path)[0] + '_contact.png'
    cols = 5; n = max(1, int(dur * 2)); rows = (n + cols - 1) // cols
    sh(['ffmpeg', '-y', '-v', 'error', '-i', path, '-vf', f'fps=2,scale=384:-2,tile={cols}x{rows}', '-frames:v', '1', '-update', '1', out])
    print('INFO contact sheet ->', out, '(inspect: text legible, no clipped glyphs, no boxy glow edges, transitions land on cuts)')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
