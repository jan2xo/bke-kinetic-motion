---
name: bke-kinetic-motion
version: 2.2.0
description: Plan, render and QA premium kinetic-typography / motion-graphics promos entirely in code (Python + NumPy + Pillow + FFmpeg), rendered on GitHub Actions, never on the agent's machine. Creative decisions are written down before any code (polarity, motion vocabulary, half-second beat sheet, ranked impacts, easing by role, accent budget, planned quiet). One manifest drives picture AND sound. A CPU 2.5D/3D card renderer is included (real camera and lens, perspective cards, DOF, fog, shadows). v2.2 adds a hard production GATE (scripts/gate.py) and produce.py, so the agent cannot ship a from-scratch sketch, skip events, or call a planning PASS "done". Use for product promos, launch ads, title sequences, logo reveals, kinetic text with exact timings.
---

# bke-kinetic-motion v2.2

Effects are cheap. Judgement is what separates a premium piece from an animated slideshow. This skill makes
you answer five questions in writing, check the answers mechanically, then check the *rendered* result. Since v2.2
a gate enforces every step, and **GitHub Actions does all rendering**.

| Question | Where you answer it | What checks it |
|---|---|---|
| **WHAT** should move? | beat sheet: exactly one dominant motion per half second | `timeline.py check` |
| **WHY** should it move? | polarity + motion vocabulary: every effect carries a meaning | `timeline.py check` (effect without meaning = FAIL) |
| **HOW** should it move? | easing by narrative role, stagger, accent budget | plan check + temporal previews |
| **WHEN** should it move? | events with times, ranked impacts, audio cues, tolerances | `sync_check.py` (declared + verified) |
| **WHEN** should it **stop**? | declared quiet moments, density curve, end card | `motion_energy.py` (holds, sag, gaps) |
| **Was it actually BUILT?** | renderer source, visual_log, audio cue log, MP4 | **`gate.py`** (v2.2) |

---

## 0. The rules that make this not slop (read first, obey always)

1. **The gate decides "done", not you.** A build is finished only when the GitHub Actions `Render` run is green and
   `gate_summary.md` says PASS (or WARN with every warning answered in words). Never tell the user a video is ready on the
   strength of a plan check, a still, or your own description.
2. **Never write a renderer from a blank file.** Copy `templates/promo_3d_template.py` (3D) or `templates/promo_template.py`
   (2D) into `projects/<name>/render.py` and change it. The gate FAILs a renderer that skips the kit:
   no `mglib` import, no `timeline.load`, no `mglib.Text`, no `mglib.finish`, no `visual_log.json`, `S=1` outside
   `--preview`, or a `camera3d` plan without `mg3d.CameraRig`/`Renderer`.
3. **Every event in the manifest is implemented or deleted.** The gate FAILs any visual event the renderer source never
   names, any event missing from `visual_log.json`, any logged id the manifest does not declare, any logged time that
   drifts from the manifest, and any event with a sound that has no cue in `audio_cues.json`.
4. **Impacts land ON the beat.** Motion *ends* (biggest visual change) on the event time: start = t - duration.
   Flash size by rank 0.85 / 0.45 / 0.30. `motion_energy` must find each ranked impact within 3 frames, in rank order.
5. **Times come only from the manifest.** The gate warns on float literals equal to event times in comparisons/`prog()`.
6. **No fix by loosening thresholds.** Fix the design (section 4), push, let CI re-run.
7. **You do not render locally.** You have no reliable compute and no eyes on the MP4. You edit files in the repo and
   push. Actions renders, measures and gates. You read the gate summary and the QA artifacts, then iterate.

## 1a. Requirements
On the runner: Python 3.11, `numpy`, `pillow`, `ffmpeg` (installed by the workflows from `requirements.txt`).
No GPU, no ML model, no paid API. About 0.5 s per 1080p frame at S=2, so 15 s at 30 fps is about 4 to 8 minutes on `ubuntu-latest`.

