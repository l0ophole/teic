"""Phase 9 cp1: real OpenRouter send + user-input candidate.

Drives `TeicDaemon._on_tick` the same way `tests/test_phase6.py` does --
real tick loop, real `WorkspaceArbiter`/`render_prompt_if_ignited` wiring --
using a duck-typed fake `ChatClient` injected via the new constructor seam
so no live network call ever happens in CI (matching Phase 8's
no-live-LLM test convention).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from teic.daemon import TeicDaemon
from teic.llm.client import ChatPrompt
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat


class FakeChatClient:
    """Duck-typed `OpenRouterClient` stand-in: only `.stream()` is ever
    called by `_handle_ignited_prompt`, so that's all this needs to
    implement."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[ChatPrompt] = []

    async def stream(self, prompt: ChatPrompt) -> AsyncIterator[str]:
        self.calls.append(prompt)
        for word in self._response.split(" "):
            yield word + " "


def _fake_heartbeat(daemon: TeicDaemon, tmp_settings: Settings) -> Heartbeat:
    fake_clock = {"t": 0.0}

    async def fake_sleep(_seconds: float) -> None:
        fake_clock["t"] += 1.0 / daemon._current_tempo_hz

    return Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )


@pytest.mark.asyncio
async def test_user_message_candidate_wins_arbitration_and_ignites(tmp_settings: Settings) -> None:
    """A queued user message must become a real `WorkspaceCandidate` with
    fixed max salience factors -- guaranteed to win and ignite regardless
    of affect/mood state, since `ignition_threshold()`'s max is exactly
    1.0 and the condition is `>=`."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    await daemon.submit_user_message("hello there")

    heartbeat = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(1)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT wb.winner_source, wb.ignited FROM workspace_broadcast wb "
        "JOIN tick t ON wb.tick_id = t.tick_id WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    winner_source, ignited = await cursor.fetchone()
    assert winner_source == "user_message"
    assert ignited == 1

    await daemon.stop()


@pytest.mark.asyncio
async def test_ignited_response_is_streamed_persisted_and_charged(tmp_settings: Settings) -> None:
    """With a fake client injected, an ignited winner must actually call
    `.stream()`, persist the accumulated response into `llm_call_log`, and
    charge the real post-response cost (nonzero completion tokens) against
    the viability ledger -- not the old prompt-tokens-only estimate."""
    fake_client = FakeChatClient(response="a real streamed response with several tokens")
    daemon = TeicDaemon(tmp_settings, llm_client=fake_client)
    await daemon.start()
    assert daemon._pricing is not None
    daemon._pricing._prices[tmp_settings.llm.primary_model] = {"prompt": 0.01, "completion": 0.01}
    await daemon.submit_user_message("hello there")

    heartbeat = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(1)

    assert len(fake_client.calls) == 1

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT response, completion_tokens, estimated_cost_usd, status FROM llm_call_log"
    )
    row = await cursor.fetchone()
    assert row is not None
    response, completion_tokens, estimated_cost_usd, status = row
    assert status == "ok"
    assert response is not None and len(response) > 0
    assert completion_tokens is not None and completion_tokens > 0
    assert estimated_cost_usd is not None and estimated_cost_usd > 0.0

    assert daemon._viability_budget is not None
    assert daemon._viability_budget.last_spend_usd == estimated_cost_usd

    await daemon.stop()
