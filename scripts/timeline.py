#!/usr/bin/env python3
"""timeline.py - the ONE shared event manifest for picture and sound, plus the creative plan checker.

The manifest (timeline.json) is written BEFORE any rendering code. Both the animation code and the
audio code read their times from it, so a sync point can only be changed in one place.

  python3 timeline.py check timeline.json            # validate schema + creative plan  (exit 2 on FAIL)
  python3 timeline.py check timeline.json --json r.json
  python3 timeline.py beats timeline.json            # print the half-second beat sheet as a table
  python3 timeline.py cues  timeline.json            # print the audio cues the manifest schedules

Library use (render code and audio code):
  import timeline as TL
  T = TL.load('timeline.json')
  T.event('reveal').t                  # visual time of an event
  T.event('reveal').audio_time         # t + audio_offset (e.g. a whoosh that must start early)
  T.events(kind='impact')              # all impacts, ordered by time
  T.scene_at(3.1).id                   # which scene owns time t
  T.audio_cues()                       # [(time, cue, gain, event_id)] for every event that wants a sound
  T.in_quiet(9.8)                      # True inside a declared deliberate stillness

Schema "bke-motion-timeline/1" (see templates/timeline.example.json for a full, commented example):
  duration, fps, bpm, tolerance_ms
  polarity   {from, to, statement}                         - the transformation the story communicates
  vocabulary {from:[{effect, meaning}], to:[...], neutral:[...]}  - every effect must mean something
  accent     {color, budget_pct, reserved_for:[...]}        - one accent colour, used only for meaning
  easing     {arrive, depart, transform, pop, mechanical}  - easing chosen by narrative ROLE
  stagger    {chars_ms, items_ms, rule}
  scenes     [{id, start, end, text, pole, energy, density, emotion}]   energy: high|medium|low|rest
  beats      [{t, dominant, supporting, ambient, audio, effects:[...], read_first}]   every 0.5 s
  events     [{id, t, kind, visual, audio, audio_offset, gain, rank, sync, tolerance_ms, duration, anticipation}]
              kind: impact|transition|accent|text|reveal|anticipation ; sync: required|visual_only|audio_only
  quiet      [{start, end, reason}]                          - planned stillness (not a defect)
  audio_bed  ["kick","hat",...]                              - music-bed cue names exempt from 1:1 sync
"""
import json, sys, math, os

SCHEMA = 'bke-motion-timeline/1'
ENERGY_LEVELS = {'rest': 0, 'low': 1, 'medium': 2, 'high': 3}
EVENT_KINDS = {'impact', 'transition', 'accent', 'text', 'reveal', 'anticipation', 'camera'}   # camera: v2.1 (3D)
CAMERA_MOVES = {'dolly', 'orbit', 'crane'}
MOVES_3D = CAMERA_MOVES | {'scatter', 'snap_align', 'recede', 'focus_pull', 'light_sweep'}
SYNC_MODES = {'required', 'visual_only', 'audio_only'}
DEFAULT_BED = ['kick', 'hat', 'clap', 'pad', 'pluck', 'bass', 'drone', 'arp', 'chord', 'rumble', 'heartbeat', 'riser_bed']


class Obj(dict):
    __getattr__ = dict.get


class Event(Obj):
    @property
    def audio_time(self):
        return None if self.t is None else self.t + float(self.get('audio_offset') or 0.0)

    @property
    def tol(self):
        return float(self.get('tolerance_ms') or 34) / 1000.0


