"""SKILL.md must keep pointing agents at the PR + Actions workflow, never at local renders or main."""
import os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSkillContract(unittest.TestCase):
    def setUp(self):
        self.s = open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8').read()

    def test_points_to_pr_and_actions(self):
        for needle in ('pull request', 'Never push to `main`', 'Never render on your own machine', 'gate.py', 'Render (preview)',
                       'final'):
            self.assertIn(needle, self.s, needle)

    def test_versions_agree(self):
        v = open(os.path.join(ROOT, 'VERSION')).read().strip()
        self.assertIn(f'version: {v}', self.s)

    def test_workflows_exist(self):
        for f in ('ci.yml', 'render.yml'):
            self.assertTrue(os.path.exists(os.path.join(ROOT, '.github', 'workflows', f)))
        self.assertTrue(os.path.exists(os.path.join(ROOT, '.github', 'pull_request_template.md')))


if __name__ == '__main__':
    unittest.main()
