# timeline.json · shared event manifest (schema "bke-motion-timeline/1")

One file describes every scene, beat and sync point. The renderer and the music code both read it, and the QA
tools compare the render against it. Times are seconds from the start of the video.

```jsonc
{
  "schema": "bke-motion-timeline/1",
  "duration": 6.0, "fps": 30, "bpm": 120, "tolerance_ms": 34,      // tolerance: about 1 frame at 30 fps
  "polarity":   {"from": "...", "to": "...", "statement": "<product> turns <from> into <to>."},
  "vocabulary": {"from": [{"effect": "rgb_split", "meaning": "corrupted signal"}], "to": [...], "neutral": [...]},
  "accent":     {"color": "#FFC228", "budget_pct": 10, "reserved_for": ["key word", "progress", "brand"]},
  "easing":     {"arrive": "expo_out", "depart": "expo_in", "transform": "cubic_in_out", "pop": "back_out",
                 "pop_targets": "logo, small UI only", "mechanical": "linear"},
  "stagger":    {"chars_ms": 35, "items_ms": 120, "rule": "..."},
  "music":      {"groove_from": 2.0, "hats_from": 3.0},                 // optional bed structure for music_synth
  "scenes": [{"id": "chaos", "start": 0, "end": 2, "text": "...", "pole": "from", "energy": "high", "density": 24, "emotion": "pressure"}],
  "beats":  [{"t": 0.0, "dominant": "...", "supporting": null, "ambient": "...", "audio": "...", "effects": ["scatter"], "read_first": "..."}],
  "events": [{"id": "reveal", "t": 2.0, "kind": "impact", "style": "cut_flash", "visual": "...", "audio": "impact",
              "audio_offset": 0.0, "gain": 0.9, "rank": 2, "sync": "required", "tolerance_ms": 34, "duration": 0.55,
              "anticipation": "riser + expo-in exit"}],
  "quiet":  [{"start": 5.1, "end": 6.0, "reason": "end card rest"}],
  "audio_bed": ["kick", "hat", "clap", "pad", "pluck", "bass"],          // bed cues exempt from 1:1 sync
  "motion_qa": {"style": "kinetic"}                                       // + any motion_energy threshold override
}
```

## Fields that matter most
- `events[].t`: the frame of **maximum visual change** for that event (for an expo-out entrance, about 2–3 frames after it starts).
- `events[].audio_offset`: seconds the sound is shifted from `t` (negative = earlier). Use it for swells that must peak on the cut.
- `events[].sync`: `required` (picture and sound), `visual_only` (no sound allowed), `audio_only` (a build with no single visual frame).
- `events[].kind`: `impact` (ranked hit), `transition`, `accent` (small sync: glitch, tick, landing), `text`, `reveal`, `anticipation`, `camera` (v2.1: a 3D camera move; needs `move3d: {type: dolly|orbit|crane|static, end, ease, rank, meaning, degrees?}`; top-level `camera3d: {lens_mm, rig}`; see docs/3D_DECISIONS.md).
- `events[].rank`: unique 1..n over the impacts; 1 = payoff.
- `scenes[].energy`: `high | medium | low | rest`, checked against the measured body energy.
- `quiet`: declared stillness. Holds inside it (≥ 80 % overlap) are INTENTIONAL, not failures.

## Logs the code writes
- **Audio cue log** (`music_synth.py --cue-log`): `[{"t": 2.0, "cue": "impact", "gain": 0.9, "event_id": "reveal"}, ...]`
- **Visual log** (renderer, e.g. `promo_template.py render|vlog`): `[{"event_id": "reveal", "t": 2.0, "scene": "reveal"}, ...]`

## Library
```python
import timeline as TL
T = TL.load('timeline.json')
T.event('reveal').t, T.event('whip').audio_time, T.events(kind='impact'), T.scene_at(3.1).id, T.in_quiet(9.8), T.audio_cues()
```
