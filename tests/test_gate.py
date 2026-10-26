"""Gate tests: the GPT draft that shipped a flat sketch must FAIL; kit builds must not."""
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import gate  # noqa: E402
import timeline as TL  # noqa: E402


def run_static(render, manifest):
    R = gate.Report(); T = TL.load(manifest)
    gate.stage_plan(T, R); gate.stage_engine(T, render, R)
    return R


def codes(R, level):
    return {i['code'] for i in R.items if i['level'] == level}


class TestStaticGate(unittest.TestCase):
    def test_gpt_draft_fails(self):
        R = run_static(os.path.join(HERE, 'fixtures', 'gpt_draft_render.py'), os.path.join(HERE, 'fixtures', 'gpt_draft_timeline.json'))
        self.assertEqual(R.result(), 'FAIL')
        fails = codes(R, 'FAIL')
        for c in ('camera3d', 'typography', 'finish', 'visual_log', 'supersample', 'unimplemented', 'manifest_load'):
            self.assertIn(c, fails, c)

    def test_3d_template_passes(self):
        R = run_static(os.path.join(ROOT, 'templates', 'promo_3d_template.py'), os.path.join(ROOT, 'templates', 'timeline_3d.json'))
        self.assertEqual(R.result(), 'PASS', R.items)

    def test_render_dock_project_passes(self):
        d = os.path.join(ROOT, 'projects', 'render-dock-15s')
        R = run_static(os.path.join(d, 'render.py'), os.path.join(d, 'timeline.json'))
        self.assertNotEqual(R.result(), 'FAIL', R.items)

    def test_every_project_is_gated(self):
        pd = os.path.join(ROOT, 'projects')
        for name in sorted(os.listdir(pd)):
            r, m = os.path.join(pd, name, 'render.py'), os.path.join(pd, name, 'timeline.json')
            if os.path.exists(r):
                self.assertTrue(os.path.exists(m), f'{name}: render.py without timeline.json')
                self.assertNotEqual(run_static(r, m).result(), 'FAIL', name)

    def test_missing_event_reference_fails(self):
        tmp = tempfile.mkdtemp()
        try:
            src = open(os.path.join(ROOT, 'templates', 'promo_3d_template.py')).read().replace("'rim_sweep'", "'rim_swxxp'")
            p = os.path.join(tmp, 'render.py'); open(p, 'w').write(src)
            R = run_static(p, os.path.join(ROOT, 'templates', 'timeline_3d.json'))
            flagged = [i for i in R.items if i['code'] in ('unimplemented', 'query_driven') and 'rim_sweep' in i['message']]
            self.assertTrue(flagged, R.items)
        finally:
            shutil.rmtree(tmp)


class TestMapGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.T = TL.load(os.path.join(ROOT, 'templates', 'timeline_3d.json'))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write(self, vlog, cues):
        json.dump(vlog, open(os.path.join(self.tmp, 'visual_log.json'), 'w'))
        json.dump(cues, open(os.path.join(self.tmp, 'audio_cues.json'), 'w'))

    def _full(self):
        vlog = [dict(event_id=e.id, t=e.t) for e in gate.visual_events(self.T)]
        cues = [dict(t=e.audio_time, cue=e.audio, event_id=e.id) for e in gate.sound_events(self.T)]
        return vlog, cues

    def test_complete_map_passes(self):
        self._write(*self._full()); R = gate.Report(); gate.stage_map(self.T, self.tmp, R)
        self.assertEqual(R.result(), 'PASS', R.items)

    def test_unrendered_event_fails(self):
        vlog, cues = self._full(); self._write(vlog[1:], cues)
        R = gate.Report(); gate.stage_map(self.T, self.tmp, R)
        self.assertIn('unrendered', codes(R, 'FAIL'))

    def test_silent_event_fails(self):
        vlog, cues = self._full(); self._write(vlog, cues[1:])
        R = gate.Report(); gate.stage_map(self.T, self.tmp, R)
        self.assertIn('silent_event', codes(R, 'FAIL'))

    def test_undeclared_and_drift_fail(self):
        vlog, cues = self._full(); vlog.append(dict(event_id='ghost', t=1.0)); vlog[0]['t'] += 0.5
        self._write(vlog, cues); R = gate.Report(); gate.stage_map(self.T, self.tmp, R)
        self.assertIn('undeclared', codes(R, 'FAIL')); self.assertIn('visual_drift', codes(R, 'FAIL'))

    def test_no_video_fails(self):
        R = gate.Report(); gate.stage_render(self.T, self.tmp, None, R)
        self.assertIn('no_video', codes(R, 'FAIL'))


if __name__ == '__main__':
    unittest.main()
