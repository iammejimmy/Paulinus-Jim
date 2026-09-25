"""Command-line entry point: `python -m ytagent <command>`."""

from __future__ import annotations

import argparse
import json
import sys

from ytagent import pipeline
from ytagent.config import load_config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ytagent", description=__doc__)
    parser.add_argument("--config", default="config.toml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("research", help="find and score profitable niches; writes output/niche_report.md")
    sub.add_parser("niches", help="list researched niches by score")
    p = sub.add_parser("create", help="plan and render new videos")
    p.add_argument("--niche", help="niche name (default: config channel.niche or top researched)")
    p.add_argument("-n", "--count", type=int, default=1)
    sub.add_parser("list", help="list videos and their status")
    p = sub.add_parser("approve", help="approve rendered videos for upload")
    p.add_argument("ids", type=int, nargs="+")
    sub.add_parser("publish", help="upload approved videos into the next schedule slots")
    sub.add_parser("autopilot", help="create videos_per_run videos, then publish approved ones")
    sub.add_parser("auth", help="connect your YouTube channel (opens a browser once)")
    p = sub.add_parser("preview", help="render a plan.json's first scene + thumbnail without API calls")
    p.add_argument("plan")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "research":
        pipeline.research(cfg)
    elif args.cmd == "niches":
        for n in pipeline._store(cfg).top_niches():
            print(f"{n['score']:5.1f}  ${n['est_monthly_revenue_usd']:>6,}/mo  {n['name']}")
    elif args.cmd == "create":
        pipeline.create(cfg, args.niche, args.count)
    elif args.cmd == "list":
        for v in pipeline._store(cfg).videos():
            extra = f"https://youtu.be/{v['youtube_id']} @ {v['publish_at']}" if v["youtube_id"] else v["video_path"]
            print(f"#{v['id']:<4} {v['status']:<9} {v['title'][:60]:<60}  {extra}")
    elif args.cmd == "approve":
        pipeline.approve(cfg, args.ids)
    elif args.cmd == "publish":
        pipeline.publish(cfg)
    elif args.cmd == "autopilot":
        pipeline.autopilot(cfg)
    elif args.cmd == "auth":
        from ytagent.uploader import get_credentials

        get_credentials(interactive=True)
    elif args.cmd == "preview":
        from pathlib import Path

        from ytagent import stickfig
        from ytagent.media import frame_size

        plan = json.loads(Path(args.plan).read_text())
        size = frame_size(cfg["channel"]["format"])
        print(stickfig.render_scene(plan["scenes"][0], "preview_scene.jpg", size))
        print(stickfig.render_thumbnail(plan["thumbnail_scene"], plan["thumbnail_text"], "preview_thumb.jpg"))


if __name__ == "__main__":
    main(sys.argv[1:])
