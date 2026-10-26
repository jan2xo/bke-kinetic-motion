# BKE Kinetic Motion

Source-of-truth repository for the Hark v2.1.0 code-first motion production skill and GitHub Actions render worker.

**Status:** bootstrap in progress. The complete original kit is distributed as `bke-kinetic-motion-v2.1.0.zip` and must be imported before the render workflow can succeed. This repository does not yet contain the full engine, templates, scripts, fonts, or tests.

## Skill
Install the full skill directory (including `SKILL.md`, `scripts/`, `templates/`, `fonts/`, and `docs/`) in an agent environment supporting custom skills. A GitHub README or `SKILL.md` by itself does not install a ChatGPT skill.

## Render
After the full kit is committed, open **Actions → Render Motion → Run workflow**. Choose `3d-demo` or `renderdock-v1`. The workflow renders on Ubuntu, generates original procedural audio, encodes MP4, runs video/temporal QA, and uploads artifacts.

Do not confuse the demo workflow with a custom Render Dock 15-second production. Each new production requires its own project renderer and matching timeline.
