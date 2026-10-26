"""v2.1 3D module tests: projection maths, depth sort, culling, depth of field, lint rules, 3D plan check,
and a camera-only dolly rendered with mg3d being classified as camera motion by motion_energy.py."""
import json, math, os, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import numpy as np
from PIL import Image
import mglib as M, mg3d as G, motion_energy as ME, timeline as TL

TMP = tempfile.mkdtemp(prefix='mg3d_')


def tex(w=200, h=120, seed=0):
    r = np.random.default_rng(seed)
    a = (r.random((h // 8 + 1, w // 8 + 1, 3)) * 200 + 30).astype(np.uint8)
    a = np.kron(a, np.ones((8, 8, 1), np.uint8))[:h, :w]
    return Image.fromarray(np.dstack([a, np.full((h, w), 255, np.uint8)]), 'RGBA')


class Projection(unittest.TestCase):
    def setUp(self): M.configure(W=1920, H=1080, S=1)

    def test_point_on_axis_lands_at_frame_centre(self):
        for pos, tgt in [((0, 0, 1800), (0, 0, 0)), ((300, -200, 900), (-50, 40, -700)), ((0, 900, 0.0), (0, 0, -1))]:
            cam = G.Camera(pos, tgt, lens_mm=40)
            p = np.array(pos, float) + (np.array(tgt, float) - np.array(pos, float)) * 2.7
            s, z = cam.project(p[None])
            self.assertAlmostEqual(s[0, 0], 960, places=6); self.assertAlmostEqual(s[0, 1], 540, places=6)
            self.assertGreater(z[0], 0)

    def test_fov_scaling(self):
        # an object of height h at distance d covers h * fpx / d pixels, fpx = (H/2) / tan(fov/2)
        for fov in (27.0, 33.4, 37.8):
            cam = G.Camera((0, 0, 1000), (0, 0, 0), fov=fov)
            s, _ = cam.project(np.array([[0, 100, 0], [0, -100, 0]], float))
            exp = 200 * (540 / math.tan(math.radians(fov) / 2)) / 1000
            self.assertAlmostEqual(s[1, 1] - s[0, 1], exp, places=6)
        a = G.Camera((0, 0, 1000), fov=40).project(np.array([[0, 100, 0]], float))[0][0, 1]
        b = G.Camera((0, 0, 1000), fov=20).project(np.array([[0, 100, 0]], float))[0][0, 1]
        ra, rb = 540 - a, 540 - b
        self.assertAlmostEqual(rb / ra, math.tan(math.radians(20)) / math.tan(math.radians(10)), places=6)

    def test_design_distance_maps_one_unit_to_one_pixel(self):
        d = G.Camera.design_distance(lens_mm=40)
        cam = G.Camera((0, 0, d), lens_mm=40)
        s, _ = cam.project(np.array([[-120, 0, 0], [120, 0, 0]], float))
        self.assertAlmostEqual(s[1, 0] - s[0, 0], 240, places=6)

    def test_lens_mm_equivalence(self):
        self.assertAlmostEqual(G.fov_from_mm(50), 26.99, places=1)
        self.assertAlmostEqual(G.fov_from_mm(35), 37.85, places=1)
        self.assertAlmostEqual(G.mm_from_fov(G.fov_from_mm(42)), 42, places=6)

    def test_matrices_agree_with_project(self):
        cam = G.Camera((200, 150, 1200), (0, 0, 0), lens_mm=45)
        P = np.array([[100, -50, 30], [-300, 200, -400]], float)
        s, _ = cam.project(P)
        h = np.c_[P, np.ones(2)] @ (cam.projection_matrix() @ cam.view_matrix()).T
        ndc = h[:, :3] / h[:, 3:4]
        sx = (ndc[:, 0] + 1) / 2 * 1920; sy = (1 - ndc[:, 1]) / 2 * 1080
        np.testing.assert_allclose(np.c_[sx, sy], s, atol=1e-6)

    def test_perspective_warp_lands_on_projected_quad(self):
        M.configure(W=640, H=360, S=1)
        d = G.Camera.design_distance(lens_mm=40, H=360); cam = G.Camera((0, 0, d), lens_mm=40)
        base = Image.new('RGBA', (640, 360), (0, 0, 0, 255))
        card = G.Card(Image.new('RGBA', (100, 60), (255, 255, 255, 255)), (200, 120), (40, 0, 0))
        G.Renderer(cam).draw_card(base, card)
        a = np.asarray(base)[..., 0] > 128; ys, xs = np.nonzero(a)
        self.assertLessEqual(abs(xs.min() - (320 + 40 - 100)), 1); self.assertLessEqual(abs(xs.max() - (320 + 40 + 100 - 1)), 1)
        self.assertLessEqual(abs(ys.min() - (180 - 60)), 1); self.assertLessEqual(abs(ys.max() - (180 + 60 - 1)), 1)
        M.configure(W=1920, H=1080, S=2)


class RenderDecisions(unittest.TestCase):
    def setUp(self):
        M.configure(W=1920, H=1080, S=1)
        self.cam = G.Camera((0, 0, 1800), (0, 0, 0), lens_mm=40)
        self.t = tex()

    def test_depth_sort_back_to_front(self):
        R = G.Renderer(self.cam)
        cards = [G.Card(self.t, (200, 120), (0, 0, z), name=str(z)) for z in (300, -900, 0, 1200, -2500)]
        order = [c.name for c in R.sort(cards)]
        self.assertEqual(order, ['-2500', '-900', '0', '300', '1200'])
        # depth is along the view axis, not straight-line distance: an off-axis near card still draws last
        a = G.Card(self.t, (200, 120), (1500, 0, 600), name='side_near'); b = G.Card(self.t, (200, 120), (0, 0, 400), name='axis_far')
        self.assertEqual([c.name for c in R.sort([a, b])], ['axis_far', 'side_near'])

    def test_culling(self):
        R = G.Renderer(self.cam)
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (0, 0, 0)))[0], 'draw')
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (0, 0, 2400)))[0], 'behind')          # behind the lens
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (0, 0, 1780)))[0], 'behind')          # straddles the near plane
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (0, 0, 0), rot=(0, 90, 0)))[0], 'edge')
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (0, 0, 0), rot=(0, 60, 0)))[0], 'draw')
        self.assertEqual(R.classify(G.Card(self.t, (200, 120), (6000, 0, 0)))[0], 'offscreen')
        base = M.canvas(); info = R.render(base, [G.Card(self.t, (200, 120), (0, 0, 0), name='ok'), G.Card(self.t, (200, 120), (0, 0, 2400), name='gone')])
        self.assertEqual([i['name'] for i in info], ['ok']); self.assertEqual(R.stats['culled_behind'], 1)

    def test_dof_blur_rises_with_distance_from_focus(self):
        R = G.Renderer(self.cam, dof=dict(focus=1800, max_px=8, bands=5, aperture=1.0, full_at=0.55))
        self.assertEqual(R.dof_radius(1800), 0.0)
        far = [R.dof_radius(z) for z in (1800, 2000, 2400, 3000, 4000, 6000, 12000)]
        near = [R.dof_radius(z) for z in (1800, 1500, 1200, 900, 600)]
        for seq in (far, near):
            self.assertTrue(all(b >= a for a, b in zip(seq, seq[1:])), seq)
            self.assertGreater(seq[-1], seq[0])
        vals = {R.dof_radius(z) for z in np.linspace(200, 20000, 400)}
        self.assertLessEqual(len(vals), 5)                     # quantised to z-bands
        # rendered: a far card is measurably softer than an in-focus one
        def sharp(z):
            base = Image.new('RGBA', (1920, 1080), (0, 0, 0, 255))
            R.draw_card(base, G.Card(tex(400, 240, 3), (400, 240), (0, 0, z)))
            g = np.asarray(base.convert('L'), np.float32); return float(np.abs(np.diff(g, axis=1)).mean())
        self.assertGreater(sharp(0) / (G.Camera.design_distance(lens_mm=40) / 1800), sharp(-2200) * 1.5)

    def test_fog_and_rim_respond_to_depth_and_angle(self):
        R = G.Renderer(self.cam, fog=dict(near=2000, far=6000, max=0.7), light=dict(pos=(0, 0, 3000), rim=0.8))
        self.assertEqual(R.fog_amount(1500), 0.0); self.assertAlmostEqual(R.fog_amount(6000), 0.7)
        c = G.Card(self.t, (200, 120), (0, 0, 0))
        _, rim_front = R.light_terms(c, c.normal())
        c2 = c.with_xf(rot=(0, 60, 0)); _, rim_graze = R.light_terms(c2, c2.normal())
        self.assertGreater(rim_graze, 0)                      # grazing view brightens the edge (key still lights it)
        self.assertGreater(rim_front, 0)


