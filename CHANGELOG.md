# Changelog

## 2.3.0 · 2026-10-26
The pull-request production line. `main` is the template and reference; every video is a PR.

- `render.yml`: a PR touching `projects/<name>/` renders a **preview** and runs the full gate. A merge to `main` renders the
  **final** (S=2). Manual Run workflow still works on any branch. Stale runs on the same PR are cancelled.
- `.github/actions/setup`: Python plus a cached static ffmpeg (BtbN build) instead of `apt-get`, which hung for more than 11 minutes on a runner.
  Each setup step has a 6-minute timeout.
- `SKILL.md`: the workflow is branch, then PR, then green CI + Render (preview), then user review, then merge (final). Agents never push to `main` or render locally.
- `.github/pull_request_template.md`: the gate checklist. `tests/test_skill_contract.py` fails CI if SKILL.md stops pointing to PR + Actions.

## 2.2.0 · 2026-10-26
The production gate and GitHub Actions production line. All rendering moves off the agent's machine.

### Why
An agent given v2.1 passed the plan check and then shipped a 140-line flat Pillow sketch. It had no mg3d camera,
no mask-rise type, no transitions and no audio, and 7 of 20 events were never implemented. The plan check validated only the
JSON, so the PASS looked like "done". v2.2 checks the build itself.

### Added
- `scripts/gate.py` (static | full): plan, engine (AST of the renderer: kit imports, manifest load, Text, finish,
  mg3d for camera3d, supersampling, every visual event referenced), implementation map (visual_log and audio cue log vs
  the manifest, undeclared ids, logged-time drift), rendered QA (validate, motion, sync, lint3d, impact found).
  Writes `gate_report.json` and `gate_summary.md`, and appends to the Actions job summary. Exit 2 on FAIL.
- `scripts/produce.py`: one command from a project folder to a gated MP4. `canvas` in the manifest sets the size.
- `.github/workflows/ci.yml`: tests, plan checks, static gate on every renderer, 3D demo render and full gate.
- `.github/workflows/render.yml`: production render (manual, or on push to `projects/`). The MP4 is uploaded only when the gate passes.
- `projects/render-dock-15s/`: the 15 s vertical Render Dock showcase as a reference production.
- `tests/test_gate.py` + `tests/fixtures/gpt_draft_*`: the real GPT draft must FAIL the gate (7 hard failures).
- `requirements.txt`, `.gitignore`.

### Changed
- `SKILL.md`: "rules that make this not slop", an Actions-only workflow, gate rows in the fix playbook and QA rubric.

## 2.1.0 · 2026-10-26
A CPU-only 2.5D/3D module. Same dependencies (Python, NumPy, Pillow, FFmpeg). Existing 2D tools and all 40 v2 tests unchanged in behaviour.

### Added
- **`scripts/mg3d.py`**: camera with view/projection matrices, lens in mm (35–50 mm rule), `design_distance`
  (1 unit = 1 px at z=0); rigs `static`, `dolly`, `orbit` (≤25°), `crane` with eased keyframe `Track`s; textured
  `Card`s with position/rotation/scale/alpha and a `layer` override for read-first type; Pillow PERSPECTIVE warp at
  supersample; painter's-algorithm depth sort; culling (behind, near-plane straddle, edge-on, off-screen) and a near fade;
  depth of field in ≤5 quantised z-bands; distance fog/dimming; projected ground shadows; ambient/key/rim lighting;
  floor grid; `card_wall`, `scatter`, `scatter_align`, `lerp_xf`; `lint_rig` and `check_readable`; `bench`.
- **`templates/promo_3d_template.py` + `templates/timeline_3d.json`**: 6 s, 30 fps, 120 BPM. 30 media cards scattered
  through depth (with lateral crossers behind the headline), snapping onto a 6×5 grid on the downbeat, rim-light sweep,
  recede, title. One 40 mm dolly. Subcommands `render [--preview]`, `stills`, `vlog`, `lint`, `bench`.
- **`docs/3D_DECISIONS.md`**: when 3D earns its place, camera/depth/readability rules with reasons, method, measured
  performance, limits. **`SKILL.md` §9** 3D workflow.
- **`tests/test_mg3d.py`** (17 tests): projection centre and FOV scaling, design distance, lens conversion, matrix vs
  project agreement, warp placement, depth-sort order, culling, DOF rising with distance from focus, fog/rim, rig and
  readability lint, 3D plan check, visual-log coverage, and a camera-only dolly rendered with mg3d classified as camera motion.
- **`qa_reports/promo_3d_v2.1/`**: full QA of the 3D demo plus a 720p preview.

### Changed
- `motion_energy.py`: measures global scale (dolly/zoom about the frame centre) per frame, counts it as camera motion and
  uses the zoom-compensated residual for `camera_only`; reports `zoom` in the series. Version 2.1.0.
