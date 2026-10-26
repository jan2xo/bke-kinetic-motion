import copy, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import sync_check as SC, timeline as TL

BASE = {"schema": TL.SCHEMA, "duration": 4.0, "fps": 30, "bpm": 120, "tolerance_ms": 34,
        "events": [
            {"id": "hit", "t": 2.0, "kind": "impact", "visual": "flash", "audio": "impact", "rank": 1, "sync": "required"},
            {"id": "tick", "t": 1.0, "kind": "accent", "visual": "card lands", "audio": "glitch", "sync": "required"},
            {"id": "whip", "t": 3.0, "kind": "transition", "visual": "whip", "audio": "whoosh", "audio_offset": -0.12, "sync": "required"},
            {"id": "title", "t": 2.2, "kind": "text", "visual": "title rises", "sync": "visual_only"}],
        "audio_bed": ["kick", "pad", "hat"]}
GOOD = [{"t": 1.0, "cue": "glitch"}, {"t": 2.0, "cue": "impact"}, {"t": 2.88, "cue": "whoosh"}, {"t": 2.0, "cue": "kick"}, {"t": 0.0, "cue": "pad"}]


def run(cues, manifest=None, vlog=None):
    T = TL.Timeline(copy.deepcopy(manifest or BASE))
    checks, _ = SC.declared(T, cues, vlog)
    return checks


def codes(checks, level=None):
    return [c['code'] for c in checks if level is None or c['level'] == level]


class Sync(unittest.TestCase):
    def test_clean_schedule_passes(self):
        ch = run(GOOD)
        self.assertEqual(codes(ch, 'FAIL') + codes(ch, 'WARN'), [], ch)

    def test_audio_offset_is_honoured(self):   # whoosh starts 120 ms early by design
        ch = run(GOOD)
        self.assertIn('synced', [c['code'] for c in ch if c.get('event') == 'whip'])

    def test_missing_sfx(self):
        ch = run([c for c in GOOD if c['cue'] != 'glitch'])
        self.assertIn('missing_sfx', codes(ch, 'FAIL'))

    def test_orphan_audio(self):
        ch = run(GOOD + [{"t": 0.61, "cue": "glitch"}])
        self.assertIn('orphan_audio', codes(ch, 'FAIL'))

    def test_bed_cues_are_not_orphans(self):
        ch = run(GOOD + [{"t": 0.5, "cue": "kick"}, {"t": 0.75, "cue": "hat"}])
        self.assertNotIn('orphan_audio', codes(ch))

    def test_drift_beyond_tolerance(self):
        cues = [dict(c) for c in GOOD]; cues[1]['t'] = 2.06
        ch = run(cues)
        self.assertIn('drift', codes(ch, 'FAIL'))

    def test_within_tolerance_is_synced(self):
        cues = [dict(c) for c in GOOD]; cues[1]['t'] = 2.02
        self.assertNotIn('drift', codes(run(cues)))

    def test_double_trigger_overlap(self):
        ch = run(GOOD + [{"t": 1.02, "cue": "glitch"}])
        self.assertIn('overlap', codes(ch, 'WARN'))

    def test_visual_only_must_stay_silent(self):
        ch = run(GOOD + [{"t": 2.2, "cue": "glitch", "event_id": "title"}])
        self.assertIn('visual_only_has_audio', codes(ch, 'WARN'))

    def test_unrendered_visual_event(self):
        vlog = [{"event_id": "hit", "t": 2.0}, {"event_id": "tick", "t": 1.0}, {"event_id": "whip", "t": 3.0}]   # title missing
        ch = run(GOOD, vlog=vlog)
        self.assertIn('unrendered', codes(ch, 'FAIL'))

    def test_undeclared_visual_event(self):
        vlog = [{"event_id": k, "t": t} for k, t in (("hit", 2.0), ("tick", 1.0), ("whip", 3.0), ("title", 2.2), ("surprise", 1.5))]
        self.assertIn('undeclared', codes(run(GOOD, vlog=vlog), 'WARN'))

    def test_drift_trend(self):
        m = copy.deepcopy(BASE)
        m['events'] = [{"id": f"e{k}", "t": float(k), "kind": "accent", "visual": "x", "audio": "glitch", "sync": "required", "tolerance_ms": 40}
                       for k in range(4)]
        cues = [{"t": k + 0.012 * k, "cue": "glitch"} for k in range(4)]   # 12 ms per second creep
        ch = run(cues, m)
        self.assertIn('drift_trend', codes(ch, 'WARN'))

    def test_event_id_matching_beats_nearest(self):
        cues = [{"t": 1.0, "cue": "glitch", "event_id": "tick"}, {"t": 2.0, "cue": "impact", "event_id": "hit"},
                {"t": 2.88, "cue": "whoosh", "event_id": "whip"}]
        self.assertEqual(codes(run(cues), 'FAIL'), [])


class Plan(unittest.TestCase):
    def manifest(self):
        p = os.path.join(HERE, '..', 'templates', 'timeline.json')
        return TL.load(p).data

    def test_template_plan_passes(self):
        R = TL.check(TL.Timeline(self.manifest()))
        self.assertFalse([r for r in R if r[0] == 'FAIL'], R)

    def test_effect_without_meaning_fails(self):
        d = self.manifest(); d['beats'][0]['effects'].append('lens_flare')
        self.assertIn('meaning', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'FAIL'])

    def test_missing_beat_slot_fails(self):
        d = self.manifest(); d['beats'] = d['beats'][:-1]
        self.assertIn('beats', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'FAIL'])

    def test_two_dominant_motions_fail(self):
        d = self.manifest(); d['beats'][2]['dominant'] = ['a', 'b']
        self.assertIn('beats', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'FAIL'])

    def test_density_must_fall(self):
        d = self.manifest(); d['scenes'][2]['density'] = 99
        self.assertIn('density', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'WARN'])

    def test_payoff_should_be_rank_one(self):
        d = self.manifest()
        for e in d['events']:
            if e.get('rank') == 1: e['rank'] = 2
            elif e.get('rank') == 2: e['rank'] = 1
        self.assertIn('impacts', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'WARN'])

    def test_no_planned_quiet_warns(self):
        d = self.manifest(); d['quiet'] = []
        self.assertIn('quiet', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'WARN'])

    def test_required_sync_needs_audio(self):
        d = self.manifest(); d['events'][1].pop('audio')
        self.assertIn('events', [c for l, c, m in TL.check(TL.Timeline(d)) if l == 'FAIL'])


if __name__ == '__main__':
    unittest.main()
