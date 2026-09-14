#!/usr/bin/env python3
"""Build orchestrator: drives Claude Code headlessly through TEIC build checkpoints.

Each checkpoint segment is one `claude -p` invocation = one fresh session
(no accumulated context). The runner composes prompts from the templates in
docs/plans/PROMPTS.md, enforces mechanical protocol guards, verifies each
checkpoint (new commit + pytest + mypy), and pauses for the user between
segments (semi-attended mode; --auto runs unattended, sleeping across
rate-limit windows).

Usage:
  python scripts/orchestrate_build.py --status
  python scripts/orchestrate_build.py --phase 6            # semi-attended
  python scripts/orchestrate_build.py --phase 6 --auto     # unattended
  python scripts/orchestrate_build.py --phase 6 --dry-run  # print, don't run

Stdlib only; no venv needed.
"""

from __future__ import annotations

import argparse
import json
import re
import selectors
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT / "build-state.json"
PLAN_DIR = PROJECT / "docs" / "plans"
USAGE_FILE = PROJECT / "usage.json"
HISTORY_FILE = PROJECT / "build-history.jsonl"
CURRENT_FILE = PROJECT / "current.json"

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TURNS = 60
AUTOCOMPACT = 120000
DEFAULT_TOKEN_CEILING = 1_500_000
DEFAULT_TIMEOUT_S = 3600
RATE_LIMIT_SLEEP_BUFFER_S = 120

ALLOW_SETTINGS = {
    "permissions": {
        "allow": [
            "Bash(source .venv/bin/activate *)",
            "Bash(pytest*)",
            "Bash(mypy*)",
            "Bash(git add*)",
            "Bash(git commit*)",
            "Bash(git log*)",
            "Bash(git status*)",
            "Bash(git diff*)",
            "Bash(git rev-parse*)",
            "Bash(python *)",
            "Read(**)",
            "Edit(**)",
            "Write(**)",
            "Task",
        ],
    }
}

PLAN_PROMPT = """Read BUILD_STATUS.md (table + "Current state" only) and the Phase {phase} sections \
of docs/PlanBuildTEIC.md. Write docs/plans/phase{phase}-plan.md: file-by-file build order, \
a "## Checkpoints" section listing 2-3 session-end checkpoints as "- cp1: <name> - <what is done>", \
and a "context to read" list. Do not start building."""

FIRST_CKPT_PROMPT = """Read docs/plans/phase{phase}-plan.md and the "Current state" section of \
BUILD_STATUS.md. Build Phase {phase} per the plan, following CLAUDE.md's build protocol. \
Stop at checkpoint {cp} and run the batched verify+commit."""

NEXT_CKPT_PROMPT = """Continue Phase {phase} at checkpoint {cp} per BUILD_STATUS.md and the \
checkpoint section of docs/plans/phase{phase}-plan.md. Do not re-read completed checkpoints' \
files unless the plan requires it. Stop at checkpoint {cp} and run the batched verify+commit."""

REPAIR_PROMPT = """The post-checkpoint verification failed. Read the failing output below and \
fix it per docs/plans/phase{phase}-plan.md, following CLAUDE.md's build protocol. \
Then run the batched verify+commit.

FAILING OUTPUT:
{output}
"""


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


class Halt(Exception):
    pass


class RateLimitedHalt(Halt):
    def __init__(self, msg: str, resets_at: float | None = None):
        super().__init__(msg)
        self.resets_at = resets_at


class SegmentResult:
    def __init__(self):
        self.session_id: str | None = None
        self.num_turns: int = 0
        self.billed_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.output_tokens: int = 0
        self.duration_s: float = 0.0
        self.is_error: bool = False
        self.result_text: str = ""
        self.rate_limit: dict | None = None
        self.permission_denials: list = []


def billed_tokens(usage: dict) -> int:
    return (usage.get("input_tokens", 0)
            + (usage.get("cache_read_input_tokens", 0) or 0)
            + (usage.get("cache_creation_input_tokens", 0) or 0)
            + usage.get("output_tokens", 0))


def write_usage(info: dict, path: Path = USAGE_FILE) -> None:
    """Merge one rate_limit_info snapshot into usage.json (atomic write)."""
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    window = data.setdefault("windows", {})
    w = info.get("rateLimitType", "?")
    window[w] = {"utilization": info.get("utilization"),
                 "resets_at": info.get("resetsAt"),
                 "status": info.get("status")}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def record_segment(label: str, res: SegmentResult, outcome: str,
                   path: Path = HISTORY_FILE) -> None:
    """Append one segment record to build-history.jsonl."""
    m = re.match(r"phase(\d+)", label)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "phase": int(m.group(1)) if m else None,
        "kind": ("repair" if "repair" in label
                 else "plan" if "plan" in label else "build"),
        "turns": res.num_turns,
        "billed_tokens": res.billed_tokens,
        "cache_read_tokens": res.cache_read_tokens,
        "cache_creation_tokens": res.cache_creation_tokens,
        "output_tokens": res.output_tokens,
        "duration_s": res.duration_s,
        "outcome": outcome,
        "session_id": res.session_id,
    }
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    if res.rate_limit:
        write_usage(res.rate_limit)


