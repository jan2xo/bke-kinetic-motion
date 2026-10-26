#!/usr/bin/env python3
"""produce.py - one command from manifest to gated MP4. This is what GitHub Actions runs. (v2.2)

  python3 scripts/produce.py <project_dir> [--preview] [--out out/<name>]

<project_dir> holds render.py + timeline.json (+ its assets). The 3D demo is the built-in project
`templates` (promo_3d_template.py + timeline_3d.json); pass `3d-demo` for it.

Steps (stops at the first hard failure, the gate always runs last):
  plan check -> static gate -> render frames + visual_log -> lint3d -> music from the manifest
  -> encode -> validate -> motion_energy -> sync_check -> previews -> full gate
Canvas size comes from the manifest's "canvas": {"w": 1080, "h": 1920} (default 1920x1080).
Exit code = the gate's exit code (2 FAIL, 1 strict WARN, 0 PASS).
"""
import argparse, json, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')


def resolve(project):
    if project in ('3d-demo', 'templates'):
        return 'promo-3d-demo', os.path.join(ROOT, 'templates', 'promo_3d_template.py'), os.path.join(ROOT, 'templates', 'timeline_3d.json')
    d = project if os.path.isdir(project) else os.path.join(ROOT, 'projects', project)
    d = os.path.abspath(d)
    r, m = os.path.join(d, 'render.py'), os.path.join(d, 'timeline.json')
    for p in (r, m):
        if not os.path.exists(p): sys.exit(f'produce: missing {p}. A project is a folder with render.py + timeline.json')
    return os.path.basename(d), r, m


def run(cmd, cwd, log, allow=(0,), env=None):
    t0 = time.time()
    print(f'\n$ {" ".join(cmd)}', flush=True)
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    out = (p.stdout or '') + (p.stderr or '')
    print(out[-6000:], flush=True)
    log.append(dict(cmd=' '.join(cmd), code=p.returncode, seconds=round(time.time() - t0, 1)))
    return p.returncode in allow, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project'); ap.add_argument('--preview', action='store_true'); ap.add_argument('--out')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    name, render, manifest = resolve(a.project)
    out = os.path.abspath(a.out or os.path.join(ROOT, 'out', name))
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(out)
    T = json.load(open(manifest))
    W, H = int(T.get('canvas', {}).get('w', 1920)), int(T.get('canvas', {}).get('h', 1080))
    D, FPS = float(T['duration']), int(T.get('fps', 30))
    py, log = sys.executable, []
    env = dict(os.environ, BKE_MANIFEST=manifest, BKE_KIT=ROOT)
    mp4 = os.path.join(out, f'{name}.mp4')

    def gate():
        ok, _ = run([py, os.path.join(S, 'gate.py'), 'full', render, manifest, '--out', out, '--video', mp4, '--name', name]
                    + (['--strict'] if a.strict else []), out, log, allow=(0, 1, 2))
        res = json.load(open(os.path.join(out, 'gate_report.json')))['result']
        json.dump(dict(project=name, preview=a.preview, steps=log, gate=res), open(os.path.join(out, 'produce_log.json'), 'w'), indent=1)
        return {'PASS': 0, 'WARN': 1 if a.strict else 0}.get(res, 2)

    ok, _ = run([py, os.path.join(S, 'timeline.py'), 'check', manifest, '--json', os.path.join(out, 'plan_check.json')], out, log)
    ok2, _ = run([py, os.path.join(S, 'gate.py'), 'static', render, manifest, '--name', name], out, log, allow=(0, 1, 2))
    if not ok:
        sys.exit(gate())
    ok, _ = run([py, render, 'render'] + (['--preview'] if a.preview else []), out, log, env=env)
    if not ok: sys.exit(gate())
    if T.get('camera3d'):
        run([py, render, 'lint'], out, log, allow=(0, 2), env=env)
    run([py, os.path.join(S, 'music_synth.py'), '--manifest', manifest, '--out', 'music.wav', '--cue-log', 'audio_cues.json'], out, log)
    ok, _ = run(['bash', os.path.join(S, 'encode.sh'), 'frames', 'music.wav', mp4, str(D), str(FPS)], out, log)
    if not ok: sys.exit(gate())
    _, vtxt = run([py, os.path.join(S, 'validate.py'), mp4, str(D), '--w', str(W), '--h', str(H), '--fps', str(FPS)], out, log, allow=(0, 1))
    open(os.path.join(out, 'validate.txt'), 'w').write(vtxt)
    run([py, os.path.join(S, 'motion_energy.py'), mp4, '--manifest', manifest, '--out', 'qa'], out, log, allow=(0, 1, 2))
    run([py, os.path.join(S, 'sync_check.py'), manifest, '--audio-log', 'audio_cues.json', '--visual-log', 'visual_log.json',
         '--video', mp4, '--motion', 'qa/motion_report.json', '--out', 'qa'], out, log, allow=(0, 1, 2))
    run([py, os.path.join(S, 'preview.py'), mp4, '--manifest', manifest, '--motion', 'qa/motion_report.json', '--out', 'qa/previews'],
        out, log, allow=(0, 1, 2))
    shutil.rmtree(os.path.join(out, 'frames'), ignore_errors=True)
    sys.exit(gate())


if __name__ == '__main__':
    main()
