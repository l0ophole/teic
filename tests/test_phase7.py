"""Phase 7 cp3: daemon tick-loop integration for self-model + metacognition.

Distinct from the unit-level `tests/test_gates/test_phase7.py` (which
constructs `SelfModel`/`ConfidenceEstimate`/`ModulationCompute` directly).
These tests drive them through `TeicDaemon._on_tick` -- the real tick loop,
real `ChannelPipeline`/`WorkspaceArbiter` wiring -- using the same injected
`time_source`/`sleep_fn` DI pattern as `tests/test_daemon.py`.
"""

from __future__ import annotations

import pytest

from teic.daemon import TeicDaemon
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat


def _fake_heartbeat(daemon: TeicDaemon, tmp_settings: Settings) -> tuple[Heartbeat, dict[str, float]]:
    fake_clock = {"t": 0.0}

    async def fake_sleep(_seconds: float) -> None:
        fake_clock["t"] += 1.0 / daemon._current_tempo_hz

    heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )
    return heartbeat, fake_clock


@pytest.mark.asyncio
async def test_self_model_row_persisted_and_versions_across_real_ticks(
    tmp_settings: Settings,
) -> None:
    """Real tick loop must write one `self_model` row per tick, with
    `version` incrementing 1, 2, 3, ... -- not a single static row."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    n = 5
    await heartbeat.run_n_ticks(n)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT sm.version FROM self_model sm JOIN tick t ON sm.tick_id = t.tick_id "
        "WHERE t.session_id = ? ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    versions = [row[0] for row in rows]
    assert versions == list(range(1, n + 1))

    assert daemon._self_model is not None
    assert daemon._self_model.version == n

    await daemon.stop()


@pytest.mark.asyncio
async def test_confidence_and_goal_gradient_lagged_one_tick_into_downstream(
    tmp_settings: Settings,
) -> None:
    """Confidence/prior_ignited feed `ModulationCompute.compute()`, and
    `identity_traits["goal_gradient"]` feeds `ChannelPipeline.process()` --
    both only for the *next* tick after the self-model that produced them,
    the same one-tick-lag pattern as prediction_error/budget_reserve. Tick 0
    (no self-model exists yet) must see the neutral defaults; tick 1 must
    see values actually derived from tick 0's real self-model."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    assert daemon._confidence is None
    assert daemon._prior_goal_gradient == 0.0

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(1)

    # After tick 0: a real self-model/confidence now exists, stored for
    # tick 1's modulation/sensing calls to consume.
    assert daemon._self_model is not None
    assert daemon._confidence is not None
    first_goal_gradient = daemon._prior_goal_gradient
    assert first_goal_gradient == daemon._self_model.identity_traits["goal_gradient"]

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT rs.raw_value FROM register_sample rs JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'goal_gradient' ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    # Tick 0's own sensing ran before any self-model existed: neutral 0.0.
    assert rows[0][0] == 0.0

    await heartbeat.run_n_ticks(1)

    cursor = await conn.execute(
        "SELECT rs.raw_value FROM register_sample rs JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'goal_gradient' ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    # Tick 1's sensing must read tick 0's real (lagged) goal_gradient value,
    # not another hardcoded 0.0 -- proves the wiring actually threads a real
    # signal across the tick boundary rather than being a dead parameter.
    assert rows[1][0] == first_goal_gradient

    await daemon.stop()


@pytest.mark.asyncio
async def test_self_model_row_fields_match_real_daemon_telemetry(
    tmp_settings: Settings,
) -> None:
    """The persisted `self_model` row's `confidence`/`agency` must be real
    values derived from this run's actual telemetry, not fixed placeholders
    -- confidence must sit in the valid [0, 1] range and reflect the
    `ConfidenceEstimate` the daemon actually computed that tick."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(3)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT sm.confidence, sm.agency FROM self_model sm JOIN tick t ON sm.tick_id = t.tick_id "
        "WHERE t.session_id = ? ORDER BY t.tick_index DESC LIMIT 1",
        (daemon.session_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    confidence, agency = row
    assert 0.0 <= confidence <= 1.0
    assert 0.0 <= agency <= 1.0
    assert daemon._confidence is not None
    assert confidence == daemon._confidence.confidence

    await daemon.stop()
