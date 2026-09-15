"""Phase 10 cp1: `build_narrative_tail()` against real persisted
`workspace_broadcast`/`llm_call_log` rows -- driven through `TeicDaemon`
the same way `tests/test_phase9.py` exercises the real ignited-send path,
not hand-authored row fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from teic.daemon import TeicDaemon
from teic.llm.client import ChatPrompt
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat
from teic.workspace.narrative_constructor import build_narrative_tail


class FakeChatClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[ChatPrompt] = []

    async def stream(self, prompt: ChatPrompt) -> AsyncIterator[str]:
        self.calls.append(prompt)
        response = self._responses.pop(0)
        for word in response.split(" "):
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
async def test_empty_session_returns_empty_list(tmp_settings: Settings) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    assert await build_narrative_tail(daemon.conn, daemon.session_id) == []
    await daemon.stop()


@pytest.mark.asyncio
async def test_user_turn_and_reply_are_narrated_in_order(tmp_settings: Settings) -> None:
    fake_client = FakeChatClient(responses=["hello yourself"])
    daemon = TeicDaemon(tmp_settings, llm_client=fake_client)
    await daemon.start()
    await daemon.submit_user_message("hello there")

    heartbeat = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(1)

    tail = await build_narrative_tail(daemon.conn, daemon.session_id)
    assert tail == ["you: hello there", "I: hello yourself "]

    await daemon.stop()


@pytest.mark.asyncio
async def test_two_turns_are_ordered_tick_ascending(tmp_settings: Settings) -> None:
    fake_client = FakeChatClient(responses=["first reply", "second reply"])
    daemon = TeicDaemon(tmp_settings, llm_client=fake_client)
    await daemon.start()

    heartbeat = _fake_heartbeat(daemon, tmp_settings)
    await daemon.submit_user_message("first message")
    await heartbeat.run_n_ticks(1)
    await daemon.submit_user_message("second message")
    await heartbeat.run_n_ticks(1)

    tail = await build_narrative_tail(daemon.conn, daemon.session_id)
    assert tail == [
        "you: first message",
        "I: first reply ",
        "you: second message",
        "I: second reply ",
    ]

    await daemon.stop()


@pytest.mark.asyncio
async def test_max_ticks_truncates_to_most_recent(tmp_settings: Settings) -> None:
    fake_client = FakeChatClient(responses=["first reply", "second reply"])
    daemon = TeicDaemon(tmp_settings, llm_client=fake_client)
    await daemon.start()

    heartbeat = _fake_heartbeat(daemon, tmp_settings)
    await daemon.submit_user_message("first message")
    await heartbeat.run_n_ticks(1)
    await daemon.submit_user_message("second message")
    await heartbeat.run_n_ticks(1)

    tail = await build_narrative_tail(daemon.conn, daemon.session_id, max_ticks=1)
    assert tail == ["you: second message", "I: second reply "]

    await daemon.stop()
