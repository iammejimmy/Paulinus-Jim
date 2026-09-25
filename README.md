# ytagent: YouTube channel autopilot

An AI agent that:

1. **Finds profitable niches.** Claude searches the web for current trends and RPM data and proposes niches. The YouTube Data API then measures each one: demand, how often small channels break through, and how many top results big channels own. Everything is scored and written to `output/niche_report.md` with an estimated monthly revenue.
2. **Creates videos.** Claude writes the script (hook, story, payoff), the title, description, tags and thumbnail text, and lays out every scene. Visuals are **stick-figure storytelling** in the style of channels like *Ink Explainer*. A free voice (edge-tts) narrates, and ffmpeg assembles the video with a slow zoom on each scene.
3. **Posts on a schedule.** It uploads to your channel as scheduled videos (for example Mon/Wed/Fri at 3 pm), sets the thumbnail, and marks the video as AI-generated.

```
research ──► niche_report.md ──► create ──► [review / approve] ──► publish (scheduled)
                                   ▲                                     │
                                   └──────────── autopilot ──────────────┘
```

## Visual styles

| `visual_style` | Look | Cost |
|---|---|---|
| `ai` (default) | Illustrated stick-figure cartoons: big round heads, simple clothes and hair, colorful backgrounds. The closest match to Ink Explainer. Claude writes a detailed image prompt per scene with consistent character descriptions, and Gemini's image model draws it. | Needs `GEMINI_API_KEY` (roughly a few cents per image) |
| `stickfigure` | Built-in renderer: classic stick figures with poses, expressions, speech bubbles, props and settings. | Free |

If `ai` is set but there is no key, or an image request fails, that scene falls back to the built-in renderer, so a video never fails because of a single image.

## Setup

Requirements: Python 3.11+ and [ffmpeg](https://ffmpeg.org/download.html).

```bash
pip install -e .
cp .env.example .env                 # fill in keys
cp config.example.toml config.toml   # your interests, schedule, voice, style
```

Keys:

| Key | Used for | Where |
|---|---|---|
| `ANTHROPIC_API_KEY` | research, scripts, scene design | console.anthropic.com |
| `YOUTUBE_API_KEY` | niche stats (read-only) | Google Cloud Console → enable *YouTube Data API v3* → Credentials → API key |
| `client_secret.json` | uploading to your channel | same project → OAuth client ID → *Desktop app* → download JSON |
| `GEMINI_API_KEY` (optional) | AI illustrations | aistudio.google.com/apikey |

Connect your channel once (this opens a browser and saves `youtube_token.json`):

```bash
python -m ytagent auth
```

> Google limits unverified OAuth apps: uploads from an unverified project may be locked to private until the project passes Google's audit. Add yourself as a test user on the OAuth consent screen. For public scheduled uploads, request the audit (YouTube API Services → Audit and Quota Extension form).

## Usage

```bash
python -m ytagent research          # propose + score niches  → output/niche_report.md
python -m ytagent niches            # ranked list
python -m ytagent create -n 2       # make 2 videos in channel.niche (or the top niche)
python -m ytagent create --niche "Ancient history daily life"
python -m ytagent list              # every video + status
python -m ytagent approve 3 4       # after watching output/<video>/video.mp4
python -m ytagent publish           # upload approved videos into the next free slots
python -m ytagent autopilot         # create videos_per_run videos, then publish approved ones
```

Every video folder in `output/` has `video.mp4`, `thumbnail.jpg` and `plan.json` (script, scenes, description, and a suggested pinned comment).

### Running it automatically

- **On your computer:** schedule `python -m ytagent autopilot` with cron or Task Scheduler.
- **GitHub Actions:** `.github/workflows/autopilot.yml` runs Mon/Wed/Fri. Add repository secrets `ANTHROPIC_API_KEY`, `YOUTUBE_TOKEN_JSON` (the contents of `youtube_token.json`), and optionally `GEMINI_API_KEY`, `YOUTUBE_API_KEY` and `YTAGENT_CONFIG` (your whole `config.toml`). For fully hands-off posting, set `review_required = false` in that config. Rendered files are also saved as workflow artifacts.

## How niches are scored

For each niche, `ytagent/scoring.py` combines:

- **demand (30%):** median views/day of the most-viewed videos from the last 90 days
- **money (30%):** estimated RPM, meaning what you earn per 1,000 views after YouTube's cut
- **access (25%):** share of those top videos from channels under 50k subscribers, plus how far their views outrun their subscriber count, with a penalty when 1M+ channels dominate
- **fit (15%):** whether the niche works faceless, and how evergreen it is

`est_monthly_revenue_usd` is a rough estimate: 12 videos/month × the median small-channel video's views × RPM. It only applies once the channel is monetized (1,000 subscribers + 4,000 watch hours, or 10M Shorts views in 90 days).

## Staying monetizable

YouTube demonetizes "inauthentic" content, meaning mass-produced or repetitive videos. The agent is built to avoid that:

- Every video gets a fresh topic and angle (it tracks past titles), a researched script, and custom scenes. It never fills a template.
- `review_required = true` by default, so you watch each video before it goes out. Keep it on at least until you trust the output.
- Uploads set YouTube's *altered or synthetic content* flag (`disclose_synthetic_media`).
- Check facts in history, finance and science videos. Claude is told not to invent statistics, but you are the publisher.

Posting fewer, better videos (3 per week) beats volume.

## Tests

```bash
python -m unittest discover -s tests
```
