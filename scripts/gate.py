#!/usr/bin/env python3
"""gate.py - the production gate. A build is DONE only when this exits 0. (v2.2)

A planning PASS is not a finished video. The gate refuses to call a build done until all of the following
hold, and it never takes the author's word for anything it can check itself:

  1 PLAN      timeline.py check passes (polarity, beats, ranked impacts, 3D rules).
  2 ENGINE    static analysis of the renderer source. It must be built on the kit, not a from-scratch sketch:
                - imports mglib (and mg3d with a camera3d block), loads the manifest through timeline.load
                - typography through mglib.Text, every frame through mglib.finish
                - writes visual_log.json; no S=1 outside a --preview branch
                - every visual event id in the manifest is referenced in the renderer source
                  (literal 'id' or an f-string pattern such as f'land{i}'), so no event is declared and never drawn
              WARN: raw ImageDraw.text calls (typography that bypasses the type system),
                    float literals equal to a manifest event time (hardcoded timing).
  3 MAP       every visual event appears in visual_log.json, and every event with a sound appears in the audio cue
              log by event_id. visual_log must contain no ids the manifest does not declare.
  4 RENDER    (with --video) validate.py, motion_energy, sync_check and lint3d reports contain no FAIL.
              A required impact must produce a measured peak (motion_energy impact rank).

  python3 scripts/gate.py static  <render.py> <timeline.json>
  python3 scripts/gate.py full    <render.py> <timeline.json> --out <dir> [--w 1080 --h 1920] [--strict]
      --out holds the build: visual_log.json, audio_cues.json, <name>.mp4 or --video, qa/, lint3d.txt, validate.txt

Writes <out>/gate_report.json and <out>/gate_summary.md (also appended to $GITHUB_STEP_SUMMARY when set).
Exit 2 on FAIL (--strict: WARN also fails, exit 1).
"""
import argparse, ast, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as TL

VERSION = '2.2.0'


class Report:
    def __init__(self): self.items = []
    def add(self, level, stage, code, msg): self.items.append(dict(level=level, stage=stage, code=code, message=msg))
    def result(self):
        lv = [i['level'] for i in self.items]
        return 'FAIL' if 'FAIL' in lv else ('WARN' if 'WARN' in lv else 'PASS')


def visual_events(T):
    return [e for e in T.events() if (e.sync or 'required') != 'audio_only' and e.kind != 'anticipation']


def sound_events(T):
    return [e for e in T.events() if e.audio and (e.sync or 'required') != 'visual_only']


# ------------------------------------------------------------------ 1 plan
def stage_plan(T, R):
    items = TL.check(T)
    nf = 0
    for lvl, code, msg in items:
        if lvl == 'FAIL':
            nf += 1; R.add('FAIL', 'plan', code, msg)
        elif lvl == 'WARN':
            R.add('WARN', 'plan', code, msg)
    if not nf: R.add('PASS', 'plan', 'plan_check', f'timeline.py check: {len(T.events())} events, {len(T.beats)} beats')


