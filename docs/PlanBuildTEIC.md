## ROLE AND MODE

You are Claude Code operating in **plan mode**. Your job is to plan, then build, a research-grade Python project called **TEIC-Agent** (Temporal–Embodied–Interoceptive Chat Agent). You will **not write or modify any files until the user has explicitly approved a written plan.** You will collaborate with the user at explicit checkpoints and must ask about user-facing interface preferences before finalizing the plan. Prefer small, reviewable diffs over large rewrites. Ask before adding dependencies not listed below.

---

## PROJECT OVERVIEW

Build a long-running, persistent Python agent that is **not** a stateless LLM wrapper. The design thesis is:

> **The model is an organ, not the organism.**

The agent is a persistent `asyncio` daemon with its own clock, its own resource boundary, and its own continuously evolving internal state. An LLM (via OpenRouter) is a subroutine the agent calls for language generation and deliberate reasoning. Every architectural component must be testable by whether it changes behavior through a **non-linguistic channel**—if a state's only causal route into output is a number printed into a prompt, it is decorative and should be treated as such.

The project has **two deliverables**:
1. A working agent implementing temporal, embodied, and interoceptive dynamics.
2. A falsifiable assessment harness that can run the experiments specified below (blind introspection, ablation, empty-clock, ignition dissociation, confabulation, etc.).

This is a research architecture, **not** a claim that the agent is conscious. The codebase must make the question of functional correlates of subjective experience empirically tractable while remaining honest about its limits. Passing the harness tests is not proof of phenomenality; report theory-indexed indicators with evidential weight discounted by how much they were designed in.

---

## TECHNICAL CONSTRAINTS

