import json, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts')); sys.path.insert(0, HERE)
import motion_energy as ME, timeline as TL, synth

CFG = dict(ME.BASE); CFG.update(ME.STYLES['kinetic'])
TMP = tempfile.mkdtemp(prefix='kmqa_')


def run(path, manifest=None, cfg=None, fps=None):
    meta, rows = ME.analyse(path, CFG['analysis_width'], fps)
    return ME.judge(meta, rows, dict(cfg or CFG), manifest)


def mk_manifest(d):
    base = {"schema": TL.SCHEMA, "duration": 4.5, "fps": 30, "scenes": [], "events": [], "quiet": []}
    base.update(d)
    return TL.Timeline(base)


def holds(rep, status=None):
    return [h for h in rep['holds'] if status is None or h['status'] == status]


class MotionEnergy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S = (640, 360)
        cls.constant = synth.render(f'{TMP}/constant.mp4', 4.5, 30, S, synth.mover([(0, 4.5, True)]))
        cls.still = synth.render(f'{TMP}/still.mp4', 4.5, 30, S, synth.mover([(0, 1.5, True), (1.5, 3.0, False), (3.0, 4.5, True)]))
        cls.endcard = synth.render(f'{TMP}/endcard.mp4', 4.5, 30, S, synth.mover([(0, 3.4, True), (3.4, 4.5, False)], flash_at=(3.0,)))
        cls.flash = synth.render(f'{TMP}/flash.mp4', 3.0, 30, S, synth.mover([(0, 3.0, True)], flash_at=(1.0,)))
        cls.pan = synth.render(f'{TMP}/pan.mp4', 3.0, 30, S, synth.texture_pan(360, S), grain=1.0)
        cls.hi = synth.render(f'{TMP}/hi60.mp4', 4.5, 60, (1280, 720), synth.mover([(0, 4.5, True)]))

    def test_constant_motion_has_no_hold(self):
        rep = run(self.constant)
        self.assertEqual(holds(rep), [], rep['holds'])
        self.assertNotEqual(rep['result'], 'FAIL')

    def test_undeclared_still_fails(self):
        rep = run(self.still)
        f = holds(rep, 'FAIL')
        self.assertEqual(len(f), 1, rep['holds'])
        self.assertAlmostEqual(f[0]['start'], 1.5, delta=0.15)
        self.assertAlmostEqual(f[0]['end'], 3.0, delta=0.15)
        self.assertEqual(rep['result'], 'FAIL')

    def test_declared_quiet_is_not_a_failure(self):
        m = mk_manifest({"quiet": [{"start": 1.5, "end": 3.0, "reason": "planned breath"}]})
        rep = run(self.still, m)
        self.assertEqual(holds(rep, 'FAIL') + holds(rep, 'WARN'), [], rep['holds'])
        self.assertEqual(len(holds(rep, 'INTENTIONAL')), 1)
        self.assertNotEqual(rep['result'], 'FAIL')

    def test_end_card_after_final_impact_is_intentional(self):
        m = mk_manifest({"events": [{"id": "payoff", "t": 3.0, "kind": "impact", "rank": 1, "visual": "flash", "audio": "impact"}]})
        rep = run(self.endcard, m)
        self.assertEqual(holds(rep, 'FAIL') + holds(rep, 'WARN'), [], rep['holds'])
        self.assertTrue(any('end-card' in (h['reason'] or '') for h in holds(rep, 'INTENTIONAL')), rep['holds'])

    def test_end_card_too_long_still_flagged(self):
        cfg = dict(CFG); cfg['end_card_max'] = 0.5
        m = mk_manifest({"events": [{"id": "payoff", "t": 3.0, "kind": "impact", "rank": 1, "visual": "flash", "audio": "impact"}]})
        rep = run(self.endcard, m, cfg)
        self.assertTrue(holds(rep, 'FAIL') or holds(rep, 'WARN'), rep['holds'])

    def test_grain_does_not_hide_a_hold(self):
        rep = run(self.still)   # the still section carries sigma-3 grain every frame
        self.assertGreater(rep['thresholds']['noise_floor'], 0.05)
        self.assertTrue(holds(rep, 'FAIL'))

    def test_flash_detected_and_classified(self):
        rep = run(self.flash)
        top = max(rep['peaks'], key=lambda p: p['energy'])
        self.assertAlmostEqual(top['t'], 1.0, delta=0.05)
        self.assertEqual(top['kind'], 'flash')

    def test_impact_missing_is_a_failure(self):
        m = mk_manifest({"duration": 4.5, "events": [{"id": "ghost", "t": 2.2, "kind": "impact", "rank": 1, "visual": "x", "audio": "impact"}]})
        rep = run(self.constant, m)
        self.assertTrue(any(c['code'] == 'impact_missing' for c in rep['checks']))

    def test_camera_pan_is_recognised_as_camera(self):
        rep = run(self.pan)
        cam = [r for r in rep['series']['camera_px'] if r > 3]
        self.assertGreater(len(cam), 0.8 * len(rep['series']['camera_px']), 'phase correlation should see the pan')
        self.assertTrue(any(c['code'] == 'camera_only' for c in rep['checks']), [c['code'] for c in rep['checks']])
        self.assertEqual(holds(rep), [], 'a pan is motion, not a hold')

    def test_fps_and_resolution_normalisation(self):
        a = run(self.constant); b = run(self.hi)
        ma = sum(a['series']['activity'][15:120]) / 105 - a['thresholds']['noise_floor']
        mb = sum(b['series']['activity'][30:240]) / 210 - b['thresholds']['noise_floor']
        self.assertLess(abs(ma - mb) / ma, 0.35, (ma, mb))

    def test_energy_order_and_sag(self):
        m = mk_manifest({"scenes": [
            {"id": "a", "start": 0, "end": 1.5, "energy": "medium"},
            {"id": "b", "start": 1.5, "end": 3.0, "energy": "high"},
            {"id": "c", "start": 3.0, "end": 4.5, "energy": "medium"}]})
        rep = run(self.still, m)
        codes = [c['code'] for c in rep['checks']]
        self.assertIn('energy_order', codes); self.assertIn('energy_sag', codes)


if __name__ == '__main__':
    unittest.main()