## Layout
```
.github/workflows/ci.yml     every push/PR: unit tests, plan checks, static gate on every renderer, 3D demo render + full gate
.github/workflows/render.yml production: Actions -> Render -> Run workflow (project name), or any push touching projects/
projects/<name>/             ONE PRODUCTION = render.py + timeline.json (+ assets). Example: projects/render-dock-15s
scripts/produce.py           manifest -> plan check -> static gate -> render -> lint3d -> music -> encode -> validate -> QA -> full gate
scripts/gate.py              the production gate (static | full). Writes gate_report.json + gate_summary.md   (v2.2)
scripts/timeline.py          shared event manifest library + creative PLAN CHECK
scripts/motion_energy.py     measures the rendered video: energy, holds, peaks, impact rank
scripts/sync_check.py        manifest vs scheduled cues (DECLARED) and vs the MP4 (VERIFIED)
scripts/preview.py           temporal QA: 1x + half-speed clips, frame strips, onion skins
scripts/music_synth.py       procedural music; --manifest places every sync sound from the manifest
scripts/mg3d.py              2.5D/3D: camera + lens, rigs, perspective cards, depth sort, DOF, fog, shadows, light
scripts/mglib.py             engine: easing, per-char Text, masks, glow, scrims, cards, transitions, finish
templates/                   promo_3d_template.py + timeline_3d.json (3D), promo_template.py + timeline.json (2D), creative_plan.md
tests/                       unittest suite incl. test_gate.py (the GPT draft fixture must FAIL the gate)
docs/                        CREATIVE_FRAMEWORK, TEMPORAL_QA, MANIFEST, 3D_DECISIONS, VALIDATION
```

## Workflow (mandatory order, GitHub Actions only)
1. **Plan in words** with `templates/creative_plan.md` (section 1). Show the user the polarity sentence, the three ranked
   impacts and the beat sheet before writing code.
2. **Create `projects/<name>/`**: copy the matching template into `render.py` and write `timeline.json`.
   Add `"canvas": {"w": 1080, "h": 1920}` for vertical (default 1920x1080). Point the renderer at its own manifest
   (`TL.load(os.path.join(HERE, 'timeline.json'))`) and the kit with
   `KIT = os.environ.get('BKE_KIT', os.path.join(HERE, '..', '..'))`.
3. **Name every event in code.** Look up each event with `TLM.event('<id>')`, drive its visual from that time, and
   list it in `build_visual_log()`. If you can't implement an event, delete it from the manifest. Don't log it.
4. **Commit on a branch and open a PR.** `CI` runs unit tests, the plan check and the static gate in about 2 minutes.
   Fix every FAIL it reports.
5. **Preview render:** Actions -> Render -> Run workflow, `project=<name>`, `preview=true`. Download the artifact and read
   `gate_summary.md`, `qa/motion_summary.txt`, `qa/sync_summary.txt`, the `*_contact.png` sheet and the frame strips in
   `qa/previews/`. Answer the questions in `qa/previews/index.md` for every window (PASS/FIX).
6. **Fix by design** (section 4), push, and repeat step 5 until the gate is PASS (or WARN with each warning justified).
7. **Final:** merge to `main` (that triggers a full S=2 render of every changed project), or Run workflow with `preview=false`.
   The MP4 artifact is uploaded **only when the gate passes**. A failed gate uploads QA files only, never a deliverable.
8. **Deliver** the artifact link plus the gate summary. State plainly what the render verified (validate, motion,
   impact rank, sync VERIFIED rows) and what was only declared (swells reported "not measurable").

Local equivalent (for debugging only): `python3 scripts/produce.py <project> [--preview]`. The result is the same as CI.

---

## 1. The creative decision framework (do this before code)

Full method with worked examples: `docs/CREATIVE_FRAMEWORK.md`. The short version, with the decision rule for each step:

**1. Semantic polarity: what transformation does the story communicate?**
Find the before and after in the brief: chaos→control, slow→fast, alone→together, noise→signal. Write one
sentence: "<product> turns <from> into <to>." If you can't, ask; every later choice depends on it.
*Render Dock:* "media chaos → production control".

**2. Motion vocabulary: which effects express each pole?**
List effects for `from`, `to` and `neutral` (finishing, transitions), each with the *meaning* it carries.
- Unstable vocabulary (from-poles like chaos, stress, noise): scatter, rotation drift, jitter, RGB split, shake that BUILDS, random timing, ease-in acceleration.
- Stable vocabulary (to-poles like control, clarity, speed): grid snap, mask rise, stagger, fixed reference (playhead), symmetric reveal, ease-out settle, linear only for machines.
- An effect may live on one pole only. Retire it when its pole ends (v1 never used RGB split after 2.0 s).
- **If you can't write the meaning, cut the effect.** The plan check fails any beat that uses an unlisted effect.

**3. Half-second beat sheet: one owner per moment.**
For every 0.5 s: `dominant` (exactly one), `supporting` (zero or one), `ambient` (grid drift, grain, particles),
`audio`, `effects`, `read_first`. Two dominants = the viewer reads neither. A slot with no change in its
dominant is a hold: either planned quiet (declare it) or a gap to fill.

