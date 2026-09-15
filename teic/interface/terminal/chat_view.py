"""Phase 9 cp2: streaming chat pane.

Renders user messages, agent responses streamed token-by-token as they
arrive from `TeicDaemon`'s `set_response_chunk_handler()` seam, and inline
system/notification lines -- all in one scrolling transcript, per
`phase9-plan.md`'s "Notifications... render as inline system-style lines
in the same pane (not a separate channel)" decision.

A `Static` widget can't append text in place, so each in-progress agent
turn gets its own mounted `Static` that `stream_chunk()` re-`update()`s as
chunks arrive, rather than trying to grow a single `RichLog` line.
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

_AGENT_PREFIX = "[bold green]agent>[/bold green] "


class ChatView(VerticalScroll):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._current_assistant: Static | None = None
        self._current_text = ""

    async def add_user_message(self, text: str) -> None:
        await self.mount(Static(f"[bold cyan]you>[/bold cyan] {text}"))
        self.scroll_end(animate=False)

    async def add_system_message(self, text: str) -> None:
        await self.mount(Static(f"[dim yellow]* {text}[/dim yellow]"))
        self.scroll_end(animate=False)

    async def stream_chunk(self, chunk: str) -> None:
        if self._current_assistant is None:
            self._current_text = ""
            self._current_assistant = Static(_AGENT_PREFIX)
            await self.mount(self._current_assistant)
        self._current_text += chunk
        self._current_assistant.update(_AGENT_PREFIX + self._current_text)
        self.scroll_end(animate=False)

    def end_streaming_turn(self) -> None:
        """Called once per tick (from the `TickSnapshot` listener) to close
        out whatever assistant turn just finished -- a full ignited send
        always completes within the one tick it started in."""
        self._current_assistant = None
        self._current_text = ""

    @property
    def is_streaming(self) -> bool:
        return self._current_assistant is not None

    async def clear(self) -> None:
        await self.remove_children()
        self.end_streaming_turn()