class Timeline:
    def __init__(self, data, path=None):
        self.data = data
        self.path = path
        self.duration = float(data.get('duration', 0))
        self.fps = float(data.get('fps', 30))
        self.bpm = data.get('bpm')
        self.tolerance = float(data.get('tolerance_ms', 34)) / 1000.0
        self.scenes = [Obj(s) for s in data.get('scenes', [])]
        self.beats = [Obj(b) for b in data.get('beats', [])]
        evs = []
        for e in data.get('events', []):
            e = Event(e)
            if 'tolerance_ms' not in e:
                e['tolerance_ms'] = data.get('tolerance_ms', 34)
            evs.append(e)
        self._events = sorted(evs, key=lambda e: e.get('t', 0))
        self.quiet = [Obj(q) for q in data.get('quiet', [])]
        self.audio_bed = set(data.get('audio_bed', DEFAULT_BED))

    # ---- queries used by render / audio code
    def events(self, kind=None, sync=None):
        out = self._events
        if kind: out = [e for e in out if e.kind == kind]
        if sync: out = [e for e in out if (e.sync or 'required') == sync]
        return out

    def event(self, eid):
        for e in self._events:
            if e.id == eid: return e
        raise KeyError(f'no event {eid!r} in manifest')

    def scene(self, sid):
        for s in self.scenes:
            if s.id == sid: return s
        raise KeyError(f'no scene {sid!r} in manifest')

    def scene_at(self, t):
        for s in self.scenes:
            if s.start <= t < s.end: return s
        return self.scenes[-1] if self.scenes else None

    def cuts(self):
        return [s.start for s in self.scenes[1:]]

    def in_quiet(self, t):
        return any(q.start <= t <= q.end for q in self.quiet)

    def audio_cues(self):
        """Every sound the manifest schedules: (time, cue, gain, event_id). Audio code places exactly these."""
        out = []
        for e in self._events:
            if (e.sync or 'required') == 'visual_only' or not e.audio: continue
            out.append((round(e.audio_time, 4), e.audio, float(e.get('gain') or 1.0), e.id))
        return out

    def frame(self, t):
        return int(round(t * self.fps))


def load(path):
    with open(path) as f:
        return Timeline(json.load(f), path)


