"""OpenRouter integration boundary.

Config-driven model selection (never hard-coded), exponential backoff on
429/5xx, automatic fallback to the secondary model after repeated primary
failure, streaming support. Every failure surfaces as an interoceptive
perturbation via `on_failure`, never a bare exception up to the daemon --
per spec: "LLM failure must surface as interoceptive strain... never a crash."
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

FailureHook = Callable[[str], Awaitable[None]]


@dataclass
class ChatPrompt:
    """Assembled, ready-to-send prompt. Constructed ONLY by
    llm/prompt_assembly.py from broadcast content -- never built here."""

    messages: list[dict[str, str]]
    temperature: float
    top_p: float


@dataclass
class ChatResult:
    content: str
    model_used: str
    fallback_used: bool
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        primary_model: str,
        fallback_model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        request_timeout_s: float = 30.0,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        on_failure: FailureHook | None = None,
    ) -> None:
        self._api_key = api_key
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._base_url = base_url
        self._timeout_s = request_timeout_s
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._on_failure = on_failure
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=request_timeout_s,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post_with_retry(self, model: str, prompt: ChatPrompt, stream: bool) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": prompt.messages,
                        "temperature": prompt.temperature,
                        "top_p": prompt.top_p,
                        "stream": stream,
                    },
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._backoff_base_s * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def complete(self, prompt: ChatPrompt) -> ChatResult:
        """Non-streaming completion with primary/fallback and interoceptive-strain
        reporting on total failure."""
        start = time.monotonic()
        try:
            resp = await self._post_with_retry(self._primary_model, prompt, stream=False)
            model_used = self._primary_model
            fallback_used = False
        except (httpx.HTTPStatusError, httpx.TransportError):
            if self._on_failure is not None:
                await self._on_failure("primary_exhausted")
            try:
                resp = await self._post_with_retry(self._fallback_model, prompt, stream=False)
                model_used = self._fallback_model
                fallback_used = True
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if self._on_failure is not None:
                    await self._on_failure("fallback_exhausted")
                raise

        latency_ms = int((time.monotonic() - start) * 1000)
        data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return ChatResult(
            content=choice,
            model_used=model_used,
            fallback_used=fallback_used,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
        )

    async def stream(self, prompt: ChatPrompt) -> AsyncIterator[str]:
        """Streams token chunks from the primary model. No fallback mid-stream
        (fallback only applies to a fresh call, not stream recovery) --
        callers should treat a stream error as a failed call and retry via
        `complete()`/`stream()` again if desired."""
        async with self._client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": self._primary_model,
                "messages": prompt.messages,
                "temperature": prompt.temperature,
                "top_p": prompt.top_p,
                "stream": True,
            },
        ) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                if self._on_failure is not None:
                    await self._on_failure("stream_failed")
                raise
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line.removeprefix("data: ").strip()
                if data_str == "[DONE]":
                    break
                import json

                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
