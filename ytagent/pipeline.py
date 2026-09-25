"""High-level steps: research -> create -> review -> publish, and the autopilot loop."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ytagent.store import Store


def _store(cfg: dict) -> Store:
    return Store(Path(cfg["paths"]["data_dir"]) / "state.db")


def _llm(cfg: dict):
    from ytagent.llm import LLM

    return LLM(cfg["llm"]["model"], cfg["llm"]["effort"])


def research(cfg: dict) -> list[dict]:
    from ytagent import research as r

    store = _store(cfg)
    rc = cfg["research"]
    print(f"Asking Claude for {rc['niche_count']} niche ideas (with web search)...")
    niches = r.brainstorm_niches(_llm(cfg), cfg)
    yt = r.YouTubeResearcher(region=rc["region"], lookback_days=rc["lookback_days"])

    scored = []
    for n in niches:
        print(f"Measuring on YouTube: {n['name']}")
        try:
            result = r.analyze_niche(n, yt, rc["keywords_per_niche"])
        except Exception as exc:  # quota errors etc. shouldn't lose the other niches
            print(f"  ! skipped ({exc})")
            continue
        store.save_niche(result["name"], result["score"], result)
        scored.append(result)

    scored.sort(key=lambda n: n["score"], reverse=True)
    report = Path(cfg["paths"]["output_dir"]) / "niche_report.md"
    report.write_text(r.format_report(scored))
    print(f"\nReport written to {report}")
    return scored


def pick_niche(cfg: dict, store: Store, name: str | None = None) -> dict:
    name = name or cfg["channel"]["niche"]
    if name:
        # A niche you typed in yourself works too, even if it was never researched.
        return store.get_niche(name) or {"name": name, "description": name, "example_video_ideas": []}
    top = store.top_niches(1)
    if not top:
        raise RuntimeError("No niche chosen. Run `research` first or set channel.niche in config.toml.")
    return top[0]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def create(cfg: dict, niche_name: str | None = None, count: int = 1) -> list[int]:
    from ytagent import content, media

    store = _store(cfg)
    niche = pick_niche(cfg, store, niche_name)
    llm = _llm(cfg)
    ids = []
    for _ in range(count):
        print(f"Planning a video for niche: {niche['name']}")
        plan = content.plan_video(llm, niche, cfg["channel"], store.titles(niche["name"]))
        print(f"  title: {plan['title']}  ({len(plan['scenes'])} scenes)")
        workdir = Path(cfg["paths"]["output_dir"]) / f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(plan['title'])}"
        video, thumb = media.render_video(plan, workdir, cfg["channel"])
        status = "rendered" if cfg["publish"]["review_required"] else "approved"
        vid = store.add_video(niche["name"], plan, str(video), str(thumb), status)
        print(f"  saved video #{vid}: {video} [{status}]")
        ids.append(vid)
    return ids


def approve(cfg: dict, video_ids: list[int]) -> None:
    store = _store(cfg)
    for vid in video_ids:
        store.update_video(vid, status="approved")
        print(f"Approved #{vid}")


def publish(cfg: dict) -> list[str]:
    from ytagent import uploader

    store = _store(cfg)
    pc = cfg["publish"]
    queue = store.videos("approved")
    if not queue:
        print("Nothing approved to publish.")
        return []
    slots = uploader.next_slots(len(queue), pc["days"], pc["times"], pc["timezone"], store.scheduled_times())
    uploaded = []
    for video, slot in zip(queue, slots):
        print(f"Uploading #{video['id']} '{video['title']}' scheduled for {slot:%Y-%m-%d %H:%M} UTC")
        try:
            yt_id = uploader.upload(video["video_path"], video["thumbnail_path"], json.loads(video["plan"]), pc, slot)
        except Exception as exc:
            store.update_video(video["id"], status="failed", error=str(exc)[:1000])
            print(f"  ! upload failed: {exc}")
            continue
        store.update_video(video["id"], status="scheduled", youtube_id=yt_id, publish_at=slot.isoformat())
        print(f"  https://youtu.be/{yt_id}")
        uploaded.append(yt_id)
    return uploaded


def autopilot(cfg: dict) -> None:
    """One unattended run: create the configured number of videos, then publish
    whatever is approved. With review_required, new videos wait for approval."""
    create(cfg, count=cfg["publish"]["videos_per_run"])
    publish(cfg)
