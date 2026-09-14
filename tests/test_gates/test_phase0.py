"""Phase 0 gate: daemon skeleton, fixed-tempo heartbeat, persistence, logging.

Runs a short synthetic session (real ticks, real DB writes) and a compressed
"empty-clock" style run (via an injected instant sleep_fn, standing in for the
full 12h manual verification run documented separately in BUILD_STATUS.md)
to prove the tick-and-persist mechanism itself is sound before the real
12h wall-clock run is attempted at Phase 6.
"""

from __future__ import annotations

import aiosqlite
import pytest

from teic.daemon import TeicDaemon
from teic.models.registers import REGISTER_CHANNELS
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat


@pytest.mark.asyncio
async def test_daemon_clean_start_stop_and_tick_rows(tmp_settings: Settings) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    await daemon.run_n_ticks(3)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM tick WHERE session_id = ?", (daemon.session_id,)
    )
    (tick_count,) = await cursor.fetchone()  # type: ignore[misc]
    assert tick_count == 3

    cursor = await conn.execute(
        "SELECT COUNT(*) FROM register_sample rs JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    (register_row_count,) = await cursor.fetchone()  # type: ignore[misc]
    assert register_row_count == 3 * len(REGISTER_CHANNELS)

    cursor = await conn.execute(
        "SELECT COUNT(*) FROM affect_sample a JOIN tick t ON a.tick_id = t.tick_id "
        "WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    (affect_row_count,) = await cursor.fetchone()  # type: ignore[misc]
    assert affect_row_count == 3

    await daemon.stop()

    # A fresh connection should show ended_at populated (clean shutdown persisted).
    fresh = await aiosqlite.connect(tmp_settings.daemon.db_path)
    cursor = await fresh.execute(
        "SELECT ended_at FROM session WHERE session_id = ?", (daemon.session_id,)
    )
    (ended_at,) = await cursor.fetchone()  # type: ignore[misc]
    assert ended_at is not None
    await fresh.close()


@pytest.mark.asyncio
async def test_heartbeat_synthetic_empty_clock_mechanism() -> None:
    """Fakes elapsed wall-clock time via an injected time_source/sleep_fn so
    the decay/tempo mechanism can be exercised over a simulated long span in
    milliseconds of real test time. This is the fast CI-friendly complement
    to Phase 6's genuine 12h manual empty-clock run (see PLAN.md risk #2)."""
    fake_clock = {"t": 0.0}
    tick_count = {"n": 0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(seconds: float) -> None:
        fake_clock["t"] += seconds

    async def on_tick(tick_index: int, dt_real: float) -> None:
        tick_count["n"] += 1

    heartbeat = Heartbeat(
        tempo_hz=1.0, on_tick=on_tick, time_source=fake_time_source, sleep_fn=fake_sleep
    )
    simulated_seconds = 12 * 60 * 60  # 12 simulated hours
    n_ticks = simulated_seconds  # 1 Hz
    await heartbeat.run_n_ticks(n_ticks)

    assert tick_count["n"] == n_ticks
    assert fake_clock["t"] == pytest.approx(simulated_seconds, rel=1e-6)
