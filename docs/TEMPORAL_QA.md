# Temporal QA: judging motion, not frames

Stills show composition. Motion quality lives *between* frames. All three v1 Render Dock defects (dead hold,
chaos sag, unsynced glitch sounds) passed every still that was inspected. So temporal QA is mandatory.

## What to inspect
`preview.py` builds these windows automatically from the manifest and the motion report:
| Window | Span | Why |
|---|---|---|
| entrance | first 0.6 s of each scene | arrivals reveal easing and stagger quality |
| transition | ±0.35 s around each impact / transition | anticipation, hit frame, release |
| hold | every hold `motion_energy` flagged, ±0.2 s | is the stillness a rest or dead air? |
| reveal | the whole final scene | payoff size, resolution, end-card rest |

Each window gets `_1x.mp4` (watch first), `_half.mp4` (watch for easing), `_strip.jpg` (every frame up to 18, with
per-frame activity bars and a sparkline) and `_onion.jpg` (earlier frames fainter: paths, arcs, overlaps).
`index.md` lists the windows with a **measured motion shape** (front-loaded ≈ ease-out, back-loaded ≈ ease-in,
build-into-hit for transitions). Treat it as a hint, never a verdict.

## How to evaluate
**Easing.** Read spacing in the strip. An arrival should show large frame-to-frame displacement first and then
smaller and smaller steps (expo-out). Equal steps on type mean linear easing, which reads as cheap. A large step followed by
zero movement is a dead stop: the settle is missing.

**Perceived velocity.** Count frames for the dominant move: 8–18 frames at 30 fps feels deliberate, < 5 frames
reads as a cut, > 25 reads as drift. Peak velocity belongs at the *start* of an arrival and the *end* of a departure.
In the half-speed clip, nothing important should feel like it teleports.

**Continuity.** Nothing appears or vanishes without an entrance or exit (look for single-frame jumps in the onion
skin). The eye's position at the end of a shot should be where the next shot's dominant motion begins. v1's
whip pan works because the outgoing title exits left and the UI panel enters from the right.

**Rhythm.** Hits land on beats. Between hits, something should change on the beat or half-beat. The activity sparkline
should look like a pulse, not a flat line. More than ~0.6 s of flat line in a kinetic piece is dead air unless declared.

**Storytelling.** Play the half-speed clip muted and narrate it in one sentence. If the sentence doesn't contain the
polarity (from → to), the window is decoration. Then ask: what does the viewer read first, and is that what the beat
sheet says they should read first?

## Recording the verdict
For each window in `index.md`, tick the questions and write PASS or FIX + the design change. Example from the template:
- `hold 2.83–3.93 (before fix)`: FIX. Title sits for 1.1 s with only grain moving. Change: the grid breathes on the
  beat (scale +7 %, brightness +35 %, left-to-right ripple) plus a 3.5 % push-in. Re-measured: no hold, PASS.

## When metrics and eyes disagree
Trust your eyes for *quality* (does it feel good?) and trust the metrics for *existence* (did anything move, did the
hit land on the frame?). A metric PASS never overrules a window that looks wrong. A window that "looks fine" in stills
but fails a metric must be watched at 1x before the failure is waived.