# ------------------------------------------------------------------ creative plan / schema checks
def check(T):
    """Return list of (level, code, message). level in PASS/WARN/FAIL."""
    R = []
    add = lambda lvl, code, msg: R.append((lvl, code, msg))
    d = T.data
    if d.get('schema') != SCHEMA:
        add('WARN', 'schema', f"schema should be {SCHEMA!r} (got {d.get('schema')!r})")
    if T.duration <= 0: add('FAIL', 'duration', 'duration missing or <= 0')
    if abs(T.duration * T.fps - round(T.duration * T.fps)) > 1e-6:
        add('FAIL', 'frames', f'duration*fps = {T.duration * T.fps} is not a whole number of frames')

    # 1 polarity
    pol = d.get('polarity') or {}
    if not (pol.get('from') and pol.get('to') and pol.get('statement')):
        add('FAIL', 'polarity', 'polarity needs from, to and statement: what transformation does the story communicate?')
    else:
        add('PASS', 'polarity', f"{pol['from']} -> {pol['to']}")

    # 2 vocabulary: every effect has a pole and a meaning
    voc = d.get('vocabulary') or {}
    known = {}
    for pole in ('from', 'to', 'neutral'):
        for v in voc.get(pole, []):
            if not v.get('effect') or not v.get('meaning'):
                add('FAIL', 'vocabulary', f'vocabulary entry in {pole!r} lacks effect or meaning: {v}')
            else:
                known[v['effect']] = pole
    if not voc.get('from') or not voc.get('to'):
        add('FAIL', 'vocabulary', 'vocabulary needs effects for BOTH poles (from and to)')
    both = set(e['effect'] for e in voc.get('from', []) if 'effect' in e) & set(e['effect'] for e in voc.get('to', []) if 'effect' in e)
    if both:
        add('WARN', 'vocabulary', f'effects assigned to both poles blur the contrast: {sorted(both)}')

    # 3 scenes contiguous, attributes present
    sc = T.scenes
    if not sc:
        add('FAIL', 'scenes', 'no scenes')
    else:
        if abs(sc[0].start) > 1e-6: add('FAIL', 'scenes', 'first scene must start at 0')
        if abs(sc[-1].end - T.duration) > 1e-6: add('FAIL', 'scenes', 'last scene must end at duration')
        for a, b in zip(sc, sc[1:]):
            if abs(a.end - b.start) > 1e-6: add('FAIL', 'scenes', f'gap/overlap between {a.id} and {b.id}')
        for s in sc:
            miss = [k for k in ('id', 'pole', 'energy', 'density', 'emotion') if s.get(k) in (None, '')]
            if miss: add('FAIL', 'scenes', f'scene {s.id}: missing {miss}')
            if s.energy and s.energy not in ENERGY_LEVELS: add('FAIL', 'scenes', f'scene {s.id}: energy must be one of {list(ENERGY_LEVELS)}')
        # density should fall from the first 'to' scene onward (decreasing visual density toward the payoff)
        dens = [(s.id, s.density) for s in sc if isinstance(s.density, (int, float))]
        first_to = next((i for i, s in enumerate(sc) if s.pole == 'to'), None)
        if first_to is not None:
            tail = [x for x in dens if [s.id for s in sc].index(x[0]) >= first_to]
            for (ia, da), (ib, db) in zip(tail, tail[1:]):
                if db > da:
                    add('WARN', 'density', f'density rises {ia}({da}) -> {ib}({db}); it should fall toward the payoff')
        # cuts on the beat grid
        if T.bpm:
            beat = 60.0 / float(T.bpm)
            for c in T.cuts():
                off = abs(c / beat - round(c / beat)) * beat
                if off > T.tolerance:
                    add('WARN', 'beatgrid', f'cut at {c:.3f}s is {off * 1000:.0f} ms off the {T.bpm} BPM grid')

    # 4 beat sheet: every half second, exactly one dominant motion
    if not T.beats:
        add('FAIL', 'beats', 'no half-second beat sheet')
    else:
        slots = int(round(T.duration / 0.5))
        have = {int(round(b.t / 0.5)) for b in T.beats if b.t is not None}
        missing = [k * 0.5 for k in range(slots) if k not in have]
        if missing: add('FAIL', 'beats', f'beat sheet missing slots at {missing}')
        for b in T.beats:
            if not isinstance(b.dominant, str) or not b.dominant.strip():
                add('FAIL', 'beats', f't={b.t}: exactly one dominant motion (a single string) is required')
            if isinstance(b.supporting, list) and len(b.supporting) > 1:
                add('FAIL', 'beats', f't={b.t}: at most one supporting motion')
            if not b.ambient: add('WARN', 'beats', f't={b.t}: no ambient layer named (grid/grain/particles keep a frame alive)')
            for ef in b.effects or []:
                if ef not in known:
                    add('FAIL', 'meaning', f"t={b.t}: effect {ef!r} is not in the vocabulary - an effect without a meaning")
                else:
                    sp = T.scene_at(b.t)
                    pole = known[ef]
                    if sp and pole in ('from', 'to') and sp.pole in ('from', 'to') and pole != sp.pole:
                        add('WARN', 'pole', f"t={b.t}: {ef!r} belongs to the {pole!r} pole but scene {sp.id} is {sp.pole!r}")
        if not missing: add('PASS', 'beats', f'{len(T.beats)} beats cover {T.duration}s at 0.5 s resolution')

    # 5 ranked impacts
    ranked = [e for e in T.events() if e.rank is not None]
    ranks = [e.rank for e in ranked]
    if not ranked:
        add('FAIL', 'impacts', 'no ranked impacts: rank the hits by narrative importance')
    else:
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            add('FAIL', 'impacts', f'ranks must be unique 1..n, got {sorted(ranks)}')
        top = min(ranked, key=lambda e: e.rank)
        last_scene = sc[-1] if sc else None
        if last_scene and not (last_scene.start - 1e-6 <= top.t <= last_scene.end):
            add('WARN', 'impacts', f'rank-1 impact {top.id!r} is not in the final scene; the payoff usually earns the biggest hit')
        for e in ranked:
            if not e.anticipation:
                add('WARN', 'anticipation', f'impact {e.id!r} has no planned anticipation (what builds into it?)')
        a_ = sorted(ranked, key=lambda e: e.t)
        for x, y in zip(a_, a_[1:]):
            if y.t - x.t < 0.4:
                add('WARN', 'overlap', f'impacts {x.id!r} and {y.id!r} are {1000 * (y.t - x.t):.0f} ms apart; they will blur into one hit')
        add('PASS', 'impacts', 'ranked: ' + ', '.join(f'{e.rank}:{e.id}@{e.t}' for e in sorted(ranked, key=lambda e: e.rank)))

    # 6 events schema
    ids = set()
    for e in T.events():
        if not e.id: add('FAIL', 'events', f'event without id at t={e.t}')
        elif e.id in ids: add('FAIL', 'events', f'duplicate event id {e.id!r}')
        ids.add(e.id)
        if e.kind not in EVENT_KINDS: add('FAIL', 'events', f'{e.id}: kind must be one of {sorted(EVENT_KINDS)}')
        if (e.sync or 'required') not in SYNC_MODES: add('FAIL', 'events', f'{e.id}: sync must be one of {sorted(SYNC_MODES)}')
        if (e.sync or 'required') == 'required' and not e.audio:
            add('FAIL', 'events', f'{e.id}: sync=required but no audio cue named')
        if (e.sync or 'required') != 'audio_only' and not e.visual:
            add('FAIL', 'events', f'{e.id}: no visual action described')
        if e.t is None or e.t < 0 or e.t > T.duration: add('FAIL', 'events', f'{e.id}: t outside the video')

    # 7 easing by role, overshoot never on headlines
    ez = d.get('easing') or {}
    for role in ('arrive', 'depart', 'transform', 'pop'):
        if role not in ez: add('WARN', 'easing', f'easing role {role!r} not declared')
    if 'linear' in str(ez.get('arrive', '')) or 'linear' in str(ez.get('depart', '')):
        add('WARN', 'easing', 'linear arrival/departure reads mechanical; reserve linear for machines (scrolling tracks, particles)')
    if 'text' in str(ez.get('pop_targets', '')).lower() or 'headline' in str(ez.get('pop_targets', '')).lower():
        add('WARN', 'easing', 'overshoot (pop) on headlines reads cheap; keep it for small UI confirmations')

    # 8 accent budget
    ac = d.get('accent') or {}
    if not ac.get('color') or ac.get('budget_pct') is None or not ac.get('reserved_for'):
        add('FAIL', 'accent', 'accent needs color, budget_pct and reserved_for: one accent, used only where it means something')

    # 9 planned stillness
    if not T.quiet and not any(s.energy == 'rest' for s in sc):
        add('WARN', 'quiet', 'no deliberate quiet declared; contrast needs at least one planned rest (often the end card)')
    for q in T.quiet:
        if not q.reason: add('WARN', 'quiet', f'quiet {q.start}-{q.end} has no reason')

    st = d.get('stagger') or {}
    if not st: add('WARN', 'stagger', 'no stagger plan (chars_ms / items_ms)')
    check_3d(T, add)
    return R


