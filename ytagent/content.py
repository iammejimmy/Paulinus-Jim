"""Video planning with Claude: topic, title, script, per-scene visuals, and metadata."""

from __future__ import annotations

from ytagent.llm import LLM

POSES = ["standing", "waving", "pointing", "arms_up", "thinking", "walking", "running", "sitting", "slumped"]
EXPRESSIONS = ["happy", "neutral", "sad", "surprised", "angry", "worried"]
PROPS = [
    "house", "tree", "money_bag", "coin", "chart_up", "chart_down", "clock", "laptop",
    "phone", "car", "sign", "box", "lightbulb", "question_mark", "arrow_right", "heart",
    "skull", "book", "desk", "door", "mountain", "sun", "cloud", "crown",
]

_figure = {
    "type": "object",
    "properties": {
        "x": {"type": "integer", "description": "horizontal position, 0 (left) to 100 (right)"},
        "pose": {"type": "string", "enum": POSES},
        "expression": {"type": "string", "enum": EXPRESSIONS},
        "facing": {"type": "string", "enum": ["left", "right"]},
        "label": {"type": "string", "description": "short name under the figure, or empty"},
        "speech": {"type": "string", "description": "speech bubble text (max ~8 words), or empty"},
        "color": {"type": "string", "description": "accent hex color for the figure, e.g. #1f6feb"},
    },
    "required": ["x", "pose", "expression", "facing", "label", "speech", "color"],
    "additionalProperties": False,
}
_prop = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": PROPS},
        "x": {"type": "integer"},
        "label": {"type": "string"},
    },
    "required": ["kind", "x", "label"],
    "additionalProperties": False,
}

SETTINGS = ["plain", "outdoors", "indoors", "night"]

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "characters": {
            "type": "array",
            "description": "recurring characters, so every illustration draws them the same way",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "look": {"type": "string", "description": "hair, clothing, colors, props that identify them"},
                },
                "required": ["name", "look"],
                "additionalProperties": False,
            },
        },
        "angle": {"type": "string", "description": "why this video is different from what exists"},
        "thumbnail_text": {"type": "string"},
        "thumbnail_scene": {
            "type": "object",
            "properties": {
                "image_prompt": {"type": "string"},
                "setting": {"type": "string", "enum": SETTINGS},
                "figures": {"type": "array", "items": _figure},
                "props": {"type": "array", "items": _prop},
            },
            "required": ["image_prompt", "setting", "figures", "props"],
            "additionalProperties": False,
        },
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "caption": {"type": "string", "description": "on-screen headline, max ~6 words, or empty"},
                    "image_prompt": {
                        "type": "string",
                        "description": "detailed illustration description: setting, characters by name with their look, poses, expressions, props, composition; no text in the image",
                    },
                    "setting": {"type": "string", "enum": SETTINGS},
                    "figures": {"type": "array", "items": _figure},
                    "props": {"type": "array", "items": _prop},
                },
                "required": ["narration", "caption", "image_prompt", "setting", "figures", "props"],
                "additionalProperties": False,
            },
        },
        "pinned_comment": {"type": "string"},
    },
    "required": [
        "title", "characters", "angle", "thumbnail_text", "thumbnail_scene", "description",
        "tags", "scenes", "pinned_comment",
    ],
    "additionalProperties": False,
}

PLAN_SYSTEM = """You are the head writer of a successful faceless YouTube channel.
You write videos people finish: a hook in the first 10 seconds that opens a curiosity loop, a clear story
arc with rising stakes, concrete examples and numbers, and a payoff that delivers on the title.
Narration is read aloud by a text-to-speech voice, so write for the ear: short sentences, no
parentheticals, no stage directions, spell out symbols ("percent", "dollars").

Visuals are simple cartoon stick-figure illustrations: characters with big round white heads, simple faces,
thin black stick limbs, and simple hair and clothing, in flat colorful settings. Each scene is one
illustration shown while its narration plays, so design scenes that tell the story visually, often with
humor: named characters, clear poses and expressions, and a few props. Define recurring characters once
in `characters` and describe them identically in every image_prompt so they stay consistent.
Each scene carries two descriptions of the same picture:
- image_prompt: a rich description for an AI illustrator (no text or letters in the image).
- setting/figures/props: a simplified layout for a basic built-in renderer. Keep 1-3 figures and
  0-3 props; spread x positions so nothing overlaps.

Be accurate. Do not invent statistics, quotes, or events; if unsure, say so plainly or leave it out.
The title and thumbnail must be compelling but honest about what the video delivers."""


def plan_video(llm: LLM, niche: dict, channel_cfg: dict, previous_titles: list[str]) -> dict:
    fmt = channel_cfg["format"]
    if fmt == "short":
        length = "a YouTube Short: 35-55 seconds of narration (about 100-140 words), 5-8 scenes"
    else:
        minutes = channel_cfg["target_minutes"]
        words = int(minutes * 150)
        length = f"about {minutes} minutes of narration (about {words} words), one scene per 10-20 seconds"

    ideas = "\n".join(f"- {t}" for t in niche.get("example_video_ideas", []))
    done = "\n".join(f"- {t}" for t in previous_titles[-50:]) or "- (none yet)"
    prompt = f"""Channel niche: {niche['name']}
Niche description: {niche.get('description', '')}
Audience: {niche.get('target_audience', 'general')}

Idea bank from research (use one, combine them, or pick something better you find via web search):
{ideas or '- (none)'}

Already published on this channel (do not repeat these topics):
{done}

Use web search to find a timely or high-interest topic in this niche and verify key facts.
Then plan one video: {length}.
- description: 2 short paragraphs plus 3-6 chapter-free bullet takeaways and 3-5 relevant hashtags at the end.
- tags: 10-15 search tags.
- thumbnail_text: 2-4 punchy words.
- pinned_comment: a question that invites viewers to comment."""
    return llm.json(PLAN_SYSTEM, prompt, PLAN_SCHEMA, web_search=True)
