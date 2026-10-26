# Creative decision framework

A method for deciding **what should move, why, how, when, and when it should stop**, before any code exists.
It is not a list of effects to copy. Every rule below comes with the decision it serves and a Render Dock example.
Render Dock facts are from the v1 code (`examples/render_dock/render.py`, `audio.py`) and its measured render
(`qa_reports/renderdock_v1/`). Where v1 got it wrong, that is said too.

---

## Step 1 · Semantic polarity

**Decision:** what transformation must the viewer feel by the last frame?

Most briefs hide a before → after. Find it, write it as one sentence, and test every later choice against it.

| Brief phrase | from-pole | to-pole |
|---|---|---|
| "from media chaos to production control" | scattered, corrupt, nervous | aligned, precise, flowing |
| "faster checkout" | waiting, friction | instant, effortless |
| "your team, finally in sync" | fragmented, out of phase | unified, rhythmic |

If a brief has no transformation (pure brand sting), the polarity is usually *absence → presence*: darkness to light, silence to a chord.

**Render Dock:** "Render Dock turns a scattered pile of media into a controlled, synchronized production pipeline."
Everything before 2.0 s belongs to the from-pole; everything after belongs to the to-pole.

## Step 2 · Motion vocabulary

**Decision:** which motions *mean* each pole?

Translate the adjectives of each pole into motion properties:

| Property | Unstable (chaos, stress, noise) | Stable (control, clarity, confidence) |
|---|---|---|
| Path | random, rotating, colliding | straight, aligned, on a grid |
| Timing | irregular, jittery | staggered at a constant step |
| Easing | ease-in (accelerating, out of control) | ease-out (arriving, settling) |
| Camera | shake that builds | locked, or slow and deliberate |
| Signal | RGB split, glitch, flicker | clean edges, focus pull from blur to sharp |
| Density | many objects, overlapping | few objects, aligned, spaced |
| Speed | fast and nervous | the confident line is slower |

Write each effect with its meaning. An effect with no meaning is decoration, and decoration reads as cheap.

**Render Dock:** RGB split = "corrupted signal" appears only on "MEDIA CHAOS?" and never after 2.0 s. The fixed
playhead = "control is a fixed reference that everything flows past". The centre-out hero reveal = "symmetry = resolved".

**Retirement rule:** when a pole ends, its vocabulary ends. Chaos effects lingering after the turn make the "control" claim unbelievable.

## Step 3 · Half-second beat sheet

**Decision:** what owns each moment?

Write a row every 0.5 s: one **dominant** motion (the thing the eye must follow), at most one **supporting** motion,
an **ambient** layer that keeps the frame alive, the **audio**, the **effects** used, and what the viewer **reads first**.

Rules:
- Exactly one dominant. Two dominants compete and the viewer reads neither.
- A supporting motion must not start on the same frame as the dominant. Offset it ≥ 100 ms.
- Read the sheet top to bottom as prose. If it's a list of things appearing, it's a slideshow; it should read as cause and effect.
- A row whose dominant is "hold on X" is a decision: either a declared rest or a defect.

**Render Dock (honest):** the 3.5 s row of v1 reads "hold on title (almost nothing moves)". Written down, that row is
obviously empty. In v1 nobody wrote it down, and the render has a 1 s dead hold there (FAIL 2.90–3.87 s).

## Step 4 · Ranked impacts and energy targets

**Decision:** which moments must hit hardest, in what order?

1. List every hit (cuts, reveals, snaps).
2. Rank them by narrative weight. The payoff (brand / product name) is rank 1. The turn of the polarity is usually rank 2.
3. Scale everything by rank: flash amount, zoom, impact sound gain, how quiet the frames before it are.
4. Plan anticipation for each ranked hit: ease-in acceleration, a riser, a zoom ramp, a moment of reduced motion.
5. Give each scene an energy level that follows the story. The from-pole is often `high`, the demo `medium`, the end card `rest`.

