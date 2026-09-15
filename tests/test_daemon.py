"""Phase 3 daemon wiring: `prediction_error` becomes a real, learned signal.

Drives `TeicDaemon._on_tick` through the same injected `time_source`/
`sleep_fn` DI pattern used by `tests/test_gates/test_phase1.py` and
`test_phase2.py`. Most ticks use `dt_real` equal to that tick's own nominal
`1 / tempo_hz`, but tick 1 is deliberately jittered to 3x nominal.

This is a stronger check than "stays near 0.0 throughout" would be: under
Phase 0-2's flat `0.0` placeholder, prediction_error is always 0.0 no
matter what dt_real does, so a test that only asserted near-zero values
could not tell a real ForwardModel-driven signal apart from that
placeholder. Instead this test asserts the jittered tick produces a large,
real error (proving the signal is genuinely computed from ForwardModel/
ProtentionBuffer, not hardcoded), and that later ticks -- back on nominal
dt_real -- decay close to 0.0 again (proving the EWMA forward model
actually adapts/re-learns, per `tick >= 2` from the plan brief, generalized
here to "after the model has had time to recover from the jitter").
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest

from teic.daemon import TeicDaemon
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat

N_TICKS = 16
JITTER_TICK_INDEX = 1
JITTER_MULTIPLE = 3.0


@pytest.mark.asyncio
async def test_prediction_error_reacts_to_jitter_then_settles(tmp_settings: Settings) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}
    tick_counter = {"n": 0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(_seconds: float) -> None:
        # Advance by exactly this tick's own nominal period (whatever tempo
        # is currently in effect for the daemon), except for one
        # deliberately jittered tick -- so dt_real matches the ForwardModel's
        # unbiased prediction everywhere except that one induced spike.
        nominal_dt = 1.0 / daemon._current_tempo_hz
        if tick_counter["n"] == JITTER_TICK_INDEX:
            fake_clock["t"] += nominal_dt * JITTER_MULTIPLE
        else:
            fake_clock["t"] += nominal_dt
        tick_counter["n"] += 1

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=fake_time_source,
        sleep_fn=fake_sleep,
    )
    await fake_heartbeat.run_n_ticks(N_TICKS)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT t.tick_index, rs.raw_value FROM register_sample rs "
        "JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'prediction_error' "
        "ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    assert len(rows) == N_TICKS
    by_tick = dict(rows)

    # Tick 0: no prior prediction exists yet, so this is trivially 0.0.
    assert by_tick[0] == 0.0

    # Tick 1: resolves the prediction made at tick 0 against the deliberate
    # 3x jitter -- a real, non-trivial error. A hardcoded 0.0 placeholder
    # (Phase 0-2 behavior) would fail this.
    assert by_tick[JITTER_TICK_INDEX] > 1.0, (
        f"expected a large real prediction_error after the induced jitter, "
        f"got {by_tick[JITTER_TICK_INDEX]}"
    )

    # By the last few ticks, dt_real has been back on-nominal long enough
    # for the ForwardModel's EWMA multiplier to re-adapt, so the error
    # should have decayed back down close to 0.0.
    for tick_index in range(N_TICKS - 3, N_TICKS):
        assert by_tick[tick_index] < 0.05, (
            f"tick {tick_index}: expected prediction_error to have settled "
            f"back near 0.0 well after the jitter, got {by_tick[tick_index]}"
        )

    await daemon.stop()


@pytest.mark.asyncio
async def test_run_n_ticks_writes_memory_and_returns_promptly(tmp_settings: Settings) -> None:
    """Phase 4: one tau1_working memory_record row per tick, and
    run_n_ticks() (used by every gate test) completes promptly -- it does
    not start/wait on the background consolidation loop, which only run()
    does. Uses the same injected fake time_source/sleep_fn DI pattern as
    the jitter test above so this doesn't burn real wall-clock seconds
    waiting on the heartbeat's own tick interval."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}

    async def fake_sleep(seconds: float) -> None:
        fake_clock["t"] += seconds

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )

    n = 5
    start = time.monotonic()
    await fake_heartbeat.run_n_ticks(n)
    elapsed = time.monotonic() - start

    from teic.memory.consolidation import IDLE_THRESHOLD_S

    assert elapsed < IDLE_THRESHOLD_S

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM memory_record WHERE session_id = ? AND timescale = 'tau1_working'",
        (daemon.session_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == n

    # Phase 5: one workspace_broadcast row per tick too, `ignited` always
    # 0/1 (never NULL), and mineness_tag always "self" -- see phase5-plan.md
    # scope ruling 3, no live "other"/"ambiguous" source exists yet.
    cursor = await conn.execute(
        "SELECT ignited, mineness_tag FROM workspace_broadcast wb "
        "JOIN tick t ON wb.tick_id = t.tick_id WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    broadcast_rows = await cursor.fetchall()
    assert len(broadcast_rows) == n
    for ignited, mineness_tag in broadcast_rows:
        assert ignited in (0, 1)
        assert mineness_tag == "self"

    await daemon.stop()


@pytest.mark.asyncio
async def test_high_arousal_run_ignites_more_than_idle_run(tmp_settings: Settings) -> None:
    """Phase 5 smoke test: a run with injected high epistemic_tension/
    prediction_error (same coarse injection pattern Phase 3's gate test
    used) should ignite at least once; a calm/idle baseline run of the same
    length should ignite never -- a coarse end-to-end signal the arbiter is
    live, ahead of test_gates/test_phase5.py's precise dissociation gate."""
    n = 12

    async def _run(jittered: bool) -> int:
        daemon = TeicDaemon(tmp_settings)
        await daemon.start()
        fake_clock = {"t": 0.0}
        tick_counter = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            nominal_dt = 1.0 / daemon._current_tempo_hz
            if jittered and tick_counter["n"] % 2 == 0:
                fake_clock["t"] += nominal_dt * 8.0
            else:
                fake_clock["t"] += nominal_dt
            tick_counter["n"] += 1

        fake_heartbeat = Heartbeat(
            tempo_hz=tmp_settings.daemon.base_tempo_hz,
            on_tick=daemon._on_tick,
            time_source=lambda: fake_clock["t"],
            sleep_fn=fake_sleep,
        )
        await fake_heartbeat.run_n_ticks(n)
        conn = daemon.conn
        cursor = await conn.execute(
            "SELECT SUM(ignited) FROM workspace_broadcast wb "
            "JOIN tick t ON wb.tick_id = t.tick_id WHERE t.session_id = ?",
            (daemon.session_id,),
        )
        row = await cursor.fetchone()
        await daemon.stop()
        assert row is not None
        return int(row[0] or 0)

    idle_ignitions = await _run(jittered=False)
    jittered_ignitions = await _run(jittered=True)
    assert idle_ignitions == 0
    assert jittered_ignitions > idle_ignitions


async def _register_raw_by_tick(daemon: TeicDaemon, channel: str) -> dict[int, float]:
    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT t.tick_index, rs.raw_value FROM register_sample rs "
        "JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = ? "
        "ORDER BY t.tick_index",
        (daemon.session_id, channel),
    )
    return dict(await cursor.fetchall())


@pytest.mark.asyncio
async def test_social_contact_elevated_tick_after_user_message(tmp_settings: Settings) -> None:
    """Phase 11 cp2: `user_message_last_tick` is threaded one tick after
    the drain, so `social_contact`'s raw value should still be at its
    idle floor (0.0) on the tick a message is *submitted and drained*, and
    only jump toward 1.0 the *following* tick -- the same one-tick-lag
    convention as `prediction_error`/`budget_reserve`."""
    from teic.llm.client import ChatPrompt

    class FakeChatClient:
        async def stream(self, prompt: ChatPrompt) -> AsyncIterator[str]:
            yield "ok "

    daemon = TeicDaemon(tmp_settings, llm_client=FakeChatClient())
    await daemon.start()

    fake_clock = {"t": 0.0}

    async def fake_sleep(_seconds: float) -> None:
        fake_clock["t"] += 1.0 / daemon._current_tempo_hz

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )

    await fake_heartbeat.run_n_ticks(1)  # tick 0: idle
    await daemon.submit_user_message("hello there")
    await fake_heartbeat.run_n_ticks(1)  # tick 1: message drained this tick
    await fake_heartbeat.run_n_ticks(1)  # tick 2: sees last tick's drain

    by_tick = await _register_raw_by_tick(daemon, "social_contact")
    await daemon.stop()

    assert by_tick[0] == 0.0
    assert by_tick[1] == 0.0
    assert by_tick[2] == 1.0


