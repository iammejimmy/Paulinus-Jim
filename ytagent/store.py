"""SQLite state: researched niches and the lifecycle of every video."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Video lifecycle: rendered -> approved -> scheduled   (or failed)
SCHEMA = """
CREATE TABLE IF NOT EXISTS niches (
    name TEXT PRIMARY KEY,
    score REAL NOT NULL,
    data TEXT NOT NULL,
    researched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niche TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    video_path TEXT,
    thumbnail_path TEXT,
    plan TEXT NOT NULL,
    youtube_id TEXT,
    publish_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- niches -------------------------------------------------------------
    def save_niche(self, name: str, score: float, data: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO niches (name, score, data, researched_at) VALUES (?, ?, ?, ?)",
            (name, score, json.dumps(data), _now()),
        )
        self.db.commit()

    def top_niches(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT data FROM niches ORDER BY score DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def get_niche(self, name: str) -> dict | None:
        row = self.db.execute(
            "SELECT data FROM niches WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    # --- videos -------------------------------------------------------------
    def add_video(self, niche: str, plan: dict, video_path: str, thumbnail_path: str, status: str) -> int:
        cur = self.db.execute(
            "INSERT INTO videos (niche, title, status, video_path, thumbnail_path, plan, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (niche, plan["title"], status, video_path, thumbnail_path, json.dumps(plan), _now()),
        )
        self.db.commit()
        return cur.lastrowid

    def update_video(self, video_id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE videos SET {cols} WHERE id = ?", (*fields.values(), video_id))
        self.db.commit()

    def videos(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.db.execute("SELECT * FROM videos WHERE status = ? ORDER BY id", (status,))
        else:
            rows = self.db.execute("SELECT * FROM videos ORDER BY id")
        return [dict(r) for r in rows.fetchall()]

    def titles(self, niche: str) -> list[str]:
        rows = self.db.execute("SELECT title FROM videos WHERE niche = ?", (niche,)).fetchall()
        return [r["title"] for r in rows]

    def scheduled_times(self) -> list[str]:
        rows = self.db.execute(
            "SELECT publish_at FROM videos WHERE publish_at IS NOT NULL"
        ).fetchall()
        return [r["publish_at"] for r in rows]
