"""Niche discovery: Claude proposes niches (with live web search), the YouTube
Data API measures them, and scoring.py ranks them."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from ytagent import scoring
from ytagent.llm import LLM

NICHE_SCHEMA = {
    "type": "object",
    "properties": {
        "niches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "target_audience": {"type": "string"},
                    "search_keywords": {"type": "array", "items": {"type": "string"}},
                    "rpm_low_usd": {"type": "number"},
                    "rpm_high_usd": {"type": "number"},
                    "rpm_rationale": {"type": "string"},
                    "faceless_friendly": {"type": "boolean"},
                    "evergreen": {"type": "integer"},
                    "extra_revenue": {"type": "array", "items": {"type": "string"}},
                    "example_video_ideas": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "string"},
                },
                "required": [
                    "name", "description", "target_audience", "search_keywords",
                    "rpm_low_usd", "rpm_high_usd", "rpm_rationale", "faceless_friendly",
                    "evergreen", "extra_revenue", "example_video_ideas", "risks",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["niches"],
    "additionalProperties": False,
}

NICHE_SYSTEM = """You are a YouTube strategist who specialises in finding profitable niches for new channels.
Think like an analyst: favour niches where advertisers pay well (high RPM), audiences are large and growing,
and new channels can still break through. The channel will be produced with AI assistance (scripted narration,
stock/generated visuals), so weigh how well each niche can be done at high quality in that format
without a presenter on camera. YouTube does not monetise mass-produced, repetitive, or low-effort content,
so only propose niches where genuinely useful, original videos are possible."""


def brainstorm_niches(llm: LLM, cfg: dict) -> list[dict]:
    r = cfg["research"]
    prompt = f"""Use web search to check current YouTube trends, recent RPM/CPM reports by category,
and what faceless channels are growing right now. Then propose {r['niche_count']} specific YouTube niches.

Creator preferences:
- Interests: {', '.join(r['interests']) or 'open to anything'}
- Avoid: {', '.join(r['avoid']) or 'nothing specific'}
- Language: {r['language']}; primary audience region: {r['region']}
- Preferred video format: {r.get('format_preference') or 'any faceless format'}

For each niche:
- Be specific ("personal finance for nurses", not "finance").
- search_keywords: {r['keywords_per_niche']} phrases a viewer would actually type into YouTube search.
- rpm_low_usd / rpm_high_usd: realistic creator RPM range (after YouTube's cut) for this audience/region,
  with a short rationale citing what you found.
- evergreen: 0-10, how long videos keep getting views.
- extra_revenue: affiliate programs, sponsors, or products that fit.
- example_video_ideas: 5 strong, specific video titles.
- risks: policy, accuracy, or competition risks."""
    return llm.json(NICHE_SYSTEM, prompt, NICHE_SCHEMA, web_search=True)["niches"]


class YouTubeResearcher:
    """Read-only YouTube Data API v3 client (API key, no OAuth)."""

    def __init__(self, api_key: str | None = None, region: str = "US", lookback_days: int = 90):
        from googleapiclient.discovery import build

        key = api_key or os.environ.get("YOUTUBE_API_KEY")
        if not key:
            raise RuntimeError("YOUTUBE_API_KEY is not set (see .env.example)")
        self.yt = build("youtube", "v3", developerKey=key, cache_discovery=False)
        self.region = region
        self.lookback_days = lookback_days

    def top_videos(self, keyword: str, max_results: int = 25) -> list[dict]:
        """Most-viewed videos for `keyword` in the lookback window (~102 quota units)."""
        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=self.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        search = self.yt.search().list(
            q=keyword, part="id", type="video", order="viewCount",
            publishedAfter=since, regionCode=self.region, maxResults=max_results,
        ).execute()
        ids = [item["id"]["videoId"] for item in search.get("items", [])]
        if not ids:
            return []

        vids = self.yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute()["items"]
        channel_ids = sorted({v["snippet"]["channelId"] for v in vids})
        subs = {}
        for i in range(0, len(channel_ids), 50):
            chans = self.yt.channels().list(
                part="statistics", id=",".join(channel_ids[i:i + 50])
            ).execute()["items"]
            for c in chans:
                stats = c["statistics"]
                # Hidden subscriber counts are treated as "big" to stay conservative.
                subs[c["id"]] = int(stats.get("subscriberCount", scoring.BIG_CHANNEL_SUBS))

        out = []
        for v in vids:
            published = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
            out.append({
                "title": v["snippet"]["title"],
                "channel": v["snippet"]["channelTitle"],
                "views": int(v["statistics"].get("viewCount", 0)),
                "age_days": max((now - published).days, 1),
                "channel_subs": subs.get(v["snippet"]["channelId"], scoring.BIG_CHANNEL_SUBS),
            })
        return out


def analyze_niche(niche: dict, yt: YouTubeResearcher, keywords_per_niche: int) -> dict:
    per_keyword, examples = [], []
    for kw in niche["search_keywords"][:keywords_per_niche]:
        videos = yt.top_videos(kw)
        per_keyword.append(scoring.keyword_metrics(videos))
        # Keep small-channel breakouts as proof points / inspiration.
        examples += [v for v in videos if v["channel_subs"] < scoring.SMALL_CHANNEL_SUBS]
    metrics = scoring.combine_metrics(per_keyword)
    result = scoring.opportunity_score(metrics, niche)
    examples.sort(key=lambda v: v["views"], reverse=True)
    return {**niche, "metrics": metrics, **result, "breakout_examples": examples[:5]}


def format_report(niches: list[dict]) -> str:
    lines = [
        "# YouTube niche opportunity report",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Revenue figures are rough estimates "
        "for a monetised channel posting ~12 videos/month, based on how small channels perform in each niche.",
        "",
        "| # | Niche | Score | RPM (USD) | Median views/day | Small-channel share | Est. $/month |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, n in enumerate(niches, 1):
        m = n["metrics"]
        lines.append(
            f"| {i} | {n['name']} | {n['score']} | {n['rpm_low_usd']:.0f}-{n['rpm_high_usd']:.0f} "
            f"| {m['median_views_per_day']:,.0f} | {m['small_channel_share']:.0%} "
            f"| ${n['est_monthly_revenue_usd']:,} |"
        )
    for i, n in enumerate(niches, 1):
        lines += [
            "", f"## {i}. {n['name']} — score {n['score']}", "",
            n["description"], "",
            f"**Audience:** {n['target_audience']}  ",
            f"**RPM:** ${n['rpm_low_usd']:.0f}-{n['rpm_high_usd']:.0f} — {n['rpm_rationale']}  ",
            f"**Extra revenue:** {', '.join(n['extra_revenue'])}  ",
            f"**Risks:** {n['risks']}", "",
            "**Video ideas:**", *[f"- {t}" for t in n["example_video_ideas"]],
        ]
        if n["breakout_examples"]:
            lines += ["", "**Small channels winning here:**"]
            lines += [
                f"- {v['title']} — {v['channel']} ({v['channel_subs']:,} subs, {v['views']:,} views)"
                for v in n["breakout_examples"]
            ]
    return "\n".join(lines) + "\n"
