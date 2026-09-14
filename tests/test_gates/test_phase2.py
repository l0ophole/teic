"""Phase 2 gate: non-linguistic modulation, the real gate.

Two parts, matching PLAN.md's gate wording ("Identical prompt text,
different registers -> divergent tempo/temperature/speak-gate"):

1. Daemon-level: a synthetic jittered run (same DI pattern as
   `test_phase1.py`) shows the heartbeat's own tempo -- fixed in Phase 0/1
   -- now genuinely varies tick to tick, and `affect_sample` is no longer
   pinned at Phase 1's flat neutral placeholder. This is the concrete
   "behavior changes with zero textual access to state" requirement.
2. Unit-level (delegated to `tests/test_interoception/test_modulation.py`,
   re-asserted here against snapshots pulled from THIS run's own DB rows):
   feeding an early-tick and a late-tick register/affect snapshot through
   `assemble_prompt` with byte-identical broadcast/narrative_tail produces
   identical prompt text with divergent temperature/tempo_hz/speak-gate.

No assertion is made on real LLM calls or generated text -- there is still
no workspace/arbiter wiring an actual chat turn (that's Phase 5+); this
phase proves the modulation *pathway*, not an end-to-end turn.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from teic.daemon import TeicDaemon
from teic.interoception.modulation import ModulationCompute
from teic.llm.prompt_assembly import assemble_prompt
from teic.models.affect import AffectState
from teic.models.registers import REGISTER_CHANNELS, RegisterState
from teic.models.workspace import WorkspaceBroadcast, WorkspaceCandidate
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat

N_TICKS = 40
# Wider swing than Phase 1's sequence so surprise_volatility/latency_strain
# (and therefore arousal) move meaningfully, not just marginally.
_JITTER_SECONDS = [0.02, 0.5]


@pytest.mark.asyncio
async def test_phase2_tempo_and_affect_vary_and_prompt_gate_holds(
    tmp_settings: Settings,
) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}
    tick_counter = {"n": 0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(_seconds: float) -> None:
        idx = tick_counter["n"] % len(_JITTER_SECONDS)
        fake_clock["t"] += _JITTER_SECONDS[idx]
        tick_counter["n"] += 1

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=fake_time_source,
        sleep_fn=fake_sleep,
    )
    await fake_heartbeat.run_n_ticks(N_TICKS)

    conn = daemon.conn

    # 1a. tick.tempo_hz is no longer fixed.
    cursor = await conn.execute(
        "SELECT DISTINCT t.tempo_hz FROM tick t WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    distinct_tempos = {row[0] for row in await cursor.fetchall()}
    assert len(distinct_tempos) > 1, (
        "tick.tempo_hz should move across ticks now that ModulationCompute "
        "feeds tempo_hz back into the heartbeat -- Phase 0/1 always wrote "
        "the same fixed base_tempo_hz"
    )

    # 1b. affect_sample is no longer Phase 1's flat neutral placeholder.
    cursor = await conn.execute(
        "SELECT DISTINCT a.valence FROM affect_sample a "
        "JOIN tick t ON a.tick_id = t.tick_id WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    distinct_valences = {row[0] for row in await cursor.fetchall()}
    assert distinct_valences != {0.0}, (
        "affect_sample.valence should move now that AffectDynamics computes "
        "it from real registers -- Phase 1 always wrote the flat 0.0 placeholder"
    )

    # 2. Pull an early and a late tick's full register+affect snapshot from
    # this same run and re-verify the literal gate wording against them.
    async def _snapshot(tick_index: int) -> tuple[RegisterState, AffectState]:
        cursor = await conn.execute(
            "SELECT t.tick_id, t.wall_ts FROM tick t "
            "WHERE t.session_id = ? AND t.tick_index = ?",
            (daemon.session_id, tick_index),
        )
        tick_id, wall_ts = await cursor.fetchone()  # type: ignore[misc]
        ts = datetime.fromisoformat(wall_ts)

        cursor = await conn.execute(
            "SELECT channel, inferred_value, inferred_var FROM register_sample "
            "WHERE tick_id = ?",
            (tick_id,),
        )
        rows = await cursor.fetchall()
        values = {row[0]: row[1] for row in rows}
        variances = {row[0]: row[2] for row in rows}
        registers = RegisterState(
            **{ch: values[ch] for ch in REGISTER_CHANNELS},
            variances=variances,
            tick_id=tick_id,
            ts=ts,
        )

        cursor = await conn.execute(
            "SELECT valence, arousal, mood FROM affect_sample WHERE tick_id = ?",
            (tick_id,),
        )
        valence, arousal, mood = await cursor.fetchone()  # type: ignore[misc]
        affect = AffectState(valence=valence, arousal=arousal, mood=mood, tick_id=tick_id, ts=ts)
        return registers, affect

    early_registers, early_affect = await _snapshot(0)
    late_registers, late_affect = await _snapshot(N_TICKS - 1)

    compute = ModulationCompute(
        idle_tempo_hz=tmp_settings.daemon.idle_tempo_hz,
        max_tempo_hz=tmp_settings.daemon.max_tempo_hz,
    )
    early_params = compute.compute(early_registers, early_affect, early_affect.mood)
    late_params = compute.compute(late_registers, late_affect, late_affect.mood)

    winner = WorkspaceCandidate(
        source_module="test",
        content={"text": "identical broadcast content"},
        novelty=0.5,
        precision=0.5,
        affective_weight=0.5,
        goal_relevance=0.5,
    )
    broadcast = WorkspaceBroadcast(
        broadcast_id="bc-1",
        tick_id=early_registers.tick_id,
        winner=winner,
        ignited=True,
        mineness_tag="self",
        ts=early_affect.ts,
    )
    narrative_tail: list[str] = ["identical", "narrative", "tail"]

    early_prompt = assemble_prompt(broadcast, narrative_tail, early_params)
    late_prompt = assemble_prompt(broadcast, narrative_tail, late_params)

    assert early_prompt.messages == late_prompt.messages
    assert (
        early_params.tempo_hz != late_params.tempo_hz
        or early_prompt.temperature != late_prompt.temperature
        or early_params.speak_gate_open != late_params.speak_gate_open
    ), "expected at least one modulated channel to diverge across this run's snapshots"

    await daemon.stop()