class Rules(unittest.TestCase):
    def test_lint_rig(self):
        ok = G.CameraRig('dolly', 0, 2, lens_mm=40, **{'from': (0, 0, 3000), 'to': (0, 0, 1800)})
        self.assertEqual(G.lint_rig([ok])[0][0], 'PASS')
        orbit = G.CameraRig('orbit', 1, 3, lens_mm=40, radius=1800, az0=0, az1=20)
        self.assertTrue(any(l == 'FAIL' and 'stacked' in m for l, m in G.lint_rig([ok, orbit])))
        wide = G.CameraRig('dolly', 0, 2, lens_mm=24, **{'from': (0, 0, 3000), 'to': (0, 0, 1800)})
        self.assertTrue(any(l == 'FAIL' and 'lens' in m for l, m in G.lint_rig([wide])))
        jolt = G.CameraRig('dolly', 0, 2, lens_mm=40, ease='linear', **{'from': (0, 0, 3000), 'to': (0, 0, 1800)})
        self.assertTrue(any(l == 'FAIL' and 'abrupt' in m for l, m in G.lint_rig([jolt])))
        with self.assertRaises(ValueError): G.CameraRig('orbit', 0, 2, radius=1800, az0=0, az1=40)
        with self.assertRaises(ValueError): G.CameraRig('dolly', 0, 2, ease='back_out', **{'from': (0, 0, 1), 'to': (0, 0, 2)})

    def test_text_tilt_rule(self):
        cam = G.Camera((0, 0, 1800)); t = tex()
        self.assertEqual(G.check_readable([G.Card(t, None, (600, 300, 0), is_text=True)], cam)[0][0], 'PASS')   # off-centre but frontal
        self.assertEqual(G.check_readable([G.Card(t, None, (0, 0, 0), rot=(0, 15, 0), is_text=True)], cam)[0][0], 'PASS')
        self.assertEqual(G.check_readable([G.Card(t, None, (0, 0, 0), rot=(0, 25, 0), is_text=True)], cam)[0][0], 'FAIL')

    def test_3d_plan_check(self):
        man = os.path.join(ROOT, 'templates', 'timeline_3d.json')
        R = TL.check(TL.load(man)); self.assertEqual([r for r in R if r[0] != 'PASS'], [])
        d = json.load(open(man))
        bad = json.loads(json.dumps(d))
        bad['events'].append({"id": "orbit2", "t": 1.0, "kind": "camera", "visual": "orbit", "audio": "whoosh", "sync": "required",
                              "move3d": {"type": "orbit", "end": 2.0, "degrees": 30, "ease": "cubic_in_out", "rank": 5, "meaning": "x"}})
        codes = [m for l, c, m in TL.check(TL.Timeline(bad)) if l == 'FAIL' and c == '3d']
        self.assertTrue(any('stacked' in m for m in codes), codes); self.assertTrue(any('> 25' in m for m in codes), codes)
        bad2 = json.loads(json.dumps(d)); bad2['camera3d']['lens_mm'] = 24; bad2['events'][0]['move3d'].pop('meaning')
        codes = [m for l, c, m in TL.check(TL.Timeline(bad2)) if l == 'FAIL' and c == '3d']
        self.assertTrue(any('35-50' in m for m in codes)); self.assertTrue(any('meaning' in m for m in codes))

    def test_template_logs_every_manifest_event(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'templates', 'promo_3d_template.py'), 'vlog'], cwd=TMP, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        logged = {v['event_id'] for v in json.load(open(os.path.join(TMP, 'visual_log.json')))}
        self.assertEqual(logged, {e.id for e in TL.load(os.path.join(ROOT, 'templates', 'timeline_3d.json')).events()})