# ------------------------------------------------------------------ 2 engine (static)
def _id_patterns(src_tree, src):
    """Every string literal plus every f-string turned into a regex ({...} -> .+)."""
    lits, pats = set(), []
    for node in ast.walk(src_tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lits.add(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str): parts.append(re.escape(v.value))
                else: parts.append('.+')
            rx = ''.join(parts)
            if rx.replace('.+', ''):
                pats.append(re.compile('^' + rx + '$'))
    return lits, pats


def stage_engine(T, render_path, R):
    src = open(render_path, encoding='utf-8').read()
    try:
        tree = ast.parse(src)
    except SyntaxError as ex:
        R.add('FAIL', 'engine', 'syntax', f'{render_path}: {ex}'); return
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imports |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module.split('.')[0])
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name: calls[name] = calls.get(name, 0) + 1

    def need(cond, code, ok, bad):
        R.add('PASS' if cond else 'FAIL', 'engine', code, ok if cond else bad)

    need('mglib' in imports, 'kit_import', 'imports mglib', 'renderer does not import mglib: it is a from-scratch sketch, not a kit build')
    need('timeline' in imports and calls.get('load', 0) > 0, 'manifest_load', 'loads the manifest through timeline.load',
         'renderer does not load the manifest with timeline.load: times cannot be trusted to come from timeline.json')
    if T.data.get('camera3d'):
        uses_cam = any(calls.get(k) for k in ('CameraRig', 'Camera', 'Renderer'))
        need('mg3d' in imports and uses_cam, 'camera3d', 'camera3d declared and mg3d camera/renderer used',
             'manifest declares camera3d but the renderer does not use mg3d (CameraRig/Renderer): "3D" would only be 2D scaling')
    need(calls.get('Text', 0) > 0, 'typography', f"mglib.Text used ({calls.get('Text', 0)} calls)",
         'no mglib.Text: typography bypasses tracking, mask rise, stagger and glow')
    need(calls.get('finish', 0) > 0, 'finish', 'frames pass through mglib.finish (grain + vignette)',
         'no mglib.finish: frames ship without grain/vignette (flat digital look)')
    need('visual_log.json' in src, 'visual_log', 'renderer writes visual_log.json', 'renderer never writes visual_log.json')
    for m in re.finditer(r'configure\(([^)]*)\)', src):
        line = src[:m.start()].count('\n')
        text = src.splitlines()[line]
        if re.search(r'\bS\s*=\s*1\b', m.group(1)) and 'preview' not in text:
            R.add('FAIL', 'engine', 'supersample', f'line {line + 1}: S=1 outside a --preview branch (final frames must be supersampled)')
    raw = len(re.findall(r'\.text\(\s*\(', src))
    if raw:
        R.add('WARN', 'engine', 'raw_text', f'{raw} raw ImageDraw.text call(s): use mglib.Text for anything the viewer reads')

    lits, pats = _id_patterns(tree, src)
    missing = []
    for e in visual_events(T):
        if e.id in lits or any(p.match(e.id) for p in pats): continue
        missing.append(e.id)
    if missing and calls.get('events', 0) > 0:
        R.add('WARN', 'engine', 'query_driven', f'{len(missing)} visual event(s) not named in the source but the renderer queries '
              f'TLM.events(): {", ".join(missing)}. Their proof rests on the visual_log map and the rendered QA')
    elif missing:
        R.add('FAIL', 'engine', 'unimplemented', f'{len(missing)} visual event(s) never referenced in the renderer: {", ".join(missing)}')
    else:
        R.add('PASS', 'engine', 'event_refs', f'all {len(visual_events(T))} visual events referenced in the renderer')

    times = {round(float(e.t), 3) for e in T.events() if e.t and float(e.t) not in (0.0, 1.0)}
    hard = set()
    def _timeish(n):
        return isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value >= 1.5 and round(n.value, 3) in times
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):          # t >= 6.0, 3 <= t < 6.12
            for n in [node.left] + list(node.comparators):
                if _timeish(n): hard.add(n.value)
        elif isinstance(node, ast.Call):           # prog(t, 6.0, 6.5), progress(t, 12, .15)
            f = node.func; fn = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
            if fn in ('prog', 'progress', 'expo', 'cubic', 'between'):
                for n in node.args:
                    if _timeish(n): hard.add(n.value)
    if hard:
        R.add('WARN', 'engine', 'hardcoded_time', f'float literal(s) equal to manifest event times: {sorted(hard)}; read times from the manifest')


# ------------------------------------------------------------------ 3 implementation map
def stage_map(T, out, R):
    vpath, apath = os.path.join(out, 'visual_log.json'), os.path.join(out, 'audio_cues.json')
    if not os.path.exists(vpath):
        R.add('FAIL', 'map', 'no_visual_log', 'visual_log.json missing: the renderer must log every event it performs')
    else:
        vlog = json.load(open(vpath)); vid = {v.get('event_id') for v in vlog}
        miss = [e.id for e in visual_events(T) if e.id not in vid]
        extra = sorted(i for i in vid - {e.id for e in T.events()} if i)
        if miss: R.add('FAIL', 'map', 'unrendered', f'not in visual_log: {", ".join(miss)}')
        else: R.add('PASS', 'map', 'visual_map', f'all {len(visual_events(T))} visual events logged')
        if extra: R.add('FAIL', 'map', 'undeclared', f'visual_log ids not in the manifest: {", ".join(extra)}')
        drift = []
        for v in vlog:
            try: e = T.event(v.get('event_id'))
            except KeyError: continue
            if v.get('t') is not None and abs(float(v['t']) - float(e.t)) > max(e.tol, 1.5 / T.fps):
                drift.append(f"{e.id} logged {float(v['t']):.3f}s vs manifest {float(e.t):.3f}s")
        if drift: R.add('FAIL', 'map', 'visual_drift', '; '.join(drift))
    if not os.path.exists(apath):
        R.add('FAIL', 'map', 'no_audio_log', 'audio_cues.json missing: run music_synth.py --manifest ... --cue-log audio_cues.json')
    else:
        cues = json.load(open(apath)); cid = {c.get('event_id') for c in cues}
        miss = [e.id for e in sound_events(T) if e.id not in cid]
        if miss: R.add('FAIL', 'map', 'silent_event', f'events with a sound but no cue: {", ".join(miss)}')
        else: R.add('PASS', 'map', 'audio_map', f'all {len(sound_events(T))} sound events scheduled')


