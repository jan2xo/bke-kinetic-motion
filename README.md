# BKE Kinetic Motion v2.3

[![CI](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/ci.yml/badge.svg)](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/ci.yml)
[![Render](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/render.yml/badge.svg)](https://github.com/jan2xo/bke-kinetic-motion/actions/workflows/render.yml)

Premium motion graphics written in code (Python, NumPy, Pillow, FFmpeg), **rendered and graded on GitHub Actions**.
A planning PASS is not a video: every build has to get through `scripts/gate.py` before an MP4 is published.

## Make a video (PR flow)
`main` holds only the kit, the templates and the reference production. Every video is a branch and a pull request.
1. Branch `video/<name>`. Copy `projects/render-dock-15s/` (or a template) to `projects/<name>/`, then edit `render.py` and `timeline.json`.
2. Open a PR. **CI** (tests + static gate + demo render) and **Render (preview)** (your project at S=1 + full gate) run on their own.
3. Download the Render artifact: preview MP4, contact sheet, `gate_summary.md`, QA. Push fixes to the same PR.
4. Merge when the preview is approved. The merge renders the **final** MP4 (S=2). It's uploaded only if the gate passes.

Recommended: Settings → Branches → add a rule for `main` → require a pull request and require the status checks
**Tests + static gate** and **Render 3D demo + full gate** to pass.

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
