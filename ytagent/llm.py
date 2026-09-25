"""Thin wrapper around the Claude API that returns schema-validated JSON."""

from __future__ import annotations

import json

import anthropic

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}
MAX_CONTINUATIONS = 5


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, model: str = "claude-opus-5", effort: str = "high"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        *,
        web_search: bool = False,
        max_tokens: int = 64000,
    ) -> dict:
        """Run one request whose final answer must match `schema`.

        With `web_search`, Claude may search the web first; server-side search
        loops can pause (`pause_turn`), in which case we resend and let the
        server resume.
        """
        messages: list = [{"role": "user", "content": prompt}]
        params = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Server-side refusal fallback: a declined request is retried on
            # Anthropic's recommended fallback model instead of failing.
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if web_search:
            params["tools"] = [WEB_SEARCH_TOOL]

        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(messages=messages, **params) as stream:
                response = stream.get_final_message()
            if response.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": response.content})
        else:
            raise LLMError("web search did not finish after several continuations")

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMError(f"Claude declined the request: {getattr(details, 'explanation', '')}")
        if response.stop_reason == "max_tokens":
            raise LLMError("response hit max_tokens before finishing")

        texts = [b.text for b in response.content if b.type == "text"]
        if not texts:
            raise LLMError("response contained no text")
        # The schema-constrained answer is the final text block; earlier text
        # blocks (if any) are commentary between web searches.
        try:
            return json.loads(texts[-1])
        except json.JSONDecodeError:
            return json.loads("".join(texts))