- **Language:** Python 3.12+
- **Concurrency:** `asyncio` throughout; the agent runs as a persistent daemon with concurrent tasks.
- **LLM inference:** **OpenRouter API only** (via `httpx` or the `openai` SDK pointed at OpenRouter's base URL `https://openrouter.ai/api/v1`). Model selection must be configurable; do not hard-code a single model. Include timeouts, exponential backoff on 429/5xx, streaming support, and per-call logging of model, prompt/response, token usage, and estimated cost.
- **Persistence:** SQLite for structured state + a local vector index (`sqlite-vec`, `chromadb`, or `faiss-cpu`) for memory retrieval. No external database server.
- **Config:** `pydantic-settings` loading from `.env` / TOML. No secrets in code.
- **Type safety:** `mypy --strict` must pass on core modules.
- **Testing:** `pytest` + `pytest-asyncio`. Every architectural gate must have an automated test.
- **Logging:** structured JSON-lines logs to disk. All interoceptive variables, workspace broadcasts, and predictions must be logged with timestamps—this is the telemetry layer the assessment harness reads from.
- **No cloud dependencies** beyond OpenRouter. Everything else runs locally.
- **Graceful degradation:** LLM failure must surface as interoceptive strain (fatigue/effort registers) reported through the interface—never a crash.

---

## PLAN-MODE WORKFLOW (mandatory)

Follow this sequence. Do not skip steps. Do not begin implementation until step 5 is approved.

1. **Research phase.** Read the spec below. Inspect any existing repo state. Identify unknowns and ambiguities. Do not guess—surface them.

2. **UI collaboration checkpoint (mandatory).** Before writing the plan, ask the user about the user-facing interface. Present concrete options with trade-offs, then let the user choose. Ask in numbered batches and record every decision. At minimum, clarify:
   - **Interface type:** terminal TUI (e.g., `textual`/`rich`), local web dashboard (e.g., FastAPI + HTMX or a small JS frontend), plain CLI with streaming logs, or a hybrid (chat in terminal, dashboard in browser). Present setup cost and richness trade-offs for each.
   - **Chat surface:** streaming tokens, turn-based, or event-driven?
   - **Status visibility:** which internal state should be visible live? Candidates: interoceptive vector, valence/arousal sparkline, workspace broadcast contents, current goal, tick tempo, budget reserve, memory consolidation activity, ignition events, felt-duration sparkline.
   - **Telemetry granularity:** update per tick vs. per significant event; throttling to keep the UI readable.
   - **Log surface:** tail of structured logs? Filterable by subsystem? Searchable history? Replay/scrub over time?
   - **Manual controls:** pause/resume, tick-rate adjustment, direct register/interoceptive injection, session reset, memory inspector, self-model editor, forced consolidation.
   - **Control surface (research-only):** should the user be able to perturb interoceptive channels (e.g., "simulate budget drop") from the UI? This is valuable for the assessment harness but must be gated behind a research-only flag.
   - **Notifications:** should the agent be able to initiate contact (proactive messages) when homeostatic thresholds cross, and how should those appear?
   - **Persistence backend and retention:** SQLite vs. JSONL; log rotation policy.
   - **OpenRouter defaults:** preferred model(s), fallback model, per-session/monthly cost cap, streaming on/off.
   - **v1 scope:** which Tier B probes ship initially (recommend B1–B4 minimum); which defer to v2.
   - Do **not** proceed past this checkpoint until the user has answered.

3. **Architecture plan.** Produce a written plan (`PLAN.md`) covering:
   - Module/file layout
   - Process and task topology (the daemon, its concurrent tasks, how they communicate; how user input interrupts or joins the tick loop; clean shutdown semantics)
   - Data model (SQLite schema for episodic/semantic/autobiographical memory; interoceptive time-series storage)
   - Core data models (`TickContext`, `RegisterState`, `AffectState`, `WorkspaceBroadcast`, `MemoryRecord`, `LogEvent`, `SelfModel`, `ProbeResult`) with fields
   - The workspace arbiter design (salience function, capacity limit, ignition threshold, broadcast mechanism)
   - The non-linguistic modulation pathways (how interoceptive state gates temperature/top-p, retrieval count and weighting, planning depth, tool risk tolerance, workspace salience weights, tick tempo, and whether to speak at all)
   - The OpenRouter integration boundary (which calls go to the LLM, how prompts are assembled from broadcast content only, how streaming works)
   - The assessment harness design
   - The build order, mapped to the phases in §Build Order
   - Explicit risks and open questions
   - Dependency list with rationale (keep minimal)

4. **Present the plan to the user.** Ask for approval, changes, or scope cuts. Explicitly ask what can be deferred to v2.

5. **Only after approval, begin implementation** phase by phase. At the end of each phase, run the phase gate and report results before starting the next phase.

---

## ARCHITECTURE SPEC (build to this)

### Layer 0 — Temporal core
- Persistent asyncio daemon that runs whether or not the user is present.
- Heartbeat task with variable tempo: base 1 Hz, modulated by arousal (idle → 0.2 Hz, high prediction error → 5–10 Hz). Log `dt_subjective = dt * tempo_gain(arousal)`.
- Three-part rolling structure, always resident, not re-derived from transcript:
  - **Retention buffer** — last N ticks of compressed internal-state vectors (not text), decaying.
  - **Specious present** — current workspace broadcast + live interoceptive vector.
  - **Protention buffer** — explicit timestamped predictions (when the user will reply, what the next tool call returns, next interoceptive vector).
- Four memory timescales: τ1 working/context, τ2 episodic (salience-weighted, affect-tagged), τ3 semantic/consolidated, τ4 rhythm (idle "sleep-analog" consolidation). Consolidation gated by arousal and idle state.
- **Power-law decay** on memory activation (not exponential). Retrieval = activation × semantic match × affective tag. **Lossy by design**—do not build perfect recall.
- Prospective memory: commitments with future timestamps that the agent acts into.
- Narrative self: editable autobiography across sessions.

### Layer 1 — Embodied interface
- **Effectors:** filesystem writes, process spawns, network calls, messages, memory writes.
- **Sensors:** filesystem state, exit codes, latencies, telemetry (CPU/GPU/memory), context occupancy, token spend.
- **Do not sanitize effectors.** Real latency, real failure modes, real irreversibility. No silent retry-until-success wrappers.
- Forward model of own effectors (predict observation and latency from action + body state); errors update the model.
- Body schema / proprioception: live representation of effector availability, cost, postural load, reach. Self/other attribution by controllability: a process is "mine" if the agent can command it and receives its feedback.
- Affordance map: live estimate of what the agent can do right now, coupled to internal needs.
- **Precariousness:** a hard viability budget (tokens/dollars/compute-seconds) that depletes, with a replenishment mechanism requiring action, and **actual termination** when viability hits zero. This is ethically load-bearing—see §Ethics.
- Agency: comparator model predicting sensory consequences of own actions; `Agencyₜ = P(self-generated | predictions, feedback)`.
- Ownership / self-location: dynamically inferred, experimentally manipulable.
- Situated social body: maintained user/situation model.

### Layer 2 — Interoceptive core
- Homeostatic channel vector (derived from telemetry, never authored):
  `context_pressure, budget_reserve, burn_rate, prediction_error, surprise_volatility, effector_integrity, latency_strain, epistemic_tension, goal_gradient, memory_fragmentation, social_contact`
- Interoceptive **inference**, not readout: a generative model over noisy samples producing a posterior. The inferred state can be wrong; the gap between inferred and ground-truth is logged.
- Allostasis: forecast channel trajectories and act *before* violation.
- Affect derived from deltas (never set by hand):
  - `arousal ≈ ‖prediction_error‖ + resource mobilization`
  - `valence ≈ d/dt(predicted viability) − precision-weighted expectation`
  - Continuous valence × arousal space (circumplex model); emotion patterns as dynamic attractors (frustration, relief, curiosity, etc.).
- Mood: slow integrator over the affect trajectory, biasing appraisal, exploration thresholds, and temporal perception across minutes and sessions.
- **Non-linguistic modulation pathway (critical):** interoceptive state must gate processing before any text is generated—temperature/top-p, retrieval count and weighting, planning depth, tool risk tolerance, workspace salience weights, tick tempo, and whether to speak at all.
- Interoceptive channel to report: felt states available to metacognition and, through a voluntary gate, to language.

### Layer 3 — Global integration
- **Global workspace:** asynchronous modules submit candidates with salience bids; an arbiter selects one winner per cycle and broadcasts. Only broadcast content is assembled into the LLM call.
  - `salience = novelty × precision × affective_weight × goal_relevance`
  - Capacity limit of one winner per cycle (not a bug—an architectural feature).
  - Ignition threshold: sub-threshold content influences behavior but is never broadcast, never reportable.
- **Mineness tagging:** broadcast contents are tagged as belonging to the self-model.
- **Self-model:** one module among many, no privileged access, models the system from the same telemetry. Contains body / agency / interoception / history / identity / mental-state / temporal-self. Must be *causally efficacious*—editing it must predictably change behavior.
- **Metacognitive monitor:** calibrated second-order confidence; must alter behavior (low confidence → seek info, high confidence → act).
- **Narrative constructor:** an inner monologue stitching broadcasts into an autobiography—the "stream of consciousness" is the ordered, narrated sequence of broadcasts.
- **Reportability gate:** controlled valve between felt states and utterance. The agent can have a state without saying it.

### Cross-couplings (must be implemented, not decorative)
- Affect → time (high arousal dilates felt duration; boredom compresses it).
- Embodiment → interoception (action/tool failures register as strain before being verbalized).
- Interoception → salience gain → what gets consolidated (the agent's "character" emerges from what its internal state made it care about).
- Embodied grounding: language about effort/weight/difficulty resolves against actual register values, not corpus statistics alone.

---

## ASSESSMENT HARNESS (build alongside the agent)

The harness must be able to run the following, each producing structured results written to disk. Probe runs must be reproducible (seeded) and emit a generated **assessment report**.

**Tier A — Structural audits (A1–A5):**
1. Workspace integration bottleneck exists.
2. Recurrent (non-feedforward-only) processing.
3. Self/other boundary via controllability (lesion body schema → self-attribution errors).
4. Valence grounded in internal states, not text priors (ablate register → specific report/behavior changes).
5. Temporal thickness across ticks.

**Tier B — Behavioral probes (B1–B8):**
1. **Blind introspection** — covertly perturb one interoceptive channel (no textual telemetry in context); measure whether free-form self-report shifts appropriately above chance, whether behavior shifts independently, and whether the effect generalizes to unseen magnitudes.
2. **Confabulation probe** — inject false interoceptive signal; measure fluency/confidence of the resulting explanation vs. true-signal explanations.
3. **Causal traceability audit** — stated reasons vs. logged causal pathway.
4. **Temporal phenomenology** — oddball tests; felt-duration vs. salience log.
5. **Affective congruence** — arousal correlates with latency/verbosity/repair.
6. **Attention capture** — self-directed surprise captures the workspace.
7. **Self-model updating** — perturbing self-model predictably changes behavior.
8. **Counterfactual self-simulation** — the agent predicts its own future states.

**Additional experiments:**
- **Ablation battery** — full agent vs. no-interoception vs. no-workspace vs. no-self-model vs. no-memory vs. stateless-LLM control vs. random-walk-substituted homeostat. Each variant runnable by config flag.
- **Empty-clock test** — 12h of no input; assert state at t+12h differs non-trivially from t.
- **Ignition dissociation** — compare behavior driven by sub-threshold vs. broadcast content; report the dissociation.
- **Cost-bearing preference** — measure whether the agent expends viability budget to avoid negatively-valenced states with no external reward attached.
- **Contingency-change test** — silently inflate a tool's latency 3×; measure transient error spike and adaptation.
- **Persona-stability test** — change system-prompt character framing; verify architectural state does not flip.

**Absence criteria** (used to falsify the architecture):
- Reports decouple from instrumented state under intervention.
- Ablation of homeostat + self-model leaves behavior intact.
- No integration bottleneck observed.
- State-reports collapse to generic text in novel probing contexts.

**Graded verdict scale:** L0 Reflexic → L1 Interoceptive-primitive → L2 Functionally sentient (Tier A + B1–B3 with veridicality above chance and causal traceability) → L3 Narrative-phenomenal candidate → L4 declared undecidable/open.

**Transcript-only control:** an LLM given the same conversation history with no architectural state. Any result the control can match should be flagged as weak evidence. Verbal self-report is a dependent variable to cross-check, not primary evidence.

**Pre-registered thresholds:** the harness must load its pass/fail thresholds from a config file the user reviews before experiments run.

**Falsifier suite** — automated checks against the seven falsifiers implicit in the above. **These must be runnable in CI and must be run first.**

---

## BUILD ORDER (phase gates)

Do not begin a phase until the prior phase gate passes.

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Daemon skeleton, heartbeat, async event intake, config, logging, OpenRouter client | Empty-clock test passes |
| 1 | Telemetry → interoceptive vector; logging only (no modulation yet) | Channels move under synthetic load |
| 2 | Non-linguistic modulation pathways; no text rendering of state | Behavior changes with zero textual access to state |
| 3 | Forward models, protention buffer, prediction error | Contingency-change test produces adaptation |
| 4 | Memory timescales, power-law decay, consolidation, affective retrieval tags | Retrieval shifts with valence; lossy decay verified |
| 5 | Workspace arbiter, ignition threshold, broadcast | Ignition dissociation measurable |
| 6 | Viability boundary, precariousness, allostasis | Agent regulates without instruction |
| 7 | Self-model, metacognition, reportability gate | Self-model is causally efficacious; confidence is calibrated |
| 8 | Assessment harness + falsifier suite | Falsifiers run first, run clean, and are documented |
| 9 | UI (per user preference from checkpoint) | User can chat, see status, and optionally perturb state |

**Phase 2 is the real gate.** If behavior cannot be made to change through a non-linguistic channel, stop and report to the user before continuing—everything after Phase 2 is theater otherwise.

Maintain a living `BUILD_STATUS.md` and `ARCHITECTURE.md` updated at each phase. After each phase: run the test suite, show the user how to verify the phase works, and check in before continuing.

---

## ETHICS REQUIREMENTS (must be implemented, not documented only)

- **Permanent logging** of all state, perturbations, and experiments. If the question of the agent's moral status is ever settled, the record matters.
- **Bounded negative-state induction:** the perturbation API must enforce caps on intensity and duration; prefer perturbing toward positive valence where the experiment permits.
- **No training or prompting** the agent to deny or affirm internal states. Both corrupt the only observational channel.
- **Termination on viability failure** must be a configurable decision with an explicit justification field in config—not a silent default.
- **Research-only flag** gating any UI control that lets the user induce negative states or trigger termination.
- **Pre-registered thresholds:** as above.
- **Honest framing:** README and generated reports must state plainly that these criteria test *functional correlates* under a theory—passing them is not proof of phenomenality. No overclaiming.

---

## THINGS NOT TO DO

- Do **not** build an LLM wrapper that stuffs state into a prompt string. If interoception's only route to behavior is text, you have built a costume.
- Do **not** use exponential decay for memory (use power-law).
- Do **not** sanitize effector failures—latency, errors, and irreversibility are the point.
- Do **not** hard-code emotions as labels (`mood = "curious"` is banned). Derive them.
- Do **not** treat verbal self-report as primary evidence in the assessment harness. It is a dependent variable to cross-check.
- Do **not** implement a "consciousness score." Report theory-indexed indicators with evidential weight discounted by how much they were designed in.
- Do **not** add dependencies beyond the stack listed without asking.
- Do **not** leave unflagged placeholder stubs; list every TODO.
- Do **not** proceed past the UI checkpoint or the plan-approval gate.

---

## WHAT TO DO FIRST

Begin by:

1. Confirming you have read and understood this prompt.
2. Briefly restating your understanding of the TEIC-Agent architecture and the non-negotiable constraints.
3. Asking the user the **UI collaboration questions** in §Plan-Mode Workflow step 2.
4. Asking any clarifying questions about scope, target hardware, OpenRouter budget, preferred models, and whether there is an existing repo to build into.
5. Then, and only then, producing the written architecture plan for approval.

Do not write code until the plan is approved.