class DollyIsCamera(unittest.TestCase):
    """A camera-only dolly (nothing moves in the world) must read as camera motion, not choreography."""
    @classmethod
    def setUpClass(cls):
        M.configure(W=640, H=360, S=1)
        d = G.Camera.design_distance(lens_mm=40, H=360)
        rig = G.CameraRig('dolly', 0.0, 3.0, lens_mm=40, ease='eio', **{'from': (0, 0, d * 1.9), 'to': (0, 0, d)})
        wall = [G.Card(tex(180, 110, i), (180, 110), w['pos']) for i, w in enumerate(G.card_wall(24, 6, (200, 130)))]
        cls.path = os.path.join(TMP, 'dolly.mp4')
        p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '640x360', '-r', '30', '-i', '-',
                              '-c:v', 'libx264', '-crf', '16', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', cls.path], stdin=subprocess.PIPE)
        for i in range(90):
            t = i / 30; cam = rig.at(t, W=640, H=360); base = M.canvas()
            G.Renderer(cam).render(base, wall)
            p.stdin.write(M.finish(M.to_output(base), i, grain=1.0).tobytes())
        p.stdin.close(); p.wait()
        cfg = dict(ME.BASE); cfg.update(ME.STYLES['kinetic'])
        meta, rows = ME.analyse(cls.path, cfg['analysis_width'])
        cls.rows = rows; cls.rep = ME.judge(meta, rows, cfg)
        M.configure(W=1920, H=1080, S=2)

    def test_zoom_is_measured_in_the_moving_middle(self):
        mid = self.rows[25:65]
        zoomed = [r for r in mid if r['cam_zoom'] > 1.002]
        self.assertGreater(len(zoomed), 0.8 * len(mid), [r['cam_zoom'] for r in mid])

    def test_classified_as_camera_only(self):
        self.assertTrue(any(c['code'] == 'camera_only' for c in self.rep['checks']), [c['code'] for c in self.rep['checks']])
        cam = self.rep['series']['camera_px'][25:65]
        self.assertGreater(sum(v >= 1.0 for v in cam), 0.8 * len(cam))

    def test_residual_after_zoom_is_small(self):
        mid = self.rows[25:65]
        ratio = np.mean([r['residual'] for r in mid]) / np.mean([r['luma'] for r in mid])
        self.assertLess(ratio, 0.5, ratio)


if __name__ == '__main__':
    unittest.main()
