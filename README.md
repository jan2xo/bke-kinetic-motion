# BKE Kinetic Motion v2.2

[![CI](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/ci.yml/badge.svg)](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/ci.yml)
[![Render](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/render.yml/badge.svg)](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/render.yml)

Premium motion graphics written in code (Python, NumPy, Pillow, FFmpeg), **rendered and graded on GitHub Actions**.
A planning PASS is not a video: every build has to get through `scripts/gate.py` before an MP4 is published.

## Make a video
1. Create `projects/<name>/` with `render.py` (copied from `templates/promo_3d_template.py`) and `timeline.json`.
   Add `"canvas": {"w": 1080, "h": 1920}` for vertical.
2. Push a branch. **CI** runs the tests, the plan check and the static gate.
3. Open **Actions → Render → Run workflow**, enter the project name, and tick `preview` for a fast pass.
4. Download the artifact. If the gate passed it holds `<name>.mp4`, the contact sheet, `gate_summary.md` and the QA files.
   If the gate failed you get only the QA files, so you can see why.
5. Merge to `main` to render every changed project at full quality.

Reference production: `projects/render-dock-15s` (15 s, 1080×1920, music only).

## The gate (`scripts/gate.py`)
| Stage | Fails when |
|---|---|
| plan | `timeline.py check` fails |
| engine | the renderer skips the kit: no `mglib`, no `timeline.load`, no `mglib.Text`, no `mglib.finish`, no `visual_log.json`, `S=1` outside preview, or camera3d without `mg3d`. Also when a visual event is never referenced in code |
| map | an event is missing from `visual_log.json`, an id is undeclared, a logged time drifts, or a sound event has no cue |
| render | there's no MP4, or validate, motion_energy, sync_check or lint3d reports a FAIL, or a ranked impact has no measured peak |

`tests/fixtures/gpt_draft_render.py` is a real agent-written draft that ignored the kit. It fails the gate with 7 hard failures, and a test keeps it that way.

## For agents (ChatGPT, Claude, Hark)
Load `SKILL.md`. Section 0 holds the rules. The agent edits files and pushes; it never renders on its own machine.

## Local debugging
```bash
pip install -r requirements.txt   # plus ffmpeg
python3 -m unittest discover -s tests
python3 scripts/produce.py 3d-demo --preview
python3 scripts/produce.py render-dock-15s
```
