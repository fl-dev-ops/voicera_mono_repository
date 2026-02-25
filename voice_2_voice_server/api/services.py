"""Service factory for LiveKit Agents SDK.

STT  → Deepgram (default: nova-2)
TTS  → Sarvam   (default: bulbul:v2)
LLM  → OpenAI | Gemini

All providers are commercial LiveKit plugins — no custom node overrides needed.

Returns:
    plugin  — LiveKit SDK plugin object passed to AgentSession(stt=, tts=, llm=)
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from livekit.plugins import openai as lk_openai
from livekit.plugins import deepgram as lk_deepgram
from livekit.plugins import google as lk_google

try:
    from livekit.plugins import sarvam as lk_sarvam

    SARVAM_AVAILABLE = True
except ImportError:
    SARVAM_AVAILABLE = False
    logger.warning("livekit-plugins-sarvam not installed — Sarvam TTS unavailable")

from config import get_llm_model
from config.stt_mappings import STT_LANGUAGE_MAP
from config.tts_mappings import TTS_LANGUAGE_MAP


class ServiceCreationError(Exception):
    """Raised when a service cannot be created."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# LLM  (OpenAI | Gemini)
# ─────────────────────────────────────────────────────────────────────────────


def create_livekit_llm(llm_config: dict) -> Any:
    """Return a LiveKit LLM plugin.

    Supported providers: openai, gemini/google
    """
    provider = (llm_config.get("name") or llm_config.get("provider") or "").lower()
    args = llm_config.get("args", {})
    model = args.get("model") or llm_config.get("model")

    provider_map = {
        "openai": "openai",
        "gemini": "gemini",
        "google": "gemini",
    }
    provider_key = provider_map.get(provider, provider)

    if provider_key == "openai":
        resolved_model = get_llm_model("OpenAI", model or "")
        logger.info(f"LLM: OpenAI model={resolved_model}")
        return lk_openai.LLM(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=resolved_model,
        )

    if provider_key == "gemini":
        resolved_model = get_llm_model("Gemini", model or "")
        logger.info(f"LLM: Gemini model={resolved_model}")
        return lk_google.LLM(
            api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            model=resolved_model,
            vertexai=False,
        )

    raise ServiceCreationError(
        f"Unknown LLM provider: {provider!r}. Supported: openai, gemini"
    )


# ─────────────────────────────────────────────────────────────────────────────
# STT  (Deepgram)
# ─────────────────────────────────────────────────────────────────────────────


def create_livekit_stt(stt_config: dict) -> Any:
    """Return a LiveKit STT plugin.

    Supported providers: deepgram (default)
    """
    provider = (stt_config.get("name") or "deepgram").lower()
    language = stt_config.get("language")
    args = stt_config.get("args", {})

    if provider == "deepgram":
        model: str = stt_config.get("model") or args.get("model") or "nova-2"
        lang_key: str = language or "en-US"
        lang_code: str = STT_LANGUAGE_MAP["Deepgram"].get(lang_key, lang_key)
        logger.info(f"STT: Deepgram model={model} language={lang_code}")
        return lk_deepgram.STT(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            model=model,
            language=lang_code,
        )

    raise ServiceCreationError(
        f"Unknown STT provider: {provider!r}. Supported: deepgram"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TTS  (Sarvam)
# ─────────────────────────────────────────────────────────────────────────────


def create_livekit_tts(tts_config: dict) -> Any:
    """Return a LiveKit TTS plugin.

    Supported providers: sarvam (default)
    """
    provider = (tts_config.get("name") or "sarvam").lower()
    language = tts_config.get("language")
    args = tts_config.get("args", {})

    if provider == "sarvam":
        if not SARVAM_AVAILABLE:
            raise ServiceCreationError(
                "Sarvam TTS requested but livekit-plugins-sarvam is not installed. "
                "Run: pip install livekit-plugins-sarvam"
            )
        tts_model: str = tts_config.get("model") or args.get("model") or "bulbul:v2"
        voice: str = tts_config.get("speaker") or args.get("speaker") or "anushka"
        lang_key: str = str(language) if language else "hi-IN"
        sarvam_lang_map: dict = TTS_LANGUAGE_MAP.get("Sarvam", {})
        lang_code: str = sarvam_lang_map.get(lang_key, lang_key)
        logger.info(
            f"TTS: Sarvam model={tts_model} speaker={voice} target_language_code={lang_code}"
        )
        import livekit.plugins.sarvam as _sarvam_mod  # noqa: PLC0415

        return _sarvam_mod.TTS(
            api_key=os.getenv("SARVAM_API_KEY"),
            model=tts_model,
            speaker=voice,
            target_language_code=lang_code,
        )

    raise ServiceCreationError(f"Unknown TTS provider: {provider!r}. Supported: sarvam")