def check_3d(T, add):
    """v2.1: rules for 3D moves (docs/3D_DECISIONS.md). Only runs when the manifest declares camera3d or move3d."""
    d = T.data; c3 = d.get('camera3d'); mv = [e for e in T.events() if e.get('move3d')]
    if not c3 and not mv: return
    if not c3:
        add('FAIL', '3d', 'move3d events need a camera3d block (lens_mm, why_3d)'); return
    if not str(c3.get('why_3d', '')).strip():
        add('FAIL', '3d', 'camera3d.why_3d is empty: real 3D only when space carries meaning, otherwise fake depth in 2D')
    lens = c3.get('lens_mm')
    if lens is None or not (35 <= float(lens) <= 50):
        add('FAIL', '3d', f'camera3d.lens_mm={lens}: use a 35-50 mm equivalent (wide lenses distort type)')
    if c3.get('lights', 1) != 1:
        add('FAIL', '3d', f"camera3d.lights={c3.get('lights')}: one accent key light plus ambient, no multi-light setups")
    if float(c3.get('max_text_tilt_deg', 20)) > 20:
        add('FAIL', '3d', 'camera3d.max_text_tilt_deg > 20: type must face the camera when it is read')
    ranks = []
    for e in mv:
        m = e.move3d
        if m.get('type') not in MOVES_3D:
            add('FAIL', '3d', f"{e.id}: move3d.type {m.get('type')!r} not in {sorted(MOVES_3D)}")
        if not str(m.get('meaning', '')).strip():
            add('FAIL', '3d', f'{e.id}: 3D move without a meaning')
        if not isinstance(m.get('rank'), int) or m['rank'] < 1:
            add('FAIL', '3d', f'{e.id}: move3d.rank must be an integer >= 1 (1 = most important 3D move)')
        else: ranks.append(m['rank'])
        if not e.audio:
            add('FAIL', '3d', f'{e.id}: every 3D move needs an audio cue (a swell for camera moves, a transient for snaps)')
        ez = str(m.get('ease', ''))
        if any(k in ez for k in ('back', 'elastic', 'bounce', 'overshoot')):
            add('FAIL', '3d', f'{e.id}: ease {ez!r} overshoots; 3D moves settle, never bounce')
        if m.get('type') in CAMERA_MOVES:
            if m.get('end') is None: add('FAIL', '3d', f'{e.id}: camera move needs an end time')
            if 'in_out' not in ez and ez not in ('eio', 'sine'):
                add('WARN', '3d', f'{e.id}: camera ease {ez!r}; use slow-in/slow-out (cubic_in_out / sine_in_out)')
            if m.get('type') == 'orbit' and float(m.get('degrees', 0)) > 25:
                add('FAIL', '3d', f"{e.id}: orbit {m.get('degrees')} deg > 25 deg")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        add('FAIL', '3d', f'move3d ranks must be unique 1..n, got {sorted(ranks)}')
    cams = [e for e in mv if e.move3d.get('type') in CAMERA_MOVES]
    for a in cams:
        for b in cams:
            if a.id < b.id and a.t < float(b.move3d.get('end', b.t)) and b.t < float(a.move3d.get('end', a.t)):
                add('FAIL', '3d', f'stacked camera moves {a.id} and {b.id}: one camera move per shot')
    shots = {}
    for e in cams:
        sc = T.scene_at(e.t); shots.setdefault(e.move3d.get('shot', sc.id if sc else ''), []).append(e.id)
    for sh, ids in shots.items():
        if len(ids) > 1: add('FAIL', '3d', f'shot {sh!r} has {len(ids)} camera moves {ids}: one per shot')
    if cams and T.scenes:
        last = T.scenes[-1]; late = [e.id for e in cams if float(e.move3d.get('end', e.t)) > last.start + 1e-6]
        if late: add('FAIL', '3d', f'camera still moving in the final scene ({late}): the end card is flat, frontal and still')
    add('PASS', '3d', f"3D plan: {len(mv)} moves, {len(cams)} camera move(s), lens {lens} mm")


