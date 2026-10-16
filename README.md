# Bounce Bhai Shorts 🫧

Automatic YouTube Shorts for **Bounce Bhai** (@bouncebhaiofficial): a 3D-looking ball-escape physics
simulation, a fresh micro-story narrated in the creator's own cloned voice (Hindi), soft code-made
background music, Hinglish captions, and Hindi / English / Telugu subtitles + translated titles.

No AI images or video. No bounce sounds. Voice = creator's own clone (exempt from YouTube's AI label).

## How it works
`scripts/make_short.sh` runs the whole pipeline:

1. `write_story.py` – writes a new story with the free Groq API (never repeats `data/history.json`)
2. `voice.py` – narrates each line with Chatterbox Multilingual (MIT licence, runs on CPU)
3. `engine/render3d.py` – renders the 1080×1920 3D simulation; the ball escapes on the story's payoff word
4. `finish.py` – mixes voice + soft pad music, pads the ending, fixes subtitle timing
5. `upload.py` – uploads to YouTube with subtitles, translations and a comment

The GitHub Action `.github/workflows/shorts.yml` runs this every hour (free on a public repo).
Every video is also saved under **Actions → the run → Artifacts** for 14 days.

## One-time setup
Only **one** repo secret is needed (Settings → Secrets and variables → Actions → New repository secret):

| Secret | What |
|---|---|
| `VOICE_KEY` | unlocks `voice/ref.wav.enc` (your voice sample) and `voice/keys.env.enc` (YouTube API credentials) |

Stories are written with free **GitHub Models** using the workflow's own token (no key needed).
Optional overrides as secrets: `GROQ_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

**Variables**
| Name | Value |
|---|---|
| `AUTO_POST` | `true` to post hourly. Leave unset while Hark is posting, or you get two Shorts an hour. |
| `YT_PRIVACY` | optional: `public` (default), `unlisted` or `private` |

YouTube API: Google Cloud project `bouncebhai`, OAuth client `bouncebhai-actions`, token for the Bounce Bhai channel.
While the consent screen is in **Testing**, Google expires the refresh token after 7 days. To renew: OAuth Playground
(own credentials) → scope `youtube.force-ssl` → pick Bounce Bhai → exchange → save as secret `YT_REFRESH_TOKEN`.

## Manual run
Actions → **Bounce Bhai Shorts** → **Run workflow**.

## Locally
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
openssl enc -d -aes-256-cbc -pbkdf2 -in voice/ref.wav.enc -out voice/ref.wav -pass pass:YOUR_VOICE_KEY
GROQ_API_KEY=... bash scripts/make_short.sh
```
Needs ~6 GB free RAM. Voice takes ~1 minute per line on a normal CPU.
