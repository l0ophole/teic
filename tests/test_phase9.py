"""Phase 9 cp1: real OpenRouter send + user-input candidate.

Drives `TeicDaemon._on_tick` the same way `tests/test_phase6.py` does --
real tick loop, real `WorkspaceArbiter`/`render_prompt_if_ignited` wiring --
using a duck-typed fake `ChatClient` injected via the new constructor seam
so no live network call ever happens in CI (matching Phase 8's
no-live-LLM test convention).

Phase 9 cp2: terminal TUI core widget-level tests using Textual's own
`App.run_test()` pilot harness. These drive the *real* `TeicDaemon.run()`
background task (not `run_n_ticks()`), so `tmp_tui_settings` below bumps
`base_tempo_hz` well above the default 1.0 so ticks land fast enough for a
test timeout without faking the clock -- `Heartbeat`'s injectable
`sleep_fn`/`time_source` seam isn't reachable through `TeicApp`, which
always builds a real `Heartbeat` inside `TeicDaemon.start()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from teic.daemon import TeicDaemon
from teic.llm.client import ChatPrompt
from teic.settings import DaemonSettings, Settings
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


@pytest.fixture
def tmp_tui_settings(tmp_path: Path) -> Settings:
    """Same shape as `tmp_settings` (no API key -> no live network call,
    matching the no-live-LLM convention), but with a fast tempo so
    `TeicApp`'s real background `daemon.run()` task produces ticks inside a
    normal test timeout."""
    db_path = tmp_path / "teic_tui_test.db"
    return Settings(daemon=DaemonSettings(db_path=str(db_path), base_tempo_hz=200.0))


@pytest.mark.asyncio
async def test_tui_chat_send_enqueues_user_message(tmp_tui_settings: Settings) -> None:
    """Submitting text in the chat input must both render a user-message
    line in `ChatView` and reach the daemon's real `submit_user_message()`
    queue -- the cp1 seam a queued message is drained from."""
    from textual.widgets import Input

    from teic.interface.terminal.app import TeicApp
    from teic.interface.terminal.chat_view import ChatView

    app = TeicApp(tmp_tui_settings)
    async with app.run_test() as pilot:
        chat_view = app.query_one(ChatView)
        before = len(list(chat_view.children))

        input_widget = app.query_one("#chat-input", Input)
        input_widget.focus()
        input_widget.value = "hello there"
        await pilot.press("enter")
        await pilot.pause()

        assert len(list(chat_view.children)) == before + 1
        assert app.query_one("#chat-input", Input).value == ""

        # The fast test tempo means the queued message is very likely
        # already drained by `_on_tick` into a `user_message`
        # `WorkspaceCandidate` (see cp1's guaranteed-ignition test) by the
        # time we get here -- confirm via the real `workspace_broadcast`
        # row rather than racing the queue's `qsize()`.
        winner_source = None
        for _ in range(25):
            await pilot.pause(0.02)
            cursor = await app.daemon.conn.execute(
                "SELECT winner_source FROM workspace_broadcast wb JOIN tick t "
                "ON wb.tick_id = t.tick_id WHERE t.session_id = ? AND wb.winner_source = 'user_message'",
                (app.daemon.session_id,),
            )
            row = await cursor.fetchone()
            if row is not None:
                winner_source = row[0]
                break
        assert winner_source == "user_message"


@pytest.mark.asyncio
async def test_tui_status_panel_updates_on_tick(tmp_tui_settings: Settings) -> None:
    """The status panel must reflect a real `TickSnapshot` from the
    daemon's background `run()` task without any manual polling call."""
    from teic.interface.terminal.app import TeicApp
    from teic.interface.terminal.status_panel import StatusPanel

    app = TeicApp(tmp_tui_settings)
    async with app.run_test() as pilot:
        for _ in range(20):
            await pilot.pause(0.02)
            panel = app.query_one(StatusPanel)
            if panel._valence_history:
                break
        panel = app.query_one(StatusPanel)
        assert len(panel._valence_history) > 0
        assert len(panel._arousal_history) > 0


@pytest.mark.asyncio
async def test_tui_pause_resume_toggles_daemon_state(tmp_tui_settings: Settings) -> None:
    """`action_toggle_pause` must flip `TeicDaemon.paused` (backed by the
    new `Heartbeat.pause()`/`resume()` pair) both ways."""
    from teic.interface.terminal.app import TeicApp
    from teic.interface.terminal.controls import ControlsBar

    app = TeicApp(tmp_tui_settings)
    async with app.run_test():
        assert app.daemon.paused is False

        app.action_toggle_pause()
        assert app.daemon.paused is True
        assert app.query_one(ControlsBar)._paused is True

        app.action_toggle_pause()
        assert app.daemon.paused is False
        assert app.query_one(ControlsBar)._paused is False
