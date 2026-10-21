"""
app/core/llm_provider.py
──────────────────────────
Centralised LLM provider/factory for CareerCopilot AI.

This is the SINGLE module responsible for creating LLM clients.
No agent or chain should import any LLM SDK directly.
All modules obtain their LLM instance via get_llm() or call_llm().

Supported providers (selected via DEFAULT_LLM_PROVIDER in .env):
  groq      → langchain-groq  (ChatGroq)       ← DEFAULT
  gemini    → langchain-google-genai            (ChatGoogleGenerativeAI)
  anthropic → langchain-anthropic               (ChatAnthropic)
  openai    → langchain-openai                  (ChatOpenAI)

Usage — LangChain style (RAG chain, streaming):
    from app.core.llm_provider import get_llm
    llm = get_llm(streaming=True)
    response = llm.invoke(messages)

Usage — simple text generation (agents):
    from app.core.llm_provider import call_llm
    text, tokens = call_llm(prompt, temperature=0.2, max_tokens=4096)

Adding a new provider:
    1. Add the new API key + model fields to config.py
    2. Add a branch in _build_langchain_llm() and _call_provider_directly()
    3. Update .env.example
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Sentinel returned when no API key is configured ───────────────────────────
_NO_KEY_SENTINEL = "__NO_KEY__"

# ── Granular (input, output) token usage from the most recent call_llm() ──────
# Populated as a side effect of each provider call below; read immediately
# afterwards via get_last_call_usage(). Thread-local so concurrent requests
# handled by different worker threads never see each other's numbers — safe
# as long as callers read it right after their own call_llm(), which is the
# only supported usage pattern.
_usage_local = threading.local()


def _set_last_usage(input_tokens: int | None, output_tokens: int | None) -> None:
    _usage_local.last = {"input_tokens": input_tokens, "output_tokens": output_tokens}


def get_last_call_usage() -> dict[str, int | None]:
    """Granular token usage (input_tokens, output_tokens) from the most recent
    call_llm() invocation on this thread. Call immediately after call_llm()."""
    return getattr(_usage_local, "last", {"input_tokens": None, "output_tokens": None})


# ═════════════════════════════════════════════════════════════════════════════
# Public API — LangChain-compatible LLM (for RAG chain and streaming)
# ═════════════════════════════════════════════════════════════════════════════

def get_llm(
    *,
    streaming: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    provider: str | None = None,
) -> Any | None:
    """
    Return a LangChain-compatible chat model for the configured provider.

    Returns None if no API key is configured (callers should use mock fallback).

    Args:
        streaming:    Enable token streaming (for SSE endpoints).
        temperature:  Sampling temperature (0.0 = deterministic).
        max_tokens:   Maximum output tokens.
        provider:     Override DEFAULT_LLM_PROVIDER for this call.

    Example:
        llm = get_llm(streaming=True)
        if llm is None:
            yield mock_response()
            return
        for chunk in llm.stream(messages):
            yield chunk.content
    """
    active_provider = (provider or settings.DEFAULT_LLM_PROVIDER).lower()
    return _build_langchain_llm(active_provider, streaming, temperature, max_tokens)


def _build_langchain_llm(
    provider: str,
    streaming: bool,
    temperature: float,
    max_tokens: int,
) -> Any | None:
    """Internal factory — returns provider-specific LangChain chat model."""

    # ── Groq ──────────────────────────────────────────────────────────────────
    if provider == "groq":
        if not settings.GROQ_API_KEY:
            logger.warning("groq_api_key_not_configured")
            return None
        try:
            from langchain_groq import ChatGroq  # type: ignore[import]
            llm = ChatGroq(
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
            )
            logger.debug("llm_provider_groq", model=settings.GROQ_MODEL)
            return llm
        except ImportError:
            logger.error("langchain_groq_not_installed", hint="Run: pip install langchain-groq")
            return None
        except Exception as exc:
            logger.error("groq_llm_init_error", error=str(exc))
            return None

    # ── Gemini ────────────────────────────────────────────────────────────────
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            logger.warning("gemini_api_key_not_configured")
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import]
            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                max_output_tokens=max_tokens,
                streaming=streaming,
                convert_system_message_to_human=True,  # Gemini requirement
            )
            logger.debug("llm_provider_gemini", model=settings.GEMINI_MODEL)
            return llm
        except ImportError:
            logger.error("langchain_google_genai_not_installed")
            return None
        except Exception as exc:
            logger.error("gemini_llm_init_error", error=str(exc))
            return None

    # ── Anthropic ─────────────────────────────────────────────────────────────
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("anthropic_api_key_not_configured")
            return None
        try:
            from langchain_anthropic import ChatAnthropic  # type: ignore[import]
            model = settings.DEFAULT_LLM_MODEL or "claude-3-5-sonnet-20241022"
            llm = ChatAnthropic(
                model=model,
                api_key=settings.ANTHROPIC_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
            )
            logger.debug("llm_provider_anthropic", model=model)
            return llm
        except ImportError:
            logger.error("langchain_anthropic_not_installed", hint="Run: pip install langchain-anthropic")
            return None
        except Exception as exc:
            logger.error("anthropic_llm_init_error", error=str(exc))
            return None

    # ── OpenAI ────────────────────────────────────────────────────────────────
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            logger.warning("openai_api_key_not_configured")
            return None
        try:
            from langchain_openai import ChatOpenAI  # type: ignore[import]
            model = settings.DEFAULT_LLM_MODEL or "gpt-4o-mini"
            llm = ChatOpenAI(
                model=model,
                api_key=settings.OPENAI_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
            )
            logger.debug("llm_provider_openai", model=model)
            return llm
        except ImportError:
            logger.error("langchain_openai_not_installed", hint="Run: pip install langchain-openai")
            return None
        except Exception as exc:
            logger.error("openai_llm_init_error", error=str(exc))
            return None

    logger.error("unknown_llm_provider", provider=provider)
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Public API — Simple text generation (for agents that need prompt → text)
# ═════════════════════════════════════════════════════════════════════════════

def call_llm(
    prompt: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    provider: str | None = None,
    json_mode: bool = True,
) -> tuple[str, int]:
    """
    Send a prompt to the configured LLM and return (response_text, tokens_used).

    This is the single call-site for all agents.  No agent imports any SDK.

    Args:
        prompt:      The complete prompt string.
        temperature: Sampling temperature.
        max_tokens:  Maximum output tokens.
        provider:    Override DEFAULT_LLM_PROVIDER for this call.
        json_mode:   Hint to the model to return JSON (best-effort).

    Returns:
        (text, token_count) — token_count may be 0 if provider doesn't report it.

    Raises:
        RuntimeError: If the LLM call fails (after exhausting fallbacks).

    Note: as a side effect, this also records granular (input, output) token
    counts retrievable via `get_last_call_usage()` immediately afterwards —
    used by agent services to log accurate cost/usage analytics without
    changing this function's existing (text, tokens) return signature.
    """
    active_provider = (provider or settings.DEFAULT_LLM_PROVIDER).lower()

    logger.info(
        "llm_call_start",
        provider=active_provider,
        model=settings.active_model,
        prompt_chars=len(prompt),
        json_mode=json_mode,
    )

    text, tokens = _call_provider(active_provider, prompt, temperature, max_tokens, json_mode)

    logger.info(
        "llm_call_complete",
        provider=active_provider,
        response_chars=len(text),
        tokens=tokens,
    )
    return text, tokens


def _call_provider(
    provider: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> tuple[str, int]:
    """Route to the correct provider implementation."""

    if provider == "groq":
        return _call_groq(prompt, temperature, max_tokens, json_mode)
    if provider == "gemini":
        return _call_gemini(prompt, temperature, max_tokens, json_mode)
    if provider == "anthropic":
        return _call_anthropic(prompt, temperature, max_tokens)
    if provider == "openai":
        return _call_openai(prompt, temperature, max_tokens, json_mode)

    logger.error("unknown_provider_falling_back_to_groq", provider=provider)
    return _call_groq(prompt, temperature, max_tokens, json_mode)


# ── Groq implementation ───────────────────────────────────────────────────────

def _call_groq(
    prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> tuple[str, int]:
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. "
            "Add it to .env or switch DEFAULT_LLM_PROVIDER to another provider."
        )
    try:
        from groq import Groq  # type: ignore[import]

        client = Groq(api_key=settings.GROQ_API_KEY)

        kwargs: dict[str, Any] = {
            "model":       settings.GROQ_MODEL,
            "messages":    [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp   = client.chat.completions.create(**kwargs)
        text   = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        if resp.usage:
            _set_last_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        else:
            _set_last_usage(None, None)
        return text, tokens

    except Exception as exc:
        logger.error("groq_call_error", error=str(exc))
        raise RuntimeError(f"Groq API call failed: {exc}") from exc


# ── Gemini implementation ─────────────────────────────────────────────────────

def _call_gemini(
    prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> tuple[str, int]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Add it to .env or switch DEFAULT_LLM_PROVIDER to 'groq'."
        )
    try:
        import google.generativeai as genai  # type: ignore[import]

        genai.configure(api_key=settings.GEMINI_API_KEY)
        gen_config: dict[str, Any] = {
            "temperature":       temperature,
            "top_p":             0.85,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            gen_config["response_mime_type"] = "application/json"

        model  = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            generation_config=gen_config,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )
        resp   = model.generate_content(prompt)
        text   = resp.text or ""
        has_usage = hasattr(resp, "usage_metadata") and resp.usage_metadata
        tokens = resp.usage_metadata.total_token_count if has_usage else 0
        if has_usage:
            _set_last_usage(
                getattr(resp.usage_metadata, "prompt_token_count", None),
                getattr(resp.usage_metadata, "candidates_token_count", None),
            )
        else:
            _set_last_usage(None, None)
        return text, tokens

    except Exception as exc:
        logger.error("gemini_call_error", error=str(exc))
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc


# ── Anthropic implementation ──────────────────────────────────────────────────

def _call_anthropic(
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, int]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. "
            "Add it to .env or switch DEFAULT_LLM_PROVIDER to 'groq'."
        )
    try:
        import anthropic  # type: ignore[import]

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        model  = settings.DEFAULT_LLM_MODEL or "claude-3-5-sonnet-20241022"
        msg    = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text   = msg.content[0].text if msg.content else ""
        tokens = (msg.usage.input_tokens + msg.usage.output_tokens) if msg.usage else 0
        if msg.usage:
            _set_last_usage(msg.usage.input_tokens, msg.usage.output_tokens)
        else:
            _set_last_usage(None, None)
        return text, tokens

    except Exception as exc:
        logger.error("anthropic_call_error", error=str(exc))
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc


# ── OpenAI implementation ─────────────────────────────────────────────────────

def _call_openai(
    prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> tuple[str, int]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Add it to .env or switch DEFAULT_LLM_PROVIDER to 'groq'."
        )
    try:
        from openai import OpenAI  # type: ignore[import]

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model  = settings.DEFAULT_LLM_MODEL or "gpt-4o-mini"

        kwargs: dict[str, Any] = {
            "model":       model,
            "messages":    [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp   = client.chat.completions.create(**kwargs)
        text   = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        if resp.usage:
            _set_last_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        else:
            _set_last_usage(None, None)
        return text, tokens

    except Exception as exc:
        logger.error("openai_call_error", error=str(exc))
        raise RuntimeError(f"OpenAI API call failed: {exc}") from exc


# ═════════════════════════════════════════════════════════════════════════════
# Shared JSON parser utility (used by all agents)
# ═════════════════════════════════════════════════════════════════════════════

def parse_llm_json(raw: str) -> dict | list:
    """
    Robustly parse JSON from LLM output.

    Handles:
      - Clean JSON strings
      - JSON wrapped in ```json ... ``` markdown fences
      - Partial JSON (finds outermost { } or [ ])

    Returns empty dict on unrecoverable parse failure (never raises).
    """
    if not raw:
        return {}

    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find the outermost JSON object or array
        for pattern in (r"\{.*\}", r"\[.*\]"):
            m = re.search(pattern, cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    continue

    logger.warning("llm_json_parse_failed", raw_prefix=raw[:200])
    return {}


# ═════════════════════════════════════════════════════════════════════════════
# Health check (used by /health endpoint)
# ═════════════════════════════════════════════════════════════════════════════

def get_llm_provider_status() -> dict:
    """
    Return a status dict for the /health endpoint.
    Does NOT make any API calls — only checks key presence.
    """
    provider = settings.DEFAULT_LLM_PROVIDER.lower()
    key_present = {
        "groq":      bool(settings.GROQ_API_KEY),
        "gemini":    bool(settings.GEMINI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "openai":    bool(settings.OPENAI_API_KEY),
    }
    return {
        "active_provider": provider,
        "active_model":    settings.active_model,
        "key_configured":  key_present.get(provider, False),
        "providers":       key_present,
    }
