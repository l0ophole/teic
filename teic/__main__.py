from __future__ import annotations

import asyncio
import signal
import sys

from teic.daemon import TeicDaemon
from teic.settings import load_settings


async def _main() -> None:
    settings = load_settings()
    daemon = TeicDaemon(settings)
    await daemon.start()
    print(f"TEIC-Agent daemon started. session_id={daemon.session_id}")

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    run_task = asyncio.create_task(daemon.run())
    await stop_event.wait()
    print("Shutting down...")
    await daemon.stop()
    run_task.cancel()


def main() -> None:
    if "--tui" in sys.argv:
        from teic.interface.terminal.app import TeicApp

        TeicApp().run()
        return
    asyncio.run(_main())


if __name__ == "__main__":
    main()