def write_current(label: str) -> None:
    tmp = CURRENT_FILE.with_name(CURRENT_FILE.name + ".tmp")
    tmp.write_text(json.dumps(
        {"label": label,
         "started_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    tmp.replace(CURRENT_FILE)


def remove_current() -> None:
    try:
        CURRENT_FILE.unlink()
    except FileNotFoundError:
        pass


def parse_checkpoints(plan_path: Path) -> list[str]:
    """Parse a plan's '## Checkpoints' section for '- cpN: ...' lines."""
    text = plan_path.read_text()
    m = re.search(r"^## Checkpoints\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    section = m.group(1) if m else text
    cps = re.findall(r"^-\s+(cp\d+)\b", section, re.M)
    if not cps:
        raise Halt(f"No '- cpN:' checkpoints found in {plan_path.name} "
                   f"(plan must have a '## Checkpoints' section)")
    return cps


def transcript_path(session_id: str | None) -> str:
    if not session_id:
        return "(no session id)"
    munged = str(PROJECT).replace(".", "-").replace("/", "-")
    return str(Path.home() / ".claude" / "projects" / munged / f"{session_id}.jsonl")


def run_segment(prompt: str, *, model: str, max_turns: int,
                token_ceiling: int, timeout_s: int, dry_run: bool,
                label: str) -> SegmentResult:
    """One headless claude session. Returns parsed result; raises Halt on guard breach."""
    cmd = ["claude", "-p", "--output-format", "stream-json",
           "--permission-mode", "acceptEdits", "--permission-prompts", "none",
           "--max-turns", str(max_turns), "--autocompact", str(AUTOCOMPACT),
           "--model", model,
           "--settings", json.dumps(ALLOW_SETTINGS)]
    if dry_run:
        log(f"DRY-RUN [{label}] would run:\n  {' '.join(shlex.quote(c) for c in cmd)}")
        log(f"DRY-RUN [{label}] prompt:\n{prompt}")
        return SegmentResult()

    log(f"[{label}] launching headless claude ({max_turns} max turns)...")
    res = SegmentResult()
    final = None
    try:
        proc = subprocess.Popen(cmd, cwd=PROJECT, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        proc.stdin.write(prompt)
        proc.stdin.close()
    except Exception as exc:
        raise Halt(f"[{label}] failed to launch claude: {exc}")

    write_current(label)
    start = time.monotonic()
    try:
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        timed_out = False
        try:
            while final is None:
                remaining = timeout_s - (time.monotonic() - start)
                if remaining <= 0:
                    timed_out = True
                    break
                events = sel.select(timeout=min(remaining, 5.0))
                if not events:
                    continue
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = ev.get("type")
                if etype == "rate_limit_event":
                    info = ev.get("rate_limit_info", {})
                    res.rate_limit = info
                    write_usage(info)
                    util = info.get("utilization")
                    if util is not None:
                        w = info.get("rateLimitType", "?")
                        status = info.get("status", "?")
                        log(f"rate-limit event: {w} window at {util:.0%} ({status})")
                        if util >= 0.9:
                            log(f"WARNING: {w} quota window >=90%")
                elif etype == "assistant":
                    msg = ev.get("message") or {}
                    tools = [c.get("name") for c in (msg.get("content") or [])
                             if isinstance(c, dict) and c.get("type") == "tool_use"]
                    if tools:
                        log(f"[{label}] tools: {', '.join(tools)}")
                elif etype == "result":
                    final = ev
        finally:
            if timed_out:
                proc.kill()
            sel.close()

        if timed_out:
            record_segment(label, res, "timeout")
            raise Halt(f"[{label}] segment timed out after {timeout_s}s "
                       f"(transcript: {transcript_path(res.session_id)})")
        if final is None:
            stderr = ""
            try:
                stderr = proc.stderr.read()
            except Exception:
                pass
            proc.wait(timeout=30)
            record_segment(label, res, "halt")
            raise Halt(f"[{label}] no result event (rc={proc.returncode}); "
                       f"stderr tail: {stderr[-500:]}")

        res.session_id = final.get("session_id")
        res.num_turns = final.get("num_turns", 0)
        res.is_error = bool(final.get("is_error"))
        res.result_text = final.get("result") or ""
        usage = final.get("usage") or {}
        res.billed_tokens = billed_tokens(usage)
        res.cache_read_tokens = usage.get("cache_read_input_tokens", 0) or 0
        res.cache_creation_tokens = usage.get("cache_creation_input_tokens", 0) or 0
        res.output_tokens = usage.get("output_tokens", 0) or 0
        res.duration_s = time.monotonic() - start
        res.permission_denials = final.get("permission_denials") or []
        log(f"[{label}] done: turns={res.num_turns} billed={res.billed_tokens:,} "
            f"error={res.is_error} sid={res.session_id}")

        try:
            # Guard: permission denials -> allowlist too narrow
            if res.permission_denials:
                tools = sorted({d.get("tool_name", "?") for d in res.permission_denials})
                raise Halt(f"[{label}] permission denials for {tools} — allowlist needs "
                           f"these rules; halting to avoid silently skipped work "
                           f"(transcript: {transcript_path(res.session_id)})")
            # Guard: rate limit blocked
            if res.is_error and ("usage limit" in res.result_text.lower()
                                 or "rate limit" in res.result_text.lower()):
                resets = (res.rate_limit or {}).get("resetsAt")
                raise RateLimitedHalt(f"[{label}] usage limit hit "
                                      f"(resets epoch: {resets})", resets)
            if res.is_error:
                raise Halt(f"[{label}] segment error: {res.result_text[:400]} "
                           f"(transcript: {transcript_path(res.session_id)})")
            # Guard: token ceiling
            if res.billed_tokens > token_ceiling:
                raise Halt(f"[{label}] billed tokens {res.billed_tokens:,} exceed ceiling "
                           f"{token_ceiling:,} — context likely ballooned "
                           f"(transcript: {transcript_path(res.session_id)})")
            record_segment(label, res, "ok")
            return res
        except Halt as exc:
            record_segment(label, res,
                           "rate_limited" if isinstance(exc, RateLimitedHalt) else "halt")
            raise
    finally:
        remove_current()


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT,
                          capture_output=True, text=True, check=True).stdout.strip()


def run_checks() -> tuple[bool, str]:
    pytest = subprocess.run([str(PROJECT / ".venv" / "bin" / "pytest"), "-q"],
                            cwd=PROJECT, capture_output=True, text=True, timeout=1200)
    if pytest.returncode != 0:
        return False, f"pytest failed:\n{pytest.stdout.strip()[-800:]}"
    mypy = subprocess.run([str(PROJECT / ".venv" / "bin" / "mypy")],
                          cwd=PROJECT, capture_output=True, text=True, timeout=1200)
    if mypy.returncode != 0:
        return False, f"mypy failed:\n{mypy.stdout.strip()[-800:]}"
    return True, pytest.stdout.strip()[-300:]


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    raise SystemExit("No build-state.json. Start with: "
                     "python scripts/orchestrate_build.py --phase <N>")


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def pause(semi_attended: bool, msg: str) -> None:
    if not semi_attended:
        return
    try:
        input(f"\n>>> {msg}\n>>> Press Enter to continue, Ctrl+C to stop...")
    except KeyboardInterrupt:
        raise Halt("user stopped the runner")


def diagnose(res: SegmentResult) -> str:
    return ("Segment halted. Transcript: "
            f"{transcript_path(res.session_id)}\n"
            "To diagnose: ask opencode to analyze this jsonl (usage pattern, "
            "protocol violations, last assistant message).")


def sleep_until_reset(resets_at: float | None) -> None:
    if resets_at:
        wait = max(60.0, resets_at - time.time()) + RATE_LIMIT_SLEEP_BUFFER_S
        log(f"sleeping {int(wait) // 60}m {int(wait) % 60}s until "
            f"rate-limit window resets...")
        time.sleep(wait)
    else:
        log("no resetsAt timestamp; sleeping 30 min and retrying")
        time.sleep(1800)


def run_phase_flow(args, state: dict) -> None:
    semi = not args.auto
    phase = state["phase"]

    while True:
        if state["status"] == "planning":
            plan_path = PLAN_DIR / f"phase{phase}-plan.md"
            if plan_path.exists():
                try:
                    cps = parse_checkpoints(plan_path)
                    log(f"plan already exists ({plan_path.name}); "
                        f"checkpoints: {cps}")
                    state["plan"] = str(plan_path)
                    state["status"] = "building"
                    save_state(state)
                except Halt:
                    log(f"existing {plan_path.name} has no checkpoints; "
                        f"rewriting it")
            elif args.dry_run:
                pass

            if state["status"] == "planning":
                res = run_segment(PLAN_PROMPT.format(phase=phase),
                                  model=args.model, max_turns=args.max_turns,
                                  token_ceiling=args.token_ceiling,
                                  timeout_s=args.timeout, dry_run=args.dry_run,
                                  label=f"phase{phase} plan")
                if not args.dry_run:
                    if not plan_path.exists():
                        raise Halt(f"plan file was not created: {plan_path}\n"
                                   f"{diagnose(res)}")
                    cps = parse_checkpoints(plan_path)
                    state["plan"] = str(plan_path)
                    state["status"] = "building"
                    save_state(state)
                    log(f"plan written; checkpoints: {cps}")
                    pause(semi, "plan written — review it, then Enter to start building")
            if args.dry_run:
                return

        if state["status"] == "building":
            plan_path = Path(state["plan"])
            cps = parse_checkpoints(plan_path)
            done = state.get("checkpoints_done", [])
            head_before = git_head()
            for cp in cps:
                if cp in done:
                    continue
                template = NEXT_CKPT_PROMPT if done else FIRST_CKPT_PROMPT
                res = run_segment(template.format(phase=phase, cp=cp),
                                  model=args.model, max_turns=args.max_turns,
                                  token_ceiling=args.token_ceiling,
                                  timeout_s=args.timeout, dry_run=args.dry_run,
                                  label=f"phase{phase} {cp}")
                if args.dry_run:
                    return

                head_after = git_head()
                if head_after == head_before:
                    log(f"WARNING [{cp}]: no new commit after segment")
                ok, output = run_checks()
                if not ok:
                    log(f"[{cp}] checks failed; launching one repair segment")
                    repair = run_segment(REPAIR_PROMPT.format(phase=phase, output=output),
                                         model=args.model, max_turns=args.max_turns,
                                         token_ceiling=args.token_ceiling,
                                         timeout_s=args.timeout, dry_run=False,
                                         label=f"phase{phase} {cp} repair")
                    ok, _ = run_checks()
                    if not ok:
                        raise Halt(f"[{cp}] verification still failing after "
                                   f"repair\n{diagnose(repair)}")
                done.append(cp)
                state["checkpoints_done"] = done
                state["checkpoint"] = cp
                save_state(state)
                log(f"checkpoint {cp} verified")
                pause(semi, f"checkpoint {cp} complete ({res.num_turns} turns, "
                            f"{res.billed_tokens:,} billed tokens)")
                head_before = git_head()
            state["status"] = "phase_done"
            state.setdefault("completed_phases", []).append(phase)
            save_state(state)
            log(f"Phase {phase} complete")

        if state["status"] == "phase_done":
            nxt = state.get("next_phase", phase + 1)
            pause(semi, f"Phase {phase} done; next: Phase {nxt} "
                        f"(plan-writing session)")
            log(f"--- advancing to phase {nxt} (new state) ---")
            save_state({"phase": nxt, "checkpoint": None, "status": "planning",
                        "completed_phases": state.get("completed_phases", [])})
            state = load_state()
            phase = state["phase"]


def main() -> None:
    ap = argparse.ArgumentParser(description="TEIC build orchestrator")
    ap.add_argument("--phase", type=int, help="phase to build")
    ap.add_argument("--auto", action="store_true",
                    help="unattended (sleep across rate-limit windows)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    ap.add_argument("--token-ceiling", type=int, default=DEFAULT_TOKEN_CEILING)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        print(STATE_FILE.read_text() if STATE_FILE.exists() else "no state file")
        return

    if not args.phase:
        ap.error("--phase N required (unless --status)")

    # (Re)initialize state for the requested phase, preserving history.
    prev_completed = []
    if STATE_FILE.exists():
        old = json.loads(STATE_FILE.read_text())
        prev_completed = old.get("completed_phases", [])
        if old.get("phase") == args.phase and not args.dry_run:
            log(f"resuming phase {args.phase} from state: "
                f"status={old.get('status')} checkpoint={old.get('checkpoint')} "
                f"done={old.get('checkpoints_done', [])}")
    state = {"phase": args.phase, "checkpoint": None, "status": "planning",
             "completed_phases": prev_completed}
    if STATE_FILE.exists():
        old = json.loads(STATE_FILE.read_text())
        if old.get("phase") == args.phase:
            state = old
    save_state(state)

    while True:
        try:
            run_phase_flow(args, state)
            return
        except RateLimitedHalt as exc:
            if args.auto:
                log(str(exc))
                sleep_until_reset(exc.resets_at)
                log("retrying after rate-limit reset...")
                continue
            raise


if __name__ == "__main__":
    try:
        main()
    except RateLimitedHalt as exc:
        log(str(exc))
        log("Usage limit reached. Re-run the same command after your window "
            "resets (or use --auto to sleep until reset automatically).")
        sys.exit(3)
    except Halt as exc:
        log(f"HALT: {exc}")
        sys.exit(2)
    except KeyboardInterrupt:
        log("interrupted; state saved in build-state.json — re-run to resume")
        sys.exit(130)
