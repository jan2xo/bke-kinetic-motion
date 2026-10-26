# 3D decisions (v2.1)

The 3D module (`scripts/mg3d.py`) is a **2.5D card renderer**: flat textured rectangles placed and rotated in a real
3D space, seen through a real pinhole camera, drawn back to front with Pillow. No meshes, no GPU, no new dependency.
Every rule below says what it's for, so you know when you may break it.

## 1. When 3D earns its place
Use depth when depth *means* something in the story. Otherwise stay flat (v2 2D is faster and sharper).

| Story need | 3D answer | Why 2D falls short |
|---|---|---|
| Chaos / overload | cards scattered through depth, tumbling, with parallax | 2D scatter reads as a pattern, not a mess |
| Order arriving | many cards snapping from depth onto one flat plane | the depth collapsing *is* the message |
| Scale / "everything in one place" | camera receding from a wall of cards | 2D zoom-out has no parallax, so it feels like a resize |
| Focus | depth of field pulled from one plane to another | 2D blur has no physical logic to follow |
| Premium reveal | a single slow move, rim light sweeping across cards | a flat sweep looks like a filter |

Don't use 3D for: type-only pieces, data that must be read precisely, more than about 60 visible cards, or anything
that needs real geometry (characters, products, liquids).

## 2. Camera
- **Lens 35–50 mm equivalent** (full-frame 24 mm sensor height): 40 mm = 33.4° vertical FOV is the default.
  Wider than 35 mm distorts cards near the edges and makes type stretch. Longer than 50 mm flattens the depth you paid for.
  Enforced by `lint_rig` and `timeline.py check` (`camera3d.lens_mm`).
- **Design distance:** `Camera.design_distance(lens)` puts the z=0 plane at 1 world unit = 1 output pixel, so a
  flat layout designed in pixels lands exactly where you drew it.
- **One camera move per shot.** Stacked moves (dolly *and* orbit at once) read as indecision and fail `lint_rig` and
  the plan check. Rigs: `static`, `dolly`, `orbit` (max 25°), `crane`.
- **Always eased in and out** (`eio`/`cubic_in_out`/`sine`). A linear start is a jolt. An overshooting camera
  (`back_out`, `elastic`) makes people feel seasick. Both are rejected.
- **The camera stops before the payoff.** The final scene's camera travel must be 0 (lint: "camera still in the final scene").
  Type that is being read must not drift.
- **Every move needs a `meaning`** in the manifest (`move3d.meaning`), like any other effect.

## 3. Depth and readability
- **Type stays frontal:** max 20° tilt while it is being read (`check_readable`). The end card is flat, frontal and
  still (tilt 0°, travel 0).
- **Read-first type is never crossed.** If a card would pass in front of type that must be read, give the type
  `layer=1`: it composites after everything in layer 0, whatever its depth. This breaks physical correctness on
  purpose, because readability wins. Prefer keeping the type's screen window clear, and use the layer as the safety net.
- **Depth of field follows attention:** focus on what reads first, then pull to what reads next (`FOCUS_PULL`). Blur is
  quantised into ≤5 z-bands, so cost stays bounded and nearby cards share a blur.
- **Fog/dimming with distance** separates planes on dark backgrounds, where blur alone is too subtle.
- **Near-plane fade:** cards straddling the near plane are culled and cards about to reach the lens fade out, so a
  wildly distorted quad never fills the frame.

## 4. Motion in 3D
- **The camera is not choreography.** A dolly scales the whole frame about its centre. `motion_energy.py` (v2.1)
  measures that scale and counts it as camera motion. A stretch where only the camera moves gets
  `camera_only` WARN, the same as a 2D pan. Give the frame something that moves *within* it. Lateral travel is ideal,
  because a zoom can't explain it. The template's crossers exist for exactly this reason.
- **Scatter → align is the core 3D gesture:** `scatter_align` interpolates position and rotation from a scattered
  state to a flat layout with expo-out and an optional stagger. The largest step lands on the declared frame.
- **Light as an accent:** a rim light sweeping across a flat grid (the template's `rim_sweep`) is a cheap, readable
  "premium" beat. Budget it like any accent: one per piece.
- **Recede to show scale:** moving the content away (not the camera) keeps the final camera still.

## 5. Rendering method and why
| Decision | Why |
|---|---|
| Painter's algorithm (sort by camera-space depth of each card centre) | no z-buffer in Pillow; cards are flat, so centre depth is right whenever cards don't intersect |
| Pillow `PERSPECTIVE` warp per card at supersample S | exact projective mapping of a planar card; one call per card |
| Cull behind / straddling near plane / edge-on (>85°) / off-screen | invisible or degenerate quads cost time and can explode the warp |
| DOF as ≤5 quantised blur bands | per-card Gaussian at unique radii is slow; banding is invisible in motion |
| Ground shadow = projected, blurred silhouette on y = ground | sells contact with the floor for about 5 % of the frame cost |
| Ambient + key + rim, Lambert-like on the card normal | enough to read orientation; not physically based |
| Supersample S=2, LANCZOS down | removes edge crawl on thin rotated cards |

## 6. Performance (measured, 2-core sandbox, 1920×1080, S=2)
- `mg3d.py bench` (30 cards, single process): **0.44 s/frame** mean, 0.51 s max.
- Demo template (30 grid cards + 8 crossers + headline + floor grid + shadows + DOF): **0.63 s/frame** mean,
  1.05 s max (single process). Full 180-frame render: **about 74 s wall-clock on 2 cores (about 0.41 s/frame throughput)**.
- Cost scales roughly linearly with visible cards and with S². Practical ceiling: about 60 visible cards and textures
  up to about 600×400 px each at S=2 before frames pass 1.5 s. Use `--preview` (S=1) while iterating.

## 7. Known limits (honest)
- **No true meshes:** only flat cards. No extrusion, bevels, curved surfaces, or 3D type.
- **No physically based lighting:** no reflections, GI, specular maps or soft area lights. Shadows go only on the ground plane.
- **Painter's algorithm can't resolve intersecting cards** (two cards passing through each other, or one long card
  spanning another's depth). The sort is per card, not per pixel. Design so cards don't interpenetrate.
- `layer` overrides depth by design. A card in a higher layer can "float" in front of nearer geometry.
- DOF is per card (one blur for the whole card), not per pixel. A steeply tilted card is blurred uniformly.
- CPU only: about 0.4–0.6 s per 1080p frame. Long pieces (60 s+) need a coffee or a preview render.
- Zoom detection in `motion_energy.py` assumes the scale is centred on the frame (true for dollies toward the target).
  An off-centre push reads partly as content motion.
