<div align="center">

# 🫧 Bounce Bhai Shorts

### Physics chaos. One-tap curiosity. Automated Shorts, end to end.

**Automated YouTube Shorts pipeline for [@bouncebhaiofficial](https://www.youtube.com/@bouncebhaiofficial)** — generating ball-race and ball-escape bangers (plus Bhai Drive promos), rendering them, and shipping uploads with localized metadata.

[![YouTube](https://img.shields.io/badge/YouTube-%40bouncebhaiofficial-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/@bouncebhaiofficial)
[![Workflow](https://img.shields.io/badge/GitHub_Actions-Automated-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](.github/workflows/shorts.yml)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](requirements.txt)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

<br/>

`Plan → Simulate → Render → Localize → Upload → Learn`

</div>

---

## ⚡ What this repo does

This isn’t just a script that spits out a video. It’s a full Shorts factory:

- 🎯 **Picks a format** automatically (`race`, `sim`, `promo`; `multiply` available for manual/forced runs)
- 🧠 **Generates hooks & metadata** tuned for curiosity, guesses, comments, and watch-through
- 🧪 **Tracks variants** (A/B/series context in generated configs) to support iteration
- 🕒 **Respects cadence gates** so posts are spaced out instead of cannibalizing each other
- 🎬 **Renders & packages** final Shorts with subtitles/config artifacts
- ☁️ **Uploads via YouTube Data API v3** with localized titles/descriptions, tags/hashtags, and a first comment (when possible)
- 📦 **Saves run artifacts** in Actions for 14 days

---

## 🎮 Formats

| Format | Vibe | How it’s made | Notes |
|---|---|---|---|
| `race` | 3-ball parkour race to the finish | `scripts/make_race.py` → `engine/sim_race.py` | Default/high-share format; prediction hooks (“guess the winner”, color/team picks) |
| `sim` | Ball escape / break challenge | `scripts/make_sim.py` → `engine/sim_escape.py` | “How many bounces?”, last-moment suspense hooks |
| `promo` | Bhai Drive game promo Short | `scripts/make_promo.py` → `scripts/promo.py` | Periodic promo slot in auto selection |
| `multiply` | Ball-multiply challenge | `scripts/make_multiply.py` → `engine/sim_multiply.py` | Manual/forced use (workflow input / `BB_FORMAT`) |

> Format selection is handled by `scripts/insights.py` (with stats/history signals) unless overridden.

---

## 🧵 Pipeline flow

```text
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Cron/Gate  │───▶│  Pick format     │───▶│  Generate config │───▶│  Render/compose │
│  (IST + gap)│    │  + hook/metadata │    │  (out/*.json)    │    │  (mp4/srt/etc.) │
└─────────────┘    └──────────────────┘    └──────────────────┘    └─────────────────┘
                                                                            │
                                                                            ▼
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  History    │◀───│  Persist/log     │◀───│  Upload to YT    │◀───│  Finalize asset │
│  + insights │    │  (CI artifacts)  │    │  (localized)     │    │  out/*_final.mp4│
└─────────────┘    └──────────────────┘    └──────────────────┘    └─────────────────┘
```

### What `make_short.sh` does

| Stage | Command | What happens |
|---|---|---|
| **Prepare** | `bash scripts/make_short.sh prepare` | Picks format (`BB_FORMAT` override or `insights.py`), generates config/metadata, writes `out/<name>.json` and `out/current_name.txt` |
| **Publish** | `bash scripts/make_short.sh publish` | Renders/animates the chosen format, prepares `out/<name>_final.mp4`, uploads (when creds are set) |
| **All** | `bash scripts/make_short.sh all` | Runs prepare + publish |

---

## ⏱️ Scheduling & cadence (anti-cannibalization)

Automated posting is controlled by **`.github/workflows/shorts.yml`** + **`data/schedule.json`**.

- **Cron wakes:** 3×/hour (`:10`, `:30`, `:50`) to reduce dropped schedule risk
- **IST posting windows:** only allowed hours in `data/schedule.json` → `hours_ist`
- **Minimum gap gate:** scheduled runs post only if the last non-`long_story` post with a `video_id` is at least `min_gap_min` minutes old
- **Manual runs:** `workflow_dispatch` bypasses time/gap gates
- **Current cadence config:** evening-weighted, spaced windows to give each Short room to earn impressions

`data/schedule.json` (current):

```json
{
  "hours_ist": [7, 10, 13, 16, 19, 21],
  "min_gap_min": 150
}
```

> Tune cadence and hooks based on performance — small spacing changes can have a big impact on Shorts distribution.

---

## 🧲 Views-oriented content mechanics

The generators are built to make people *react*, not just watch:

- **Strong first-second hooks** (prediction, challenge, “guess in 3 seconds”, finish-line suspense)
- **On-screen sub-hooks** to reinforce the prompt
- **Richer descriptions/questions/comments** to encourage replies and guesses
- **Expanded tags/hashtags + localized title/description fields**
- **Series/episode and A/B tracking fields** in generated configs
- **Anti-title-fatigue logic** (avoids recently used/repetitive titles from history)
- **Team/variant pools** (where applicable) to keep the feed fresh without losing format identity

Tune these in:
- `scripts/make_race.py`
- `scripts/make_sim.py`
- `scripts/make_promo.py`
- `scripts/insights.py`
- `data/schedule.json`

---

## 🔐 Setup (GitHub Actions)

### 1) Secrets
Configure in **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|---|---:|---|
| `YT_CLIENT_ID` | ✅ (for upload) | YouTube OAuth client ID |
| `YT_CLIENT_SECRET` | ✅ (for upload) | YouTube OAuth client secret |
| `YT_REFRESH_TOKEN` | ✅ (for upload) | YouTube OAuth refresh token |
| `YT_CHANNEL_ID` | Recommended | Safety check: abort if credentials target a different channel |
| `MY_VOICE_KEY` | Optional | Unlocks encrypted voice/token assets when used by enabled paths |
| `NARA_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY` | Optional | API keys for specific scripts/paths when configured |
| `NTFY_TOPIC` | Optional | ntfy notifications (see `scripts/guard.py`) |

> `scripts/upload.py` skips upload cleanly if YouTube creds are missing (useful for local/dev runs).

### 2) Variables

| Variable | Purpose | Example |
|---|---|---|
| `YT_PRIVACY` | Upload privacy mode | `public` (default), `unlisted`, `private` |
| `BB_DESKTOP` | Enable optional studio desktop step | `1` |
| `BB_PROMO` | Toggle daily promo selection in insights logic (if used) | `0` to disable |

### 3) Manual run

**Actions → Bounce Bhai Shorts → Run workflow**

- Optional input: `format` = `race` | `sim` | `promo` | `multiply` (empty = auto)
- Manual runs bypass the scheduled time/gap gate

---

## 🧑‍💻 Local development

### Install core dependencies

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` covers the common race/sim/upload tooling. Some formats/paths may need extra system tools or optional deps (e.g. `ffmpeg`, `blender`, Playwright/Chromium for promo capture, voice/TTS stacks for legacy paths). Check script headers and workflow steps for the exact environment.

### Run locally

```bash
# Generate config/metadata
bash scripts/make_short.sh prepare

# Render + upload (upload skipped if YT creds not set)
bash scripts/make_short.sh publish

# Or both
bash scripts/make_short.sh all
```

Useful env vars: `BB_FORMAT`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `YT_CHANNEL_ID`, `YT_PRIVACY`, etc.

---

## 🗂️ Repo map (high level)

```text
.
├─ .github/workflows/shorts.yml   # Automation: cron wakes, gates, render/upload, artifacts
├─ data/
│  ├─ schedule.json               # IST posting windows + min gap gate
│  └─ history.json                # Generated/posted history used by insights & anti-fatigue
├─ scripts/
│  ├─ make_short.sh               # Prepare/publish orchestrator
│  ├─ insights.py                 # Format selection / performance-informed logic
│  ├─ make_race.py                # Race config + hooks/metadata
│  ├─ make_sim.py                 # Sim/escape config + hooks/metadata
│  ├─ make_promo.py               # Promo config + metadata
│  ├─ make_multiply.py            # Multiply config (manual/forced)
│  └─ upload.py                   # YouTube upload/localizations/comments
├─ engine/                        # Render/simulation engines per format
├─ assets/, voice/, secrets/      # Media/assets and sensitive material (handle carefully)
├─ docs/                          # Site/docs/game pages
└─ out/                           # Generated outputs (gitignored)
```

---

## 📈 Tuning playbook

When views dip, don’t guess wildly — iterate deliberately:

1. **Hook first:** test sharper prediction/challenge openers in `make_race.py` / `make_sim.py`
2. **Cadence:** adjust `data/schedule.json` (`hours_ist`, `min_gap_min`) to reduce overlap
3. **Format mix:** review `scripts/insights.py` choices and forced-run results
4. **Metadata:** refine questions/comments/tags/hashtags to drive replies and session intent
5. **Measure A/B fields:** use generated `ab`/series signals + YouTube analytics to keep winners
6. **Protect freshness:** keep anti-fatigue/title variety on so the feed doesn’t feel repetitive

---

## 🛡️ Notes & safety

- `data/history.json` is part of the feedback loop (and CI may append/push updates)
- Generated outputs/artifacts live under `out/` (ignored by git)
- Treat anything in `secrets/`, `.env*`, and encrypted assets with care; rotate credentials regularly
- Third-party assets/models/fonts may carry their own licenses (see e.g. `assets/characters/LICENSE.txt`)

---

## 📄 License

MIT — see [LICENSE](LICENSE).

<div align="center">

**Built to ship Shorts fast, test hooks faster, and keep the chaos entertaining.**



