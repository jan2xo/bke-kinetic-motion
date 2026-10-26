"""Regression fixtures from the v1 Render Dock render (proxy re-encode, 640x360; the original file is untouched).
The three defects v1 shipped with must stay detectable, and the v2 manifest-driven audio must clear the sync one."""
import json, os, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import motion_energy as ME, sync_check as SC, timeline as TL

PROXY = os.path.join(HERE, 'fixtures', 'renderdock_v1_proxy360.mp4')
CUES = os.path.join(HERE, 'fixtures', 'renderdock_v1_audio_cues.json')
MAN = os.path.join(ROOT, 'examples', 'render_dock', 'timeline.json')
FULL = os.environ.get('RENDERDOCK_FULL')   # optional: path to the original 1080p render


def motion(path):
    T = TL.load(MAN); cfg = dict(ME.BASE); cfg.update(ME.STYLES['kinetic'])
    meta, rows = ME.analyse(path, cfg['analysis_width'])
    return ME.judge(meta, rows, cfg, T)


class RenderDockV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = motion(PROXY)

    def test_dead_hold_2_8_to_3_9(self):
        f = [h for h in self.rep['holds'] if h['status'] == 'FAIL']
        self.assertEqual(len(f), 1, self.rep['holds'])
        self.assertLess(abs(f[0]['start'] - 2.85), 0.15); self.assertLess(abs(f[0]['end'] - 3.88), 0.15)

    def test_chaos_energy_sag(self):
        sag = [c for c in self.rep['checks'] if c['code'] == 'energy_sag']
        self.assertTrue(sag, [c['code'] for c in self.rep['checks']])
        self.assertEqual(sag[0]['scene'], 'chaos'); self.assertAlmostEqual(sag[0]['start'], 1.0)

    def test_end_card_is_not_a_false_failure(self):
        last = [h for h in self.rep['holds'] if h['end'] >= 9.9]
        self.assertTrue(all(h['status'] == 'INTENTIONAL' for h in last), last)

    def test_impacts_follow_narrative_rank(self):
        self.assertIn('impact_rank', [c['code'] for c in self.rep['checks'] if c['level'] == 'PASS'])
        top3 = sorted(self.rep['peaks'], key=lambda p: -p['energy'])[:3]
        self.assertEqual([round(p['t'], 2) for p in top3], [8.5, 2.0, 6.5])

    def test_random_glitch_sounds_are_caught(self):
        ch, _ = SC.declared(TL.load(MAN), json.load(open(CUES)))
        orph = [c for c in ch if c['code'] == 'orphan_audio']
        self.assertGreaterEqual(len(orph), 9)
        self.assertTrue(all(0.3 <= c['t'] <= 1.9 for c in orph))
        self.assertIn('glitch_2', [c.get('event') for c in ch if c['code'] == 'missing_sfx'])

    def test_v2_manifest_audio_clears_the_sync_defect(self):
        d = tempfile.mkdtemp()
        subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'music_synth.py'), '--manifest', MAN,
                        '--out', f'{d}/m.wav', '--cue-log', f'{d}/c.json'], check=True, capture_output=True)
        ch, _ = SC.declared(TL.load(MAN), json.load(open(f'{d}/c.json')))
        self.assertEqual([c for c in ch if c['level'] in ('FAIL', 'WARN')], [])

    def test_manifest_audio_is_deterministic_and_tagged(self):
        d = tempfile.mkdtemp(); logs = []
        for k in range(2):
            subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'music_synth.py'), '--manifest', MAN,
                            '--out', f'{d}/m{k}.wav', '--cue-log', f'{d}/c{k}.json'], check=True, capture_output=True)
            logs.append(json.load(open(f'{d}/c{k}.json')))
        self.assertEqual(logs[0], logs[1])
        bed = set(TL.load(MAN).audio_bed)
        self.assertTrue(all(c.get('event_id') for c in logs[0] if c['cue'] not in bed))

    @unittest.skipUnless(FULL and os.path.exists(FULL or ''), 'set RENDERDOCK_FULL to the original 1080p render')
    def test_full_resolution_agrees(self):
        rep = motion(FULL)
        f = [h for h in rep['holds'] if h['status'] == 'FAIL']
        self.assertEqual(len(f), 1); self.assertLess(abs(f[0]['start'] - 2.85), 0.15)
        self.assertTrue([c for c in rep['checks'] if c['code'] == 'energy_sag'])


if __name__ == '__main__':
    unittest.main()
