"""Phase 6 cp3: daemon/arbiter integration for viability + allostasis.

Distinct from the unit-level `tests/test_gates/test_phase6.py` (which
constructs `ViabilityBudget`/`AllostaticForecaster`/`TerminationGate`
directly). These tests drive them through `TeicDaemon._on_tick` -- the real
tick loop, real `ChannelPipeline`/`WorkspaceArbiter` wiring -- using the same
injected `time_source`/`sleep_fn` DI pattern as `tests/test_daemon.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from teic.daemon import TeicDaemon
from teic.settings import Settings, ViabilitySettings
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
async def test_budget_reserve_depletes_under_real_spend(tmp_settings: Settings) -> None:
    """Real spend (never synthetic per-tick decay) must actually move the
    ledger, and the moved value must show up in the sensed budget_reserve/
    burn_rate channels one tick later (Phase 6 task 7's one-tick-lag wiring)."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    # Seed pricing so render_prompt_if_ignited's real assembled prompt
    # actually costs something -- PricingCache.estimate_cost_usd() returns
    # 0.0 for any model it has no entry for, and no real OpenRouter refresh
    # happens in this checkpoint's scope.
    assert daemon._pricing is not None
    daemon._pricing._prices[tmp_settings.llm.primary_model] = {"prompt": 0.01, "completion": 0.0}

    n = 12
    fake_clock = {"t": 0.0}
    tick_counter = {"n": 0}

    async def jittered_sleep(_seconds: float) -> None:
        # Same coarse jitter-forcing pattern as
        # test_daemon.test_high_arousal_run_ignites_more_than_idle_run --
        # ignitions are what makes render_prompt_if_ignited return non-None,
        # which is what makes spend() ever receive a nonzero cost.
        nominal_dt = 1.0 / daemon._current_tempo_hz
        if tick_counter["n"] % 2 == 0:
            fake_clock["t"] += nominal_dt * 8.0
        else:
            fake_clock["t"] += nominal_dt
        tick_counter["n"] += 1

    heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=jittered_sleep,
    )
    await heartbeat.run_n_ticks(n)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT t.tick_index, rs.raw_value FROM register_sample rs "
        "JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'budget_reserve' "
        "ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    by_tick = dict(rows)
    assert len(by_tick) == n
    # Tick 0 reads the ledger before any spend has happened this session:
    # full reserve.
    assert by_tick[0] == 1.0
    # Some later tick must show a real, sensed drop -- a hardcoded 1.0
    # placeholder (pre-cp3 behavior) would fail this.
    assert min(by_tick[i] for i in range(1, n)) < 1.0

    assert daemon._viability_budget is not None
    assert daemon._viability_budget.last_spend_usd >= 0.0
    assert daemon._viability_budget.reserve_usd < daemon._viability_budget._settings.monthly_budget_usd

    await daemon.stop()


