# Bounce Bhai Shorts 🫧

Automated YouTube Shorts pipeline for **Bounce Bhai** ([@bouncebhaiofficial](https://www.youtube.com/@bouncebhaiofficial)). It generates physics-based Shorts (ball races and ball-escape challenges, plus periodic game promos), renders them, and uploads with localized metadata.

## Current pipeline

`scripts/make_short.sh` runs in two stages:

1. **`prepare`**
   - Picks a format via `scripts/insights.py format` unless `BB_FORMAT` is set (workflow input/env override).
   - Supported/used formats:
     - `race` – 3-ball parkour race (`scripts/make_race.py` → `engine/sim_race.py`)
     - `sim` – ball-escape/break challenge (`scripts/make_sim.py` → `engine/sim_escape.py`)
     - `promo` – Bhai Drive game promo (`scripts/make_promo.py` → `scripts/promo.py`)
     - `multiply` – ball-multiply challenge (manual/forced use; `scripts/make_multiply.py` → `engine/sim_multiply.py`)
   - Writes `out/<name>.json` config/metadata and `out/current_name.txt`.

2. **`publish`**
   - Renders/animates the selected format.
   - For race/sim/multiply, copies the rendered MP4 to `out/<name>_final.mp4` and uploads.
   - For promo, records/composes via `scripts/promo.py` then uploads.
   - A legacy story/cartoon path still exists in code for non-sim formats in some branches, but the normal automated Shorts flow is race/sim/promo.
   - Uploads via `scripts/upload.py` (YouTube Data API v3) with titles/descriptions/localizations, tags/hashtags, and a first comment when possible.

Every workflow run uploads artifacts (`out/*_final.mp4`, `*.srt`, `*.json`) for 14 days.

## Scheduling and cadence

- Workflow: `.github/workflows/shorts.yml`
- Cron wakes 3×/hour (`:10`, `:30`, `:50`) to avoid dropped schedules, but a **gate** controls actual posting:
  - Scheduled runs only post during allowed IST hours listed in `data/schedule.json` (`hours_ist`).
  - Scheduled runs only post if the last non-`long_story` post with a `video_id` is at least `data/schedule.json:min_gap_min` minutes old.
  - Manual runs (`workflow_dispatch`) bypass the time/gap gate.
- `data/schedule.json` is the source of truth for posting windows and minimum spacing (tuned to reduce self-competition/cannibalization).

## Setup (GitHub Actions)

### Secrets
Configure in **Settings → Secrets and variables → Actions** as needed:

| Secret | Purpose |
|---|---|
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | YouTube upload credentials (OAuth). |
| `YT_CHANNEL_ID` (optional but recommended) | Expected channel ID; upload aborts if credentials don’t match. |
| `MY_VOICE_KEY` (optional) | Unlocks encrypted voice/token assets if used by enabled formats/workflows. |
| `NARA_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY` (optional) | Model/API keys used by specific scripts/paths when configured. |
| `NTFY_TOPIC` (optional env/secret depending on setup) | Phone notifications via ntfy (see `scripts/guard.py`). |

> Note: `secrets/yt_token.enc` may be used by some workflows if `MY_VOICE_KEY` is available; prefer keeping credentials in GitHub secrets and rotate regularly.

### Variables
| Variable | Purpose |
|---|---|
| `YT_PRIVACY` | `public` (default), `unlisted`, or `private`. |
| `BB_DESKTOP` | Set to `1` to enable the optional studio desktop step. |
| `BB_PROMO` | Set to `0` to disable daily promo selection (if used by insights logic). |

### Manual run
**Actions → Bounce Bhai Shorts → Run workflow**. You can provide a `format` input (`race`, `sim`, `promo`, `multiply`) to force a format.

## Local development

Requirements depend on the format/path you run. For the common race/sim/upload tooling:

```bash
python -m pip install -r requirements.txt
```

Additional tools may be required for specific formats (e.g. `ffmpeg`, `blender`, Playwright/Chromium for promo capture, or voice/TTS stacks for legacy story paths). See script headers and workflow steps for the exact environment.

To run the pipeline locally (example):

```bash
bash scripts/make_short.sh prepare
bash scripts/make_short.sh publish
# or
bash scripts/make_short.sh all
```

Set env vars such as `BB_FORMAT`, `YT_*`, etc. as needed. Upload is skipped automatically if YouTube secrets are not set.

## Repo notes

- `data/history.json` tracks posted/generated entries; CI appends and pushes updates.
- `scripts/insights.py` uses history/stats to inform format choices and prompting signals.
- Hooks/titles/descriptions/comments/tags are generated to encourage guessing, comments, and watch-through; tune `scripts/make_race.py`, `scripts/make_sim.py`, and `data/schedule.json` based on performance.
- Encrypted assets/credentials may exist under `secrets/` and `voice/`; handle and rotate with care.

## License

MIT — see [LICENSE](LICENSE). Third-party assets/models/fonts may have their own licenses (see e.g. `assets/characters/LICENSE.txt`).
