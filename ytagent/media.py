"""Turns a video plan into files: voiceover, scene images, the final MP4, and a thumbnail.

Requires ffmpeg/ffprobe on PATH.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

from ytagent import stickfig

FPS = 30

DEFAULT_STYLE = (
    "Simple 2D cartoon illustration in the style of stick-figure explainer videos. Characters have large "
    "round white heads, simple dot or line eyes and curved-line mouths, thin black stick-figure arms and "
    "legs, and simple cartoon hair and clothing. Clean bold black outlines, flat bright colors, simple "
    "uncluttered backgrounds, gentle humor. No text, letters, captions, or watermarks in the image."
)


def frame_size(fmt: str) -> tuple[int, int]:
    return (1080, 1920) if fmt == "short" else (1920, 1080)


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{proc.stderr[-2000:]}")
    return proc.stdout


def check_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} not found on PATH; install ffmpeg (https://ffmpeg.org/download.html)")


def audio_duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


# --- voice -------------------------------------------------------------------

def synthesize_voice(text: str, path: Path, voice: str) -> Path:
    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice).save(str(path))

    asyncio.run(_go())
    return path


# --- images ------------------------------------------------------------------

def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS)


def generate_ai_image(prompt: str, path: Path, size: tuple[int, int], model: str) -> Path:
    """Generate an illustration with Google's Gemini image model (needs GEMINI_API_KEY)."""
    key = os.environ["GEMINI_API_KEY"]
    aspect = "9:16" if size[1] > size[0] else "16:9"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline:
                img = Image.open(io.BytesIO(base64.b64decode(inline["data"])))
                _fit(img, size).save(path, quality=92)
                return path
    raise RuntimeError(f"image model returned no image: {json.dumps(data)[:500]}")


def scene_image(scene: dict, plan: dict, path: Path, size: tuple[int, int], channel_cfg: dict) -> Path:
    """AI illustration when configured, else the built-in stick-figure renderer."""
    if channel_cfg["visual_style"] == "ai" and os.environ.get("GEMINI_API_KEY"):
        cast = "; ".join(f"{c['name']}: {c['look']}" for c in plan.get("characters", []))
        prompt = f"{channel_cfg['image_style'] or DEFAULT_STYLE}\n\nRecurring characters: {cast}\n\nScene: {scene['image_prompt']}"
        try:
            generate_ai_image(prompt, path, size, channel_cfg["image_model"])
            if scene.get("caption"):
                stickfig.add_caption(path, scene["caption"])
            return path
        except Exception as exc:  # fall back rather than lose the whole video
            print(f"  ! AI image failed ({exc}); using built-in renderer for this scene")
    return stickfig.render_scene(scene, path, size)


# --- video -------------------------------------------------------------------

def _scene_clip(image: Path, audio: Path, out: Path, size: tuple[int, int], zoom_in: bool) -> Path:
    """One still image with a slow Ken Burns zoom, timed to its narration."""
    W, H = size
    dur = audio_duration(audio) + 0.35  # small breath between scenes
    frames = int(dur * FPS)
    step = 0.10 / max(frames, 1)
    z = f"1+{step}*on" if zoom_in else f"1.10-{step}*on"
    vf = (
        f"scale={W * 2}:{H * 2},"
        f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        "format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", str(image),
        "-i", str(audio),
        "-vf", vf, "-af", "apad",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(out),
    ])
    return out


def render_video(plan: dict, workdir: Path, channel_cfg: dict) -> tuple[Path, Path]:
    """Build the full video + thumbnail. Returns (video_path, thumbnail_path)."""
    check_ffmpeg()
    workdir.mkdir(parents=True, exist_ok=True)
    size = frame_size(channel_cfg["format"])
    (workdir / "plan.json").write_text(json.dumps(plan, indent=2))

    clips = []
    for i, scene in enumerate(plan["scenes"]):
        print(f"  scene {i + 1}/{len(plan['scenes'])}")
        audio = synthesize_voice(scene["narration"], workdir / f"scene{i:03d}.mp3", channel_cfg["voice"])
        image = scene_image(scene, plan, workdir / f"scene{i:03d}.jpg", size, channel_cfg)
        clips.append(_scene_clip(image, audio, workdir / f"scene{i:03d}.mp4", size, zoom_in=i % 2 == 0))

    listing = workdir / "clips.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = workdir / "joined.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(listing), "-c", "copy", str(joined)])

    final = workdir / "video.mp4"
    music = channel_cfg.get("music_path")
    if music and Path(music).exists():
        vol = channel_cfg.get("music_volume", 0.08)
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(joined),
            "-stream_loop", "-1", "-i", music,
            "-filter_complex", f"[1:a]volume={vol}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(final),
        ])
    else:
        joined.replace(final)

    thumb = workdir / "thumbnail.jpg"
    tscene = plan["thumbnail_scene"]
    thumb_size = (1280, 720)
    if channel_cfg["visual_style"] == "ai" and os.environ.get("GEMINI_API_KEY"):
        scene_image({**tscene, "caption": ""}, plan, thumb, thumb_size, channel_cfg)
        stickfig.add_headline(thumb, plan["thumbnail_text"])
    else:
        stickfig.render_thumbnail(tscene, plan["thumbnail_text"], thumb, thumb_size)
    return final, thumb