**4. Ranked impacts → energy targets.**
List the hits and rank them by narrative importance; the payoff (usually the brand reveal) is rank 1.
Give hit size by rank (flash 0.85 / 0.45 / 0.3; impact gain 1.0 / 0.9 / bed kick). Give each scene an energy
level (`high|medium|low|rest`) that follows the story, and plan **anticipation** for every ranked hit (what builds into it:
ease-in acceleration, riser, zoom ramp). `motion_energy.py` later checks the measured peaks follow the same order.

**5. Easing by narrative role, never by taste.**
| Role | Curve | Duration |
|---|---|---|
| arrive (things entering, settling) | expo-out | 0.4–0.6 s; hero settles 0.9–1.2 s |
| depart / build into a cut | expo-in | 0.12–0.25 s |
| transform in frame (reflow, progress, dim) | cubic in-out | 0.4–0.8 s |
| pop (small confirmations ≤ 5 % of frame: checks, nodes, logo) | back-out | 0.25–0.4 s |
| mechanical (scrolling tracks, particles, spinners) | linear | continuous |
Never overshoot a headline. The calm, confident line moves *slower* (v1: chaos title settles in 0.45 s, "PRODUCTION CONTROL" in 0.9 s).

**6. Stagger and typographic choreography.**
Characters 25–40 ms apart, list items 100–150 ms, nodes 60–80 ms. Direction carries meaning: left→right = process,
centre-out = resolved, rising from a mask = precise, collapsing tracking = forcing together. Only one large element starts
on any frame unless simultaneity *is* the message (v1's 2.0 s snap: order arrives at once).

**7. Accent budget and decreasing density.**
One accent colour, reserved for meaning (the key word, progress/done state, the brand); target ≤ 10 % of frame
pixels outside the end card. Count the elements that move or matter per scene: from the first `to`-pole scene, density should fall
toward the payoff (v1: 32 → 14 → 11 → 3). The plan check warns when it rises.

**8. Anticipation, transitions and deliberate quiet.**
Transitions follow the story: sideways (whip) = next topic at the same level; zoom-through = deeper into the system;
flash cut = payoff. Put sound *before* the picture for swells (whoosh starts 0.1–0.2 s early via `audio_offset`), on the
frame for transients. Declare every planned stillness in `quiet` with a reason: the end card always, and any breath
before a big hit. Undeclared stillness longer than ~0.5 s (kinetic style) is treated as dead air.

## 2. Measurement: what the tools prove and what they don't

**`motion_energy.py`** measures frame-to-frame change at a fixed analysis width (resolution-independent) and
normalises to 30 fps. Channels: luma, edge (structure), chroma (colour-only change), extent (how much of the frame),
local (busiest block: small objects such as a cursor still count), camera (phase correlation: global translation)
and grain (per-frame noise estimate, so grain is not mistaken for motion and does not hide a hold).
- **Hold** = smoothed activity, edges, extent AND the local channel all quiet for ≥ `hold_warn` s. FAIL at ≥ `hold_fail`.
  Declared `quiet`, or an end card after the final ranked impact, is reported as INTENTIONAL (PASS).
- **Peaks** = local maxima above `max(peak_abs, peak_mult × rolling median)`, classified flash / cut / camera / content, ranked.
- **Scenes**: mean, body mean (cut boundaries excluded), median, p90, half-second windows, hold fraction.
- **Energy order / sag**: a scene planned higher must measure higher; a `high` scene may not dip below the typical `medium` half-second.
- **Impact rank**: each ranked impact must produce a peak within ±3 frames, in rank order.
- **Pacing gaps**: long stretches between significant events (outside declared quiet).
- **Camera-only**: long stretches where all movement is global translation (motion without choreography).
- **Pops**: single-frame spikes no declared event explains (jumps, glitches in the render).
- Styles: `kinetic` (default), `calm`, `documentary`; override any value with `--set key=value` or a `motion_qa` block in the manifest.
- **Limits:** frame difference measures "how much changed", not "how good it feels". It over-counts flashes and grain,
  under-counts slow zooms and tiny details, and can't judge easing quality or taste. That is why section 3 is mandatory.

**`sync_check.py`** reports two levels, never mixed:
- **DECLARED** (manifest vs the cue log the music code wrote, plus the renderer's visual log): missing sfx, orphan audio
  (a sound no event accounts for), drift beyond tolerance, double triggers/masking, overlapping hit windows, drift trend,
  unrendered or undeclared visual events. Proves plan and code agree.
- **VERIFIED** (manifest vs the rendered MP4): audio onsets by spectral flux, visual hits from motion peaks. Only events
  distinct in BOTH count; the rest are `not_measurable`, which is not a pass. Swells (whoosh, riser) are never onset-timed.

## 3. Temporal QA (mandatory: stills are not enough)

Contact sheets catch legibility and clipping. They cannot show timing, easing, continuity or rhythm; every v1 defect
was invisible in the stills. `preview.py` builds the windows that matter (every scene entrance, ±0.35 s around every
impact/transition, every flagged hold, the final reveal) as a real-time clip, a half-speed clip, an 18-frame strip
with per-frame activity bars, and an onion skin. Watch the clips; if you can only view images, read the strips.

How to judge (details and examples in `docs/TEMPORAL_QA.md`):
- **Easing:** in the strip, frame-to-frame spacing should shrink toward the end of an arrival (big gaps, then small).
  Equal spacing on type = linear = cheap. A dead stop with no settle = missing ease-out.
- **Perceived velocity:** the dominant element should cover its distance in 8–18 frames at 30 fps; < 5 frames reads
  as a cut, > 25 frames reads as drift. Peak velocity belongs at the start of an arrival and the end of a departure.
- **Continuity:** no element may appear or vanish without an entrance or exit (check the onion skin for pops), and
  the eye position at the end of one shot should be where the next shot's dominant motion starts.
- **Rhythm:** hits land on beats (cut times divisible by 60/BPM); between hits, something moves on the beat or the
  half-beat. More than ~0.6 s with nothing on the beat in a kinetic piece is dead air unless declared.
- **Storytelling:** play the half-speed clip without sound and say what is happening. If you can't name the
  transformation, the motion is decoration.

## 4. Fix playbook (respond to findings with design, not thresholds)
| Finding | Design response |
|---|---|
| hold FAIL | Give the moment a supporting motion on the beat (the template's grid "breathes" with a left-to-right ripple), add a slow push-in, bring the next element in earlier, or shorten the scene. Declare it `quiet` only if the stillness is truly wanted. |
| energy_sag in a `high` scene | Add a beat-locked event (a glitch burst, a card swarm surge) in the dip, or raise ambient motion; check the dip isn't masked by a scrim. |
| energy_order | Either the plan is wrong (update the energy label honestly) or the scene needs more or less motion. |
| impact_rank | Scale flash/zoom/impact by rank; quiet the frames before the rank-1 hit so it contrasts. |
| impact_missing | The hit isn't visible: add a flash, cut or snap on that frame, or remove the event. |
| missing_sfx / orphan_audio | Every sync sound comes from the manifest. Delete random or unplanned sounds, or give them a visual event. |
| VERIFIED drift | Put the event time on the frame of maximum visual change, not on the motion start (template: the glitch moved 0.32→0.40 s because the expo-out slam peaks about 3 frames after it starts). |
| camera_only | Add choreography inside the frame; camera moves support, they don't carry a scene. |
| pop | Inspect the strip around it: a missing ease, a z-order flip, or an asset loading late. |
| gate `kit_import` / `typography` / `finish` / `camera3d` | You wrote a sketch. Restart from the template and port your scene ideas into its structure. |
| gate `unimplemented` / `unrendered` | Draw the event (driven by `TLM.event(id).t`) and log it, or delete it from the manifest and re-run the plan check. |
| gate `silent_event` | Re-run `music_synth.py --manifest`; never hand-edit the cue log. |
| gate `visual_drift` | Log the frame of maximum change, and move the motion so it peaks there. |
| gate `hardcoded_time` | Replace the literal with `TLM.event(id).t` (+/- an offset with a name). |

## 5. QA rubric (deliver only when every row passes)
| Check | Tool | Pass |
|---|---|---|
| Creative plan complete | `timeline.py check` | no FAIL |
| No dead air | `motion_energy` holds | no FAIL; WARNs justified in words |
| Hits follow the story | `motion_energy` impact_rank | PASS |
| Energy follows the plan | energy_order / energy_sag | no WARN, or the plan corrected |
| Picture/sound agree (declared) | `sync_check` DECLARED | no FAIL |
| Picture/sound agree (rendered) | `sync_check` VERIFIED | no FAIL; ranked impacts verified |
| Easing, velocity, continuity, rhythm | `preview.py` + your eyes | every window PASS in `index.md` |
| Legibility, clipping, glow artefacts | `validate.py` contact sheet | every text beat readable at thumbnail size |
| Delivery spec | `validate.py` | exit 0 |
| Built as planned | `gate.py full` in the Actions `Render` run | PASS, or WARN with every warning answered |

## 6. Taste vs technique vs planning vs iteration
- **Taste** (what to want): a meaning for every effect, one accent, the courage to be quiet before a big hit, hierarchy of hits.
- **Technique** (how to draw): easing math, masks, supersampling, glow, transitions. All in `mglib.py`. Necessary, not sufficient.
- **Planning discipline** (the biggest gap in agents that render "clean but boring"): polarity, vocabulary, beat sheet
  with one owner per moment, ranked hits, planned quiet, one manifest for picture and sound.
- **Iteration quality:** measure the render, watch motion previews, fix by design, re-measure. Stills alone hide
  holds, sync and rhythm.

## 7. Anti-patterns (each one makes a piece look cheap)
The same effect on every word · effects with no pole · two large elements starting on one frame · overshoot on headlines ·
linear easing on type · accent colour used as decoration · flat backgrounds · a UI shown as a sliding screenshot instead
of an action (show the cursor press, lift, carry, drop) · holds > 0.6 s that aren't declared · random sound effects ·
a payoff that is smaller than an earlier hit · density that rises toward the end · motion still running at the last frame.

## 8. Rendering techniques (unchanged from v1, still required)
- Every frame is a pure function `frame(t)`; render at 2x supersample, LANCZOS down; pre-render textures at 3x.
- Mask reveals, tracking animation (40–70 px → 4–12 px), glow under text from a blurred 1/4-res copy (pad ≥ 2.5× blur radius),
  soft scrims behind text over busy visuals, depth from z → scale/opacity/blur/parallax, soft shadows, drifting grid.
- Transitions on beats: whip pan (shift + horizontal blur, 0.12–0.18 s), zoom-through (1→1.35 + darken), flash by rank.
- Finish: vignette + Gaussian grain (σ≈3). Parallel frames with `multiprocessing`, PNG `compress_level=1`, blur at low res.
- Audio: oscillators and noise only (royalty-free by construction), master about −16 LUFS (−14 with voiceover), true peak ≤ −1 dBTP.

## 9. 2.5D / 3D (v2.1, `scripts/mg3d.py`)
Read `docs/3D_DECISIONS.md` first. Short version:
- **Use depth only when it means something:** chaos (scatter in depth), order arriving (depth collapsing onto a plane),
  scale (receding wall), focus (DOF pull). Otherwise stay 2D.
- **Plan it in the manifest:** top-level `camera3d: {lens_mm, rig}`, and one `kind: "camera"` event per move with
  `move3d: {type, end, ease, rank, meaning}`. `timeline.py check` FAILs stacked camera moves, orbit > 25°, lens
  outside 35–50 mm, linear or overshooting camera ease, and a move without meaning.
- **Camera:** one move per shot, eased in and out, still before the payoff. `Camera.design_distance()` makes the
  z=0 plane 1 unit = 1 px, so flat layouts land where you designed them.
- **Readability:** type ≤20° tilt while read, end card flat/frontal/still (`check_readable`, template `lint`).
  Read-first type that cards could cross gets `layer=1`.
- **The camera is not choreography:** `motion_energy.py` now measures dolly/zoom as camera motion, so a stretch
  where only the camera moves is `camera_only` WARN. Add in-frame motion (lateral travel works best).
- **Build:** `Renderer(cam, dof=, fog=, light=, shadow=).render(base, cards, floor=)` inside your `frame(t)`;
  `card_wall`, `scatter`, `scatter_align`, `lerp_xf` for layouts; `CameraRig(kind, t0, t1, ...)` for the move.
- **QA is the same pipeline** plus `promo_3d_template.py lint` (lens, tilt, end state, camera still) and the preview
  windows `cam_<id>_start` / `cam_<id>_settle` for every camera move.
- **Cost:** about 0.4–0.6 s per 1080p frame at S=2 on 2 cores. About 60 visible cards is the practical ceiling.
  Iterate at `--preview`.

## Known limits
3D is 2.5D only (flat cards: no meshes, no physically based lighting; painter's sort can't resolve intersecting cards). No characters or footage. Motion metrics are proxies: they never replace watching the previews.
VERIFIED sync can only time events that stand out in both picture and sound; subtle accents are reported as not
measurable. Spoken VO works; sung TTS sounds robotic. Lyric timing needs LRC/SRT input (no ASR).