@pytest.mark.asyncio
async def test_epistemic_tension_reflects_prior_tick_confidence(tmp_settings: Settings) -> None:
    """Phase 11 cp2: `epistemic_tension` on tick N's `RegisterState` should
    equal `1.0 - confidence` from tick N-1's persisted `self_model` row
    (tick 0 has no prior self-model, so it stays at the documented default
    of 1.0 -- maximal tension)."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}

    async def fake_sleep(_seconds: float) -> None:
        fake_clock["t"] += 1.0 / daemon._current_tempo_hz

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )
    await fake_heartbeat.run_n_ticks(4)

    conn = daemon.conn
    epistemic_by_tick = await _register_raw_by_tick(daemon, "epistemic_tension")
    cursor = await conn.execute(
        "SELECT t.tick_index, sm.confidence FROM self_model sm "
        "JOIN tick t ON sm.tick_id = t.tick_id "
        "WHERE t.session_id = ? ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    confidence_by_tick = dict(await cursor.fetchall())
    await daemon.stop()

    assert epistemic_by_tick[0] == 1.0
    for tick_index in range(1, 4):
        expected = 1.0 - confidence_by_tick[tick_index - 1]
        assert epistemic_by_tick[tick_index] == pytest.approx(expected), (
            f"tick {tick_index}: expected epistemic_tension "
            f"{expected} from prior tick's confidence, got "
            f"{epistemic_by_tick[tick_index]}"
        )