@pytest.mark.asyncio
async def test_idle_run_never_spends_or_replenishes(tmp_settings: Settings) -> None:
    """A calm/idle run (no jitter) never ignites, per test_daemon.py's own
    phase 5 baseline -- so it should never spend (no prompt ever rendered)
    and never replenish (no ignited viability winner ever occurs). The
    reserve must stay exactly at its starting value throughout."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    assert daemon._pricing is not None
    daemon._pricing._prices[tmp_settings.llm.primary_model] = {"prompt": 0.01, "completion": 0.0}

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    n = 8
    await heartbeat.run_n_ticks(n)

    assert daemon._viability_budget is not None
    assert daemon._viability_budget.reserve_usd == tmp_settings.viability.monthly_budget_usd

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM workspace_broadcast wb JOIN tick t ON wb.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND wb.winner_source = 'viability'",
        (daemon.session_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 0

    await daemon.stop()


@pytest.mark.asyncio
async def test_low_reserve_bids_viability_candidate_and_replenishment_requires_it(
    tmp_settings: Settings,
) -> None:
    """A precarious reserve must bid a real "viability" candidate into the
    workspace (allostatic pressure, not a background cron job), and
    replenish() must only ever be reached through that candidate actually
    winning and igniting -- never as a silent top-up."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    assert daemon._viability_budget is not None
    budget = daemon._viability_budget
    # Force the reserve down to well below VIABILITY_PRESSURE_THRESHOLD
    # (0.2) *before* any tick runs, so the very first tick's sensed
    # budget_reserve is already precarious.
    budget.spend(budget.reserve_usd - 0.5)
    assert budget.reserve_channel() < 0.2

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    await heartbeat.run_n_ticks(1)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT wb.winner_source, wb.ignited FROM workspace_broadcast wb "
        "JOIN tick t ON wb.tick_id = t.tick_id WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    winner_source, ignited = await cursor.fetchone()
    assert winner_source == "viability"
    assert ignited == 1

    # The one and only replenish() call site fired: reserve is higher than
    # the post-forced-depletion value by exactly replenishment_amount_usd
    # (spend() this same tick can only ever lower it further, never raise
    # it, so this delta is unambiguously replenish()'s doing).
    assert budget.reserve_usd >= 0.5 + tmp_settings.viability.replenishment_amount_usd - budget.last_spend_usd

    await daemon.stop()


@pytest.mark.asyncio
async def test_termination_gate_refuses_when_unconfigured(tmp_settings: Settings) -> None:
    """Default settings (allow_actual_termination=False) must never let a
    depleted reserve actually halt the daemon -- refusal is silent (no log
    row) and ticking continues normally."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    assert daemon._viability_budget is not None
    daemon._viability_budget.spend(daemon._viability_budget.reserve_usd)
    assert daemon._viability_budget.reserve_usd == 0.0

    heartbeat, _ = _fake_heartbeat(daemon, tmp_settings)
    n = 4
    await heartbeat.run_n_ticks(n)

    assert daemon._terminated is False

    conn = daemon.conn
    cursor = await conn.execute("SELECT COUNT(*) FROM tick WHERE session_id = ?", (daemon.session_id,))
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == n

    cursor = await conn.execute(
        "SELECT COUNT(*) FROM log_event WHERE session_id = ? AND event_type = 'termination_fired'",
        (daemon.session_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 0

    await daemon.stop()


@pytest.mark.asyncio
async def test_termination_gate_fires_and_halts_daemon_when_configured(tmp_path: Path) -> None:
    """A fully configured gate (both keys set) must actually halt the
    daemon on a depleted reserve, log a permanent record before doing so,
    and leave every later tick in the same fixed-count run a true no-op --
    Heartbeat.run_n_ticks() has no stop-event check of its own, so this is
    what daemon.py's own `_terminated` guard is for."""
    db_path = tmp_path / "teic_test.db"
    settings = Settings(
        viability=ViabilitySettings(
            allow_actual_termination=True,
            termination_justification="authorized test termination",
        )
    )
    settings.daemon.db_path = str(db_path)

    daemon = TeicDaemon(settings)
    await daemon.start()
    assert daemon._viability_budget is not None
    daemon._viability_budget.spend(daemon._viability_budget.reserve_usd)
    assert daemon._viability_budget.reserve_usd == 0.0

    heartbeat, _ = _fake_heartbeat(daemon, settings)
    n = 5
    await heartbeat.run_n_ticks(n)

    assert daemon._terminated is True

    conn = daemon.conn
    cursor = await conn.execute("SELECT COUNT(*) FROM tick WHERE session_id = ?", (daemon.session_id,))
    row = await cursor.fetchone()
    assert row is not None
    # Termination fires at the end of the first tick's own processing, so
    # every one of the n-1 remaining run_n_ticks() calls must be a no-op:
    # exactly one tick row total.
    assert row[0] == 1

    cursor = await conn.execute(
        "SELECT payload FROM log_event WHERE session_id = ? AND event_type = 'termination_fired'",
        (daemon.session_id,),
    )
    log_row = await cursor.fetchone()
    assert log_row is not None
    assert "authorized test termination" in log_row[0]

    await daemon.stop()