**Render Dock:** measured peaks are 8.5 s = 129, 2.0 s = 98, 6.5 s = 66, matching ranks 1 to 3. v1 got this right.
But the chaos scene is planned `high` and still dips at 1.0–1.5 s below the typical half-second of the calmer
scenes. That was a planning miss (nothing new happens in that half second), and the measurement margin is small (1.79 vs 1.83).

## Step 5 · Easing by narrative role

**Decision:** how does each motion accelerate and settle?

Choose the curve from what the motion *is doing in the story*, not from what looks nice in isolation:
- **arrive** → expo-out: fast attack, long settle. It reads as confident and expensive.
- **depart / build into a cut** → expo-in: acceleration, which is anticipation.
- **transform in frame** → cubic in-out: a state change both starts and ends gently.
- **pop** → back-out, only for small confirmations (checks, nodes, logo).
- **mechanical** → linear, only for things that should feel like machines (scrolling tracks, particles, spinners).

Duration: arrivals 0.4–0.6 s; a hero settle 0.9–1.2 s; transitions 0.12–0.25 s. The more confident the message, the longer the settle.

**Render Dock:** "MEDIA CHAOS?" settles in 0.45 s and jitters. "PRODUCTION CONTROL" focus-pulls in over 0.9 s with
no jitter. The difference in speed *is* the message.

## Step 6 · Stagger and typographic choreography

**Decision:** in what order do parts of a group move, and what does the order say?

- Step size: characters 25–40 ms, list rows 100–150 ms, nodes 60–80 ms.
- Direction: left→right = process / reading; centre-out = resolution; bottom-up out of a mask = precision.
  Collapsing tracking (wide → tight) means "pulling together". Random order means chaos.
- Simultaneity is a statement, so use it once: v1's 32 cards snap to the grid on the same frame because order arrives at once.
- Text and action: a word should enter *with* the action it names, as a caption, not before it as a headline.
  v1: DRAG at 4.12 s as the cursor approaches, ORGANIZE at 4.78 s while the card is carried, RENDER at 5.45 s just before progress starts.

## Step 7 · Accent budget and density

**Decision:** what deserves colour, and how much is on screen?

- One accent colour, reserved for meaning: the key word, the punctuation that carries tone, progress and done states, the brand.
  Budget ≤ about 10 % of frame pixels outside the end card. If gold is everywhere, it means nothing.
- White carries information; grey is environment; the background is never flat (radial lift, faint grid, grain).
- Density (elements that move or matter) falls toward the payoff, starting at the first to-pole scene.
  Render Dock: 32 → 14 → 11 → 3. The end card has the fewest elements and the biggest hit.

## Step 8 · Anticipation, transitions, quiet

**Decision:** how does each moment hand over to the next, and where does it rest?

- **Anticipation:** every ranked hit gets a build: ease-in acceleration into the cut, a riser, a zoom ramp, a brief reduction.
- **Transitions follow meaning:** a whip pan moves sideways (next topic, same level); a zoom-through goes deeper; a flash cut is the payoff.
- **Sound placement:** transients (impact, glitch, tick) land on the frame of maximum visual change. Swells (whoosh,
  riser) start early (`audio_offset` −0.1 to −0.2 s) so they peak on the cut.
- **Quiet is planned:** declare every intended stillness with a reason. The end card always. Optionally a breath
  before the biggest hit. Everything else that is still is dead air.

---

## Choosing *not* to use an effect

Ask, in order:
1. Does it express this scene's pole? If not, cut it.
2. Does another effect already carry that meaning in this beat? If so, cut the weaker one.
3. Would it start on the same frame as the dominant motion? Then move it or cut it.
4. Is the scene already at its planned density? Then cut it.
5. Will it still be running when the next scene needs the eye? Then retire it earlier.

"Clean but boring" means the quiet is everywhere. "Chaotic and amateur" means there is no quiet. The goal is
contrast: one dominant motion, at most one supporting motion, an ambient layer, and quiet placed deliberately before the hits.
