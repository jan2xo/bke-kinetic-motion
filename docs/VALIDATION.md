# Validation evidence · v2.0.0 (2026-10-26)

Everything here was produced in this version's build environment: 2-core ARM Linux, Python 3, NumPy 2.5, Pillow 13,
FFmpeg, no GPU. The original Render Dock production files were read only, never modified; the regression fixture is a
640×360 re-encode of the delivered MP4 plus a cue log captured by running an instrumented *copy* of v1 `audio.py`.

## 1. Test suite
`python3 -m unittest discover -s tests -v` → **40 tests, OK** (full log: `qa_reports/test_run.txt`; the optional
full-resolution test ran against the original 1080p file via `RENDERDOCK_FULL`).
- 11 motion tests on synthetic videos: constant motion has no hold; an undeclared 1.5 s still FAILs at 1.5–3.0 s (±0.15);
  **the same still declared as quiet is INTENTIONAL (no false failure)**; **an end card after the final impact is
  INTENTIONAL**, but an over-long end card is still flagged; σ3 grain doesn't hide a hold; a flash is detected and
  classified at 1.0 s; a missing declared impact FAILs; a texture pan is recognised as camera motion, not a hold;
  energy at 320×180@30 vs 1280×720@60 agrees within 35 %; energy order and sag fire on a planned-high still section.
- 13 sync tests: clean schedule passes; audio_offset honoured; missing sfx; orphan audio; bed cues exempt; drift beyond
  tolerance FAILs and within tolerance passes; double trigger; visual-only with sound; unrendered and undeclared visual
  events; drift trend; event-id matching.
- 8 plan-check tests: the template plan passes; effect without meaning, missing beat slot and two dominants FAIL;
  rising density, payoff not rank 1 and no planned quiet WARN; required sync without audio FAILs.
- 8 regression tests on v1 Render Dock (below).

## 2. v1 Render Dock: the three reported defects are detected
Source: the delivered 1080p MP4 (`qa_reports/renderdock_v1/`); the 360p proxy gives the same verdicts.

| Defect reported in the design analysis | v2 finding | Notes |
|---|---|---|
| Dead hold 2.8–3.9 s | **FAIL hold 2.90–3.87 s** (0.97 s, activity 0.90 < 1.43) | The gold edge wave counts as small motion until about 2.9 s, so the hold starts there. |
| Energy sag in the chaos sequence | **WARN energy_sag chaos 1.0–1.5 s**: 1.79 vs medium reference 1.83 | Real but marginal (about 2 % under the line). Reported as WARN, not FAIL, on purpose. |
| Random glitch sounds | **DECLARED: 9 orphan glitch sounds (0.53–1.88 s), glitch_2 at 1.62 s missing (nearest −173 ms), 5 double triggers** | glitch_1 at 1.20 s happens to be matched by a random glitch 27 ms early. |

Also confirmed: measured hit sizes follow narrative rank (8.5 s = 129 > 2.0 s = 98 > 6.5 s = 66, ranks 1 > 2 > 3);
the end card 9.67–10.0 s is accepted as declared quiet; VERIFIED sync times 4 events in the render (glitch_open +16 ms,
reveal −8 ms, control_cut −4 ms, hero −8 ms) and reports 9 as not measurable (subtle accents and swells).

**Correction to the earlier analysis:** the analysis called 5.7–6.4 s a "soft hold". It was measured with luma alone.
v2's local-block channel sees the spinners and progress bars moving there, so it is low-energy but alive, not a hold.
v2 no longer flags it.

**The v2 pipeline clears the sync defect:** generating v1's music from `examples/render_dock/timeline.json` with
`music_synth.py --manifest` gives DECLARED sync **PASS (0 fail, 0 warn)** and a byte-identical cue log on repeat runs (test-covered).