- `timeline.py`: `kind: "camera"` events with `move3d`, top-level `camera3d`; `check` FAILs stacked camera moves,
  orbit > 25°, lens outside 35–50 mm, linear/overshoot camera ease and moves without meaning.
- `preview.py`: `camera` windows (start and settle) for every camera move, with camera-specific questions.
- `sync_check.py` report version 2.1.0 (camera swells such as risers are reported "not measurable", never passed).

## 2.0.0 · 2026-10-26
Creative judgement and real motion QA. The rendering engine is unchanged; v2 decides before it draws and measures after.

### Added
- **Creative decision framework, mandatory before code** (`SKILL.md` §1, `docs/CREATIVE_FRAMEWORK.md`, `templates/creative_plan.md`):
  semantic polarity, motion vocabulary with meanings, half-second beat sheet (one dominant motion), ranked impacts and
  energy targets, easing by narrative role, stagger and typographic choreography, accent budget, decreasing density,
  planned anticipation, transitions and quiet.
- **`scripts/timeline.py`**: one shared event manifest (`timeline.json`, schema `bke-motion-timeline/1`) read by both
  render and audio code, plus `timeline.py check`, which fails effects without meaning, missing beat slots, multiple
  dominants, bad ranks and required sync events without sound; warns on rising density, an off-grid cut, a payoff not
  ranked 1, missing anticipation and no planned quiet.
- **`scripts/motion_energy.py`**: measures rendered video or PNG frames. Per-frame luma, edge, chroma, extent, local-block,
  camera (phase correlation) and grain channels; fps/resolution normalisation; style presets; holds (with declared quiet
  and end-card handling), peaks (flash/cut/camera/content) and ranking, scene statistics, energy order and sag, impact
  presence and rank, pacing gaps, camera-only stretches, single-frame pops; JSON report, PNG graph, PASS/WARN/FAIL summary.
- **`scripts/sync_check.py`**: DECLARED sync (manifest vs audio cue log and visual log: missing sfx, orphan audio, drift,
  double triggers/masking, overlapping hit windows, drift trend, unrendered/undeclared events) and VERIFIED sync
  (spectral-flux audio onsets vs motion peaks in the MP4; events not distinct in both are "not measurable", never a pass).
- **`scripts/preview.py`**: temporal QA windows (entrances, transitions, flagged holds, final reveal) as real-time and
  half-speed clips with timecode, frame strips with activity bars, onion skins, and a checklist `index.md`.
- **`docs/TEMPORAL_QA.md`** (how to judge easing, velocity, continuity, rhythm, storytelling), **`docs/MANIFEST.md`**,
  **`docs/VALIDATION.md`**.
- **Tests** (`tests/`, stdlib `unittest`, 40 tests): synthetic videos for holds, declared quiet, end cards, grain,
  flashes, camera pans and fps/resolution invariance; sync and plan-check unit tests; regression fixtures from the v1
  Render Dock render (640×360 proxy re-encode + the v1 audio cue log captured by instrumenting a copy of v1 `audio.py`).
- **`examples/render_dock/timeline.json`**: v1's intent reconstructed as a manifest (marked AS BUILT) for regression.
- **`qa_reports/`**: real reports for v1 Render Dock (fails as it should), the template before its fix, and after.

### Changed
- `music_synth.py --manifest`: every sync sound (impact, whoosh, riser, glitch/tick, off-grid kick) is placed at
  its event's `audio_time` and tagged with its event id; no random ticks; deterministic. `--cue-log` writes the log.
  Legacy flags still work; their random ticks now show up as orphan audio in `sync_check`.
- `promo_template.py` is manifest-driven (scene times, transitions, glitch bursts and flash size by rank come from
  `templates/timeline.json`), writes `visual_log.json`, and fixes two defects the new QA found in the v1 template:
  a 1.1 s dead hold after the reveal (fixed with a beat-locked grid "breathe" ripple + slow push-in) and a payoff
  flash smaller than the reveal flash (now scaled by rank: 0.85 / 0.45 / 0.3).
- `templates/timeline.json` glitch_open moved 0.32 → 0.40 s after VERIFIED sync measured the slam's visual peak 84 ms
  after the sound.
- `SKILL.md` rewritten around the five questions (what / why / how / when / when to stop), the mandatory workflow,
  the QA rubric and a fix playbook.

### Unchanged
- `mglib.py`, `encode.sh`, `validate.py`, `voiceover.py`, `setup.sh`, fonts.
- `examples/render_dock/render.py` and `audio.py` are the v1 production code exactly as shipped in v1.0 of this kit
  (documented as the "before" state; their hardcoded times and random glitch sounds are what the regression tests catch).

## 1.0.0 · 2026-10-25
Initial portable kit: engine, template, music synth, voiceover, encode, validate, Render Dock example.