def summarize(R, title='PLAN CHECK'):
    lines = [title]
    for lvl, code, msg in R:
        if lvl != 'PASS' or code in ('polarity', 'beats', 'impacts', '3d'):
            lines.append(f'{lvl:4s}  [{code}] {msg}')
    nf = sum(1 for r in R if r[0] == 'FAIL'); nw = sum(1 for r in R if r[0] == 'WARN')
    res = 'FAIL' if nf else ('WARN' if nw else 'PASS')
    lines.append(f'RESULT: {res} ({nf} fail, {nw} warn)')
    return '\n'.join(lines), res


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('check', 'beats', 'cues'):
        print(__doc__); sys.exit(2)
    T = load(a[1])
    if a[0] == 'check':
        R = check(T)
        txt, res = summarize(R)
        print(txt)
        if '--json' in a:
            with open(a[a.index('--json') + 1], 'w') as f:
                json.dump({'result': res, 'items': [dict(level=l, code=c, message=m) for l, c, m in R]}, f, indent=1)
        sys.exit(2 if res == 'FAIL' else 0)
    if a[0] == 'beats':
        print(f"{'t':>5} | {'scene':10} | {'dominant':40} | {'supporting':28} | audio")
        for b in sorted(T.beats, key=lambda b: b.t):
            s = T.scene_at(b.t)
            print(f"{b.t:5.1f} | {(s.id if s else ''):10} | {str(b.dominant)[:40]:40} | {str(b.supporting or '')[:28]:28} | {b.audio or ''}")
    if a[0] == 'cues':
        for t, cue, g, eid in T.audio_cues():
            print(f'{t:7.3f}  {cue:10} gain={g:.2f}  <- {eid}')


if __name__ == '__main__':
    main()
