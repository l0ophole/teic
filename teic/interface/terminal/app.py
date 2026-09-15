"""Phase 9 cp2: terminal TUI core.

Owns a `TeicDaemon`, runs its real tick loop (`daemon.run()`, the same
method `teic/__main__.py`'s headless path uses -- not `run_n_ticks()`,
which is a test-only convenience) as a background asyncio task alongside
the Textual event loop, and wires the daemon's `TickSnapshot`/response-
chunk observer seams into the chat/status/log widgets.
"""

from __future__ import annotations

import asyncio
import contextlib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

from teic.daemon import TeicDaemon, TickSnapshot
from teic.interface.terminal import controls
from teic.interface.terminal.chat_view import ChatView
from teic.interface.terminal.controls import ControlsBar
from teic.interface.terminal.log_view import LogView
from teic.interface.terminal.status_panel import StatusPanel
from teic.settings import Settings, load_settings

CSS = """
Screen {
    layout: vertical;
}
#body {
    layout: horizontal;
    height: 1fr;
}
StatusPanel {
    width: 34;
    border: solid $accent;
    padding: 0 1;
}
#main-col {
    width: 1fr;
    layout: vertical;
}
ChatView {
    height: 2fr;
    border: solid $primary;
}
LogView {
    height: 1fr;
    border: solid $secondary;
}
ControlsBar {
    height: 1;
    dock: bottom;
}
"""


class TeicApp(App[None]):
    CSS = CSS
    BINDINGS = [
        Binding(controls.PAUSE_RESUME_KEY, "toggle_pause", "Pause/Resume"),
        Binding(controls.RESET_KEY, "reset_session", "Reset session"),
        Binding(controls.QUIT_KEY, "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._settings = settings if settings is not None else load_settings()
        self.daemon = TeicDaemon(self._settings)
        self._run_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            yield StatusPanel(id="status-panel")
            with Vertical(id="main-col"):
                yield ChatView(id="chat-view")
                yield LogView(self._settings.interface.tui_log_tail_rows, id="log-view")
        yield Input(placeholder="Type a message and press Enter...", id="chat-input")
        yield ControlsBar(id="controls-bar")
        yield Footer()

    async def on_mount(self) -> None:
        await self._start_daemon()
        self.set_interval(1.0, self._poll_logs)
        self.query_one("#chat-input", Input).focus()

    async def _start_daemon(self) -> None:
        await self.daemon.start()
        self.daemon.add_tick_listener(self._on_tick_snapshot)
        self.daemon.set_response_chunk_handler(self._on_response_chunk)
        self._run_task = asyncio.create_task(self.daemon.run())

    async def _stop_daemon(self) -> None:
        if self._run_task is not None:
            self._run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._run_task
            self._run_task = None
        if self.daemon.is_running:
            await self.daemon.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        chat_view = self.query_one(ChatView)
        await chat_view.add_user_message(text)
        await self.daemon.submit_user_message(text)

    async def _on_response_chunk(self, chunk: str) -> None:
        await self.query_one(ChatView).stream_chunk(chunk)

    async def _on_tick_snapshot(self, snapshot: TickSnapshot) -> None:
        self.query_one(StatusPanel).update_snapshot(snapshot)
        chat_view = self.query_one(ChatView)
        if chat_view.is_streaming:
            chat_view.end_streaming_turn()

    async def on_unmount(self) -> None:
        await self._stop_daemon()

    async def _poll_logs(self) -> None:
        if not self.daemon.is_running:
            return
        await self.query_one(LogView).poll(self.daemon.conn, self.daemon.session_id)

    def action_toggle_pause(self) -> None:
        if self.daemon.paused:
            self.daemon.resume()
        else:
            self.daemon.pause()
        self.query_one(ControlsBar).set_paused(self.daemon.paused)

    async def action_reset_session(self) -> None:
        await self._stop_daemon()
        self.daemon = TeicDaemon(self._settings)
        await self._start_daemon()
        chat_view = self.query_one(ChatView)
        await chat_view.clear()
        self.query_one(StatusPanel).reset()
        self.query_one(LogView).reset()
        self.query_one(ControlsBar).set_paused(False)
        await chat_view.add_system_message(f"session reset: {self.daemon.session_id}")

    async def action_quit(self) -> None:
        await self._stop_daemon()
        self.exit()


def main() -> None:
    TeicApp().run()


if __name__ == "__main__":
    main()
