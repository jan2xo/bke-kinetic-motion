# BKE Kinetic Motion

This repository is being bootstrapped from the original Hark v2.1.0 production skill.

**Current status:** GitHub Actions render workflow is committed, but the original kit files have **not yet been imported into this repository**. The workflow requires `SKILL.md`, `scripts/`, `templates/`, `fonts/`, and related source files; it cannot produce video until those files are present.

## Import original kit

Extract the repository-ready ZIP at the repository root and commit its contents (not the ZIP itself). Preserve the original `SKILL.md` and all source files. The complete package includes a `.github/workflows/render.yml` workflow.

## Render

After importing the kit, open **Actions → Render Motion → Run workflow**. This initial workflow renders the 6-second 3D demonstration from `templates/promo_3d_template.py`, generates original audio, encodes MP4, runs QA, and uploads artifacts.

This is **not** yet a custom Render Dock 15-second renderer. Add a project-specific renderer and timeline to produce that advertisement.

## ChatGPT skill

The original `SKILL.md` is available in the separate complete skill package. Uploading an MD file to a conversation supplies instructions for that conversation but does not permanently install a skill across all chats. Use a supported custom skill installation mechanism where available.
