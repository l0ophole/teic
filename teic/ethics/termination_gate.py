"""Phase 6 cp2: the single authorized path to actual daemon termination.

`fire()` refuses unless both `ViabilitySettings.allow_actual_termination` is
True and `termination_justification` is a non-empty string -- the two-key
config gate the Ethics Requirements demand. On a successful fire, it writes
a permanent `log_event` row via `teic.persistence.log_sink.LogSink` *before*
signalling the daemon to halt, so the termination is never silent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from teic.models.log_event import LogEvent
from teic.persistence.log_sink import LogSink
from teic.settings import ViabilitySettings


class TerminationRefused(Exception):
    """Raised when fire() is called without both config keys set."""


class TerminationGate:
    def __init__(self, settings: ViabilitySettings, log_sink: LogSink) -> None:
        self._settings = settings
        self._log_sink = log_sink

    async def fire(self, session_id: str, tick_id: int, reason: str) -> None:
        """Attempt termination. Raises TerminationRefused and writes nothing
        if the settings gate isn't fully configured. Never called from the
        tick loop directly on reserve == 0 -- the caller decides whether
        zero reserve warrants invoking this."""
        if not self._settings.allow_actual_termination or not self._settings.termination_justification:
            raise TerminationRefused(
                "termination refused: allow_actual_termination and "
                "termination_justification must both be set"
            )
        await self._log_sink.emit(
            LogEvent(
                session_id=session_id,
                tick_id=tick_id,
                ts=datetime.now(timezone.utc),
                level="WARN",
                subsystem="ethics.termination_gate",
                event_type="termination_fired",
                payload={
                    "justification": self._settings.termination_justification,
                    "reason": reason,
                },
            )
        )