## 3. The QA loop on the template (before → after)
The v1 template was re-run through v2 QA (`qa_reports/template_before_fix/`, a draft render at S=1):
- **FAIL hold 2.83–3.93 s** (the template inherited v1's dead hold after the reveal)
- **WARN impact_rank**: payoff flash (95) smaller than the reveal flash (97)

Design fixes (not threshold changes): a beat-locked grid "breathe" with a left-to-right ripple and a 3.5 % push-in
during the held title; flash size scaled by rank. Final S=2 render (`qa_reports/template_v2/`):
- plan check **PASS**; validate **PASS** (6.000 s, 180 frames, 1080p, yuv420p, −15.9 LUFS)
- motion **PASS**: no undeclared hold; hits 4.0 s = 140 > 2.0 s = 88 in rank order; end card 5.2–6.0 s INTENTIONAL
- sync DECLARED **PASS** (renderer visual log and audio cue log both match the manifest)
- sync VERIFIED: the first run **FAILed glitch_open (−84 ms)**: the slam's visual peak is 3 frames after the declared
  0.32 s. The event moved to 0.40 s (rule now in SKILL.md: put t on the frame of maximum visual change). Re-run:
  **PASS**, 3 events verified (−8 ms each), 3 not measurable.
- temporal previews: 7 windows with clips, strips and onion skins in `qa_reports/template_v2/previews/`.

## 4. Performance
`motion_energy.py` on the 10 s 1080p video: about 5.5 s. `preview.py` with clips for 13 windows from a 1080p source:
about 60 s (about 10 s without clips). Template final render (180 frames, S=2): 90 s on 2 cores.

## 5. Honest limits of this evidence
- Thresholds were calibrated on this kit's own visual style (dark background, grain, gold accent) plus synthetic tests.
  Very different styles (bright, flat, live footage) should start from the `calm`/`documentary` presets and be re-checked.
- The chaos-sag finding sits close to the line; small changes to encoding or analysis width can flip it.
- VERIFIED sync can't time subtle accents or swells; those stay "declared only".
- No metric judges taste. The previews and a human or agent watching them remain part of the gate.

## 6. v2.1.0: 3D module evidence (`qa_reports/promo_3d_v2.1/`)
Demo: `templates/promo_3d_template.py` + `templates/timeline_3d.json`, final S=2 render, 180 frames 1920x1080.
- plan check **PASS** (0 fail, 0 warn); 3D lint **PASS** (40 mm = 33.4° vertical FOV, headline tilt 0°, end cards flat/still, camera still)
- validate **PASS**: 6.000 s, 1080p, 30 fps, yuv420p, 180 frames, audio 6.000 s, −15.7 LUFS, true peak −2.2 dBFS, no black gaps
- motion **WARN** (0 fail, 1 warn): `energy_sag` in scatter 0.5–1.0 s (1.54 vs reference 1.58, about 3 % under). Kept as
  a documented WARN rather than relabelling the scene's planned energy. Peaks 4.00 s = 145 > 2.50 s = 92 (rank order PASS); no undeclared hold.
- sync **PASS**: DECLARED 5/5 within 0 ms; VERIFIED snap −8 ms and title −4 ms; 3 not measurable (riser and whoosh are
  swells; the rim sweep is not a distinct visual change). These are never counted as passes.
- temporal previews: 9 windows including camera start/settle, verdicts in `previews/index.md` (all PASS, hit_snap with a note).
- What the 3D QA caught during development, and the design fixes (no threshold changes):
  1. Cards crossing in front of TOO MANY FILES? at 0.5–1.0 s (contact sheet). Fix: read-first type `layer=1`.
  2. After that fix, the new dolly detector flagged 0.9–2.2 s as **camera-only**. Fix: 8 crossers travelling sideways behind
     the headline (lateral motion a zoom can't explain).
  3. A true-peak WARN (−0.2 dBFS). Fix: snap impact gain 0.8 in the manifest (a sound-design change). Result: −2.2 dBFS.
- Performance: `mg3d.py bench` 0.44 s/frame (30 cards, single process); demo 0.63 s/frame mean, 1.05 s max (single
  process); full render about 74 s on 2 cores (about 0.41 s/frame throughput).