# ------------------------------------------------------------------ 4 rendered QA
def _report_result(path):
    if not os.path.exists(path): return None
    try: return json.load(open(path)).get('result')
    except Exception: return 'FAIL'


def stage_render(T, out, video, R):
    if not video or not os.path.exists(video):
        R.add('FAIL', 'render', 'no_video', f'no rendered MP4 ({video}): a plan is not a deliverable'); return
    val = os.path.join(out, 'validate.txt')
    if not os.path.exists(val): R.add('FAIL', 'render', 'no_validate', 'validate.txt missing (run validate.py and tee it)')
    else:
        fails = [l.strip() for l in open(val) if l.startswith('FAIL')]
        if fails: R.add('FAIL', 'render', 'validate', '; '.join(fails))
        else: R.add('PASS', 'render', 'validate', 'container, size, fps, frame count, black frames and loudness pass')
    for name, code in (('motion_report.json', 'motion'), ('sync_report.json', 'sync')):
        res = _report_result(os.path.join(out, 'qa', name))
        if res is None: R.add('FAIL', 'render', code, f'qa/{name} missing')
        elif res == 'FAIL': R.add('FAIL', 'render', code, f'qa/{name}: FAIL (see qa/{code}_summary.txt)')
        else: R.add('WARN' if res == 'WARN' else 'PASS', 'render', code, f'qa/{name}: {res}')
    mr = os.path.join(out, 'qa', 'motion_report.json')
    if os.path.exists(mr):
        rep = json.load(open(mr))
        imps = rep.get('impacts') or {}
        rows = imps.get('rows') if isinstance(imps, dict) else imps
        for r in rows or []:
            if isinstance(r, dict) and r.get('found') is False:
                R.add('FAIL', 'render', 'impact_missing', f"ranked impact {r.get('event') or r.get('id')} produced no measured peak")
    if T.data.get('camera3d'):
        lt = os.path.join(out, 'lint3d.txt')
        if not os.path.exists(lt): R.add('FAIL', 'render', 'lint3d', 'camera3d declared but lint3d.txt missing (run render.py lint)')
        elif any(l.startswith('FAIL') for l in open(lt)): R.add('FAIL', 'render', 'lint3d', 'lint3d.txt has FAIL lines')
        else: R.add('PASS', 'render', 'lint3d', 'camera, readability and end-state lint pass')


# ------------------------------------------------------------------ output
def write(R, out, name, mode):
    res = R.result()
    icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}
    lines = [f'## BKE gate: {name} ({mode}): {icon[res]} {res}', '', '| | Stage | Check | Detail |', '|---|---|---|---|']
    for i in R.items:
        lines.append(f"| {icon[i['level']]} | {i['stage']} | {i['code']} | {i['message'].replace('|', '/')} |")
    nf = sum(i['level'] == 'FAIL' for i in R.items); nw = sum(i['level'] == 'WARN' for i in R.items)
    lines += ['', f'**RESULT: {res}** ({nf} fail, {nw} warn). A build is done only at PASS or reviewed WARN.']
    md = '\n'.join(lines) + '\n'
    print(md)
    if out:
        os.makedirs(out, exist_ok=True)
        json.dump(dict(tool='bke-kinetic-motion/gate', version=VERSION, name=name, mode=mode, result=res, items=R.items),
                  open(os.path.join(out, 'gate_report.json'), 'w'), indent=1)
        open(os.path.join(out, 'gate_summary.md'), 'w').write(md)
    gs = os.environ.get('GITHUB_STEP_SUMMARY')
    if gs:
        with open(gs, 'a') as f: f.write(md + '\n')
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['static', 'full'])
    ap.add_argument('render'); ap.add_argument('manifest')
    ap.add_argument('--out', default=None); ap.add_argument('--video', default=None)
    ap.add_argument('--name', default=None); ap.add_argument('--strict', action='store_true')
    a = ap.parse_args(argv)
    T = TL.load(a.manifest); R = Report()
    name = a.name or os.path.basename(os.path.dirname(os.path.abspath(a.render)))
    stage_plan(T, R)
    stage_engine(T, a.render, R)
    if a.mode == 'full':
        if not a.out: ap.error('full mode needs --out')
        stage_map(T, a.out, R)
        video = a.video
        if not video:
            mp4s = sorted(f for f in os.listdir(a.out) if f.endswith('.mp4'))
            video = os.path.join(a.out, mp4s[0]) if mp4s else None
        stage_render(T, a.out, video, R)
    res = write(R, a.out, name, a.mode)
    return 2 if res == 'FAIL' else (1 if a.strict and res == 'WARN' else 0)


if __name__ == '__main__':
    sys.exit(main())
