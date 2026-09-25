"""Uploading to YouTube (OAuth) and computing publish slots."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path("youtube_token.json")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def next_slots(
    count: int,
    days: list[str],
    times: list[str],
    tz: str,
    taken: list[str],
    now: datetime | None = None,
    min_lead: timedelta = timedelta(hours=2),
) -> list[datetime]:
    """Next `count` free posting slots (UTC) on the configured weekly schedule.

    `taken` holds ISO timestamps already scheduled; slots on or before the latest
    taken slot are skipped so new videos queue up behind existing ones.
    """
    zone = ZoneInfo(tz)
    now = now or datetime.now(timezone.utc)
    taken_dt = [datetime.fromisoformat(t) for t in taken]
    start = max([now + min_lead, *[t + timedelta(minutes=1) for t in taken_dt]])
    wanted_days = {DAYS.index(d.lower()[:3]) for d in days} or set(range(7))
    clock = sorted(tuple(int(p) for p in t.split(":")) for t in times) or [(15, 0)]

    slots: list[datetime] = []
    day = start.astimezone(zone).date()
    for _ in range(400):
        if day.weekday() in wanted_days:
            for hh, mm in clock:
                local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
                if local.astimezone(timezone.utc) >= start:
                    slots.append(local.astimezone(timezone.utc))
                    if len(slots) == count:
                        return slots
        day += timedelta(days=1)
    return slots


def get_credentials(client_secrets: str | None = None, interactive: bool = False):
    """Load saved OAuth credentials (file or YOUTUBE_TOKEN_JSON env), refreshing as needed.

    With `interactive`, runs the browser consent flow and saves youtube_token.json.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if os.environ.get("YOUTUBE_TOKEN_JSON"):
        creds = Credentials.from_authorized_user_info(json.loads(os.environ["YOUTUBE_TOKEN_JSON"]), SCOPES)
    elif TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if creds and creds.valid:
        return creds
    if not interactive:
        raise RuntimeError("No valid YouTube credentials; run `python -m ytagent auth` first.")

    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = client_secrets or os.environ.get("YOUTUBE_CLIENT_SECRETS", "client_secret.json")
    flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Saved credentials to {TOKEN_PATH}")
    return creds


def upload(
    video_path: str,
    thumbnail_path: str | None,
    plan: dict,
    publish_cfg: dict,
    publish_at: datetime | None,
) -> str:
    """Upload a video. With `publish_at`, it stays private until then and YouTube
    publishes it automatically. Returns the YouTube video id."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)

    status = {
        "privacyStatus": "private" if publish_at else publish_cfg["privacy"],
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": bool(publish_cfg.get("disclose_synthetic_media", True)),
    }
    if publish_at:
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": plan["title"][:100],
            "description": plan["description"][:5000],
            "tags": plan.get("tags", [])[:30],
            "categoryId": publish_cfg["category_id"],
        },
        "status": status,
    }
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"  uploading {int(progress.progress() * 100)}%")
    video_id = response["id"]

    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
        except HttpError as exc:  # custom thumbnails need a phone-verified channel
            print(f"  ! thumbnail not set ({exc.status_code}); verify your channel at youtube.com/verify")

    return video_id
