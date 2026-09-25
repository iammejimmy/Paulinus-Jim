"""Pure scoring functions: turn raw YouTube stats + Claude's niche estimate into a
0-100 opportunity score and a rough revenue estimate.

Signals, and why they matter:
  demand      median views/day of recent top videos: are people watching?
  money       estimated RPM (revenue per 1,000 views): what is a view worth?
  access      how often small channels break through (and how far their
              views outrun their subscriber count): can a NEW channel win?
  saturation  share of top results owned by 1M+ subscriber channels (a penalty)
  fit         can this be made well with AI narration + visuals (faceless),
              and does it stay relevant (evergreen)?
"""

from __future__ import annotations

import math
from statistics import median

SMALL_CHANNEL_SUBS = 50_000
BIG_CHANNEL_SUBS = 1_000_000

WEIGHTS = {"demand": 0.30, "money": 0.30, "access": 0.25, "fit": 0.15}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _log_norm(value: float, ceiling: float) -> float:
    """0 at value=0, 1 at value=ceiling, log-scaled in between."""
    return _clamp(math.log10(value + 1) / math.log10(ceiling + 1))


def keyword_metrics(videos: list[dict]) -> dict:
    """Aggregate stats for one keyword.

    Each video dict needs: views, age_days, channel_subs.
    """
    if not videos:
        return {
            "videos": 0,
            "median_views": 0,
            "median_views_per_day": 0.0,
            "small_channel_share": 0.0,
            "big_channel_share": 0.0,
            "median_outlier_ratio": 0.0,
            "small_channel_median_views": 0,
        }
    views = [v["views"] for v in videos]
    vpd = [v["views"] / max(v["age_days"], 1) for v in videos]
    small = [v for v in videos if v["channel_subs"] < SMALL_CHANNEL_SUBS]
    big = [v for v in videos if v["channel_subs"] >= BIG_CHANNEL_SUBS]
    # Views relative to channel size; floor subs so tiny channels don't explode it.
    outlier = [v["views"] / max(v["channel_subs"], 1_000) for v in videos]
    return {
        "videos": len(videos),
        "median_views": int(median(views)),
        "median_views_per_day": round(median(vpd), 1),
        "small_channel_share": round(len(small) / len(videos), 3),
        "big_channel_share": round(len(big) / len(videos), 3),
        "median_outlier_ratio": round(median(outlier), 2),
        "small_channel_median_views": int(median([v["views"] for v in small])) if small else 0,
    }


def combine_metrics(per_keyword: list[dict]) -> dict:
    """Average keyword metrics, ignoring keywords with no results."""
    rows = [m for m in per_keyword if m["videos"]]
    if not rows:
        return keyword_metrics([])
    out = {}
    for key in rows[0]:
        vals = [r[key] for r in rows]
        out[key] = sum(vals) if key == "videos" else round(sum(vals) / len(vals), 3)
    return out


def opportunity_score(metrics: dict, niche: dict) -> dict:
    """Return {'score': 0-100, 'components': {...}, 'est_monthly_revenue_usd': ...}.

    `niche` needs: rpm_low_usd, rpm_high_usd, faceless_friendly, evergreen (0-10).
    """
    rpm_mid = (niche["rpm_low_usd"] + niche["rpm_high_usd"]) / 2

    demand = _log_norm(metrics["median_views_per_day"], 50_000)
    money = _clamp(rpm_mid / 20)  # $20 RPM ~ top-tier finance/software niches
    breakout = _log_norm(metrics["median_outlier_ratio"], 10)  # views = 10x subs -> 1.0
    access = (0.6 * metrics["small_channel_share"] + 0.4 * breakout) * (
        1 - 0.5 * metrics["big_channel_share"]
    )
    fit = 0.5 * (1.0 if niche["faceless_friendly"] else 0.2) + 0.5 * _clamp(niche["evergreen"] / 10)

    components = {"demand": demand, "money": money, "access": access, "fit": fit}
    score = 100 * sum(WEIGHTS[k] * v for k, v in components.items())

    # What a small channel posting ~12 videos/month might earn once monetized,
    # if its videos perform like the median small-channel video in this niche.
    typical_views = metrics["small_channel_median_views"] or metrics["median_views"] * 0.1
    est_revenue = typical_views * 12 * rpm_mid / 1000

    return {
        "score": round(score, 1),
        "components": {k: round(v, 3) for k, v in components.items()},
        "rpm_mid_usd": round(rpm_mid, 2),
        "est_monthly_revenue_usd": round(est_revenue),
    }
