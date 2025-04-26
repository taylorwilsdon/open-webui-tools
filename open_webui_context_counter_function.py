"""
title: Chat Context Window Tracking for Open-WebUI
author: Taylor Wilsdon
author_url: https://github.com/open-webui
funding_url: https://github.com/open-webui
version: 0.1
license: MIT
requirements: tiktoken
description: Performant, lightweight context window tracker for Open-WebUI built with minimal latency in mind
"""
from __future__ import annotations

import functools
import hashlib
import logging
from typing import Any, Awaitable, Callable, Optional

import tiktoken
from open_webui.models.models import Models
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
#  Globals & helpers                                                          #
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("StandardContextCounter")

DEFAULT_FALLBACK_CONTEXT_SIZE = 4096
HARD_CODED_CONTEXTS = {
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4-vision-preview": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "claude-2.1": 200000,
    "claude-2.0": 100000,
    "claude-instant-1.2": 100000,
    "gemini-1.5-pro-latest": 1048576,
    "gemini-1.5-flash-latest": 1048576,
    "gemini-pro": 30720,
    "gemini-pro-vision": 12288,
    "llama3-70b-8192": 8192,
    "llama3-8b-8192": 8192,
    "llama2-70b-4096": 4096,
    "mistral-large-latest": 32768,
    "mistral-medium-latest": 32768,
    "mistral-small-latest": 32768,
    "mistral-7b-instruct-v0.2": 32768,
    "mixtral-8x7b-instruct-v0.1": 32768,
}

_K, _M = 1_000, 1_000_000
INDICATORS = ["⬡", "⬢"]

def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()


def _format_number(num: int) -> str:
    if num >= _M:
        return f"{num / _M:.1f}M"
    if num >= _K:
        return f"{num / _K:.1f}K"
    return str(num)


def _build_bar(filled: int, total: int) -> str:
    return "[" + INDICATORS[1] * filled + INDICATORS[0] * (total - filled) + "]"


@functools.lru_cache(maxsize=256)
def _get_context_size_cached(
    raw_name: str,
    normalised: str,
    ctx_items: frozenset[tuple[str, int]],
) -> int:
    """
    Pure function suitable for LRU-caching.  Re-created when custom-model
    overrides change (cache cleared by Filter._refresh_custom_models).
    """
    ctx_map = dict(ctx_items)

    if not raw_name:
        return DEFAULT_FALLBACK_CONTEXT_SIZE

    lname = raw_name.lower()
    if "sonnet" in lname:
        return 128_000

    try:
        m = Models.get_model_by_id(raw_name)
        data = m.model_dump() if hasattr(m, "model_dump") else m.__dict__
        num_ctx = data.get("params", {}).get("num_ctx")
        if isinstance(num_ctx, int) and num_ctx > 0:
            return num_ctx
    except Exception:
        pass

    return (
        ctx_map.get(raw_name)
        or ctx_map.get(normalised)
        or DEFAULT_FALLBACK_CONTEXT_SIZE
    )


# --------------------------------------------------------------------------- #
#  Filter                                                                     #
# --------------------------------------------------------------------------- #


