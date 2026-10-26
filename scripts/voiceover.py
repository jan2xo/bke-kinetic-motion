#!/usr/bin/env python3
"""voiceover.py - beat-locked TTS voiceover + ducked mix.

  python3 voiceover.py --cues cues.txt --music music.wav --duration 10 --out mix_vo.wav [--voice en-US-ChristopherNeural]

cues.txt: one cue per line  "<start_seconds> | <text> [| tempo]"   e.g.
  0.35 | Media chaos?
  9.17 | by B K E. | 1.2
TTS engine: edge-tts (free Microsoft neural voices, needs internet). Any TTS that writes audio files can replace gen().
Each line's leading/trailing silence is trimmed so the FIRST SYLLABLE lands on the cue time.
"""
import argparse, subprocess, os, tempfile, sys

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode: sys.exit(f'failed: {" ".join(cmd)}\n{p.stderr}')
    return p.stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cues', required=True); ap.add_argument('--music', required=True)
    ap.add_argument('--duration', type=float, required=True); ap.add_argument('--out', default='mix_vo.wav')
    ap.add_argument('--voice', default='en-US-ChristopherNeural'); ap.add_argument('--pitch', default='-6Hz')
    ap.add_argument('--lufs', type=float, default=-14)
    a = ap.parse_args()
    cues = []
    for ln in open(a.cues, encoding='utf-8'):
        if not ln.strip() or ln.startswith('#'): continue
        parts = [p.strip() for p in ln.split('|')]
        cues.append((float(parts[0]), parts[1], float(parts[2]) if len(parts) > 2 else 1.0))
    tmp = tempfile.mkdtemp(); wavs = []
    for i, (st, text, tempo) in enumerate(cues):
        mp3 = os.path.join(tmp, f'{i}.mp3'); wav = os.path.join(tmp, f'{i}.wav')
        run([sys.executable, '-m', 'edge_tts', '--voice', a.voice, f'--pitch={a.pitch}', '--text', text, '--write-media', mp3])
        trim = 'silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse'
        run(['ffmpeg', '-y', '-v', 'error', '-i', mp3, '-af', trim, '-ar', '48000', '-ac', '2', wav])
        d = float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav])) / tempo
        end = st + d
        nxt = cues[i + 1][0] if i + 1 < len(cues) else a.duration
        flag = '  <-- OVERLAPS next cue / end: raise tempo or shorten text' if end > nxt else ''
        print(f'{st:6.2f}-{end:6.2f}s  {text}{flag}')
        wavs.append((wav, st, tempo))
    inputs = sum([['-i', w] for w, _, _ in wavs], []) + ['-i', a.music]
    chains = []
    for k, (_, st, tempo) in enumerate(wavs):
        ms = int(st * 1000); tp = f'atempo={tempo},' if abs(tempo - 1) > 1e-3 else ''
        chains.append(f'[{k}]{tp}adelay={ms}|{ms}[v{k}]')
    n = len(wavs); D = a.duration
    fc = ';'.join(chains) + ';' + ''.join(f'[v{k}]' for k in range(n)) + \
        f'amix=inputs={n}:normalize=0,apad=whole_dur={D},atrim=0:{D},highpass=f=90,' \
        'acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=4,equalizer=f=3500:t=q:w=1:g=2,volume=1.6[vo];' \
        '[vo]asplit=2[vo1][vosc];' \
        f'[{n}]loudnorm=I=-18:TP=-2,atrim=0:{D}[mus];' \
        '[mus][vosc]sidechaincompress=threshold=0.03:ratio=5:attack=10:release=250[duck];' \
        f'[duck][vo1]amix=inputs=2:normalize=0,alimiter=limit=0.89,loudnorm=I={a.lufs}:TP=-1:LRA=11,atrim=0:{D}[out]'
    run(['ffmpeg', '-y', '-v', 'error'] + inputs + ['-filter_complex', fc, '-map', '[out]', '-ar', '48000', a.out])
    print('wrote', a.out, '\nmux: ffmpeg -i video.mp4 -i', a.out, '-map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -t', D, 'out_vo.mp4')

if __name__ == '__main__':
    main()