class Filter:
    """High-throughput context-window tracker optimised for per-request usage."""

    # -------------------------- configuration models ----------------------- #

    class Valves(BaseModel):
        custom_models_plaintext: str = Field(default="")
        log_level: str = Field(default="INFO")
        show_status: bool = Field(default=True)
        show_progress_bar: bool = Field(default=True)
        bar_length: int = Field(default=5)
        warn_at_percentage: float = Field(default=75.0)
        critical_at_percentage: float = Field(default=90.0)

    class UserValves(BaseModel):
        enabled: bool = Field(default=True)

    # ------------------------------- init ---------------------------------- #

    def __init__(self) -> None:
        self.valves = self.Valves()
        logger.setLevel(getattr(logging, self.valves.log_level.upper(), logging.INFO))

        self._encoder: Optional[tiktoken.Encoding] = None
        self._custom_models_hash: str = ""
        self._model_contexts: dict[str, int] = HARD_CODED_CONTEXTS.copy()
        self._refresh_custom_models()  # one-off at start-up

        logger.info("Context counter initialised")

    # ------------------------- heavyweight resources ----------------------- #

    def _encoder_fast(self) -> tiktoken.Encoding:
        """Lazy-load and cache tiktoken encoder."""
        if self._encoder is None:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder

    # ------------------------- custom model support ----------------------- #

    def _refresh_custom_models(self) -> None:
        """
        Parse the plaintext overrides only when the text actually changes.
        """
        txt = self.valves.custom_models_plaintext
        digest = _sha1(txt)
        if digest == self._custom_models_hash:
            return  # no change

        for line in txt.splitlines():
            name, *rest = line.split()
            if rest and rest[0].isdigit():
                size = int(rest[0])
                if size > 0:
                    self._model_contexts[name] = size

        self._custom_models_hash = digest
        _get_context_size_cached.cache_clear()

    # ---------------------------- internals -------------------------------- #

    @staticmethod
    def _normalise_id(model_id: str) -> str:
        name = model_id.lower().strip()
        for p in (
            "openai/",
            "anthropic/",
            "google/",
            "meta-llama/",
            "mistralai/",
            "ollama/",
        ):
            if name.startswith(p):
                return name[len(p) :]
        return name

    def _get_context_size(self, model_name: str) -> int:
        return _get_context_size_cached(
            model_name,
            self._normalise_id(model_name),
            frozenset(self._model_contexts.items()),
        )

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        try:
            return len(self._encoder_fast().encode_ordinary(text))
        except Exception as e:  # pragma: no cover
            logger.error("Tokenisation error: %s", e)
            return len(text) // 4

    # --------------------------------------------------------------------- #
    #  Filter API                                                            #
    # --------------------------------------------------------------------- #

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:  # noqa: N802
        return body

    def stream(self, event: dict) -> dict:  # noqa: N802
        return event

    async def outlet(  # noqa: N802, C901 (complexity acceptable)
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]],
        __user__: Optional[dict] = None,
        __model__: Optional[dict] = None,
    ) -> dict:  # pragma: no cover (I/O heavy, mock in tests)
        # user-level valve
        if __user__ and isinstance(__user__.get("valves"), dict):
            if not __user__["valves"].get("enabled", True):
                return body

        # refresh custom model cache if needed
        self._refresh_custom_models()

        try:
            model_id = (__model__ or {}).get("id", "")
            msgs = body.get("messages") or []
            if not msgs:
                return body

            # token counting (single encoder pass for totals)
            all_texts, assistant_last = [], ""
            for m in msgs:
                text = m.get("content") or ""
                if isinstance(text, list):  # vision messages
                    text = "\n".join(
                        item.get("text", "") for item in text if item.get("type") == "text"
                    )
                all_texts.append(text)
                if m.get("role") == "assistant":
                    assistant_last = text

            enc = self._encoder_fast()
            total = len(enc.encode_ordinary("\n".join(all_texts)))
            output = len(enc.encode_ordinary(assistant_last)) if assistant_last else 0
            input_tokens = total - output

            limit = self._get_context_size(model_id)
            pct = 100.0 * total / limit if limit else 0.0

            prefix = (
                "CRIT:" if pct >= self.valves.critical_at_percentage
                else "WARN:" if pct >= self.valves.warn_at_percentage
                else ""
            )

            bar = (
                _build_bar(int(self.valves.bar_length * pct / 100), self.valves.bar_length)
                if self.valves.show_progress_bar
                else ""
            )

            status = " | ".join(
                p for p in (
                    prefix,
                    f"Tokens: {_format_number(total)}/{_format_number(limit)} ({pct:.1f}%)",
                    bar,
                    f"{_format_number(input_tokens)}/{_format_number(output)}",
                ) if p
            )

            logger.debug(
                "Context %s/%s tokens (%.1f%%) | model=%s",
                total, limit, pct, model_id,
            )

            if self.valves.show_status:
                await __event_emitter__(
                    {"type": "status", "data": {"description": status, "done": True}}
                )

        except Exception:  # noqa: BLE001
            logger.exception("Context counter failed")
            if self.valves.show_status:
                try:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {"description": "Error calculating context", "done": True},
                        }
                    )
                except Exception:
                    pass

        return body