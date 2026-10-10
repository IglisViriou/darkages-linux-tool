#!./venv/bin/python

import asyncio
from typing import Any
from collections.abc import Coroutine
import threading
import subprocess
import os
import curses
import locale
import argparse
from state import state
import input_hub
from features import butterwalk, spacebar, controller, hotkeys
from features.macro import MacroFeature, load_macros
from ui.tabs import draw_ui
from ui import theme


async def get_darkages_window_info() -> tuple[str | None, str]:
    try:
        proc1 = await asyncio.create_subprocess_exec(
            "xdotool", "getactivewindow",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        wid_out, _ = await proc1.communicate()
        wid = wid_out.decode().strip()

        proc2 = await asyncio.create_subprocess_exec(
            "xdotool", "getwindowname", wid,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        name_out, _ = await proc2.communicate()
        name = name_out.decode().strip()
        
        return wid, name
    except Exception:
        return None, "Not Found"


async def focus_monitor() -> None:
    while state["running"]:
        if not state.get("macro_playing"):
            wid, name = await get_darkages_window_info()
            state["active_window_id"] = wid
            state["client_name"] = name or "Not Found"
            if name:
                state["active"] = any(x.lower() == name.lower() for x in state["window_hooks"])
            else:
                state["active"] = False
        await asyncio.sleep(0.5)


async def main_async(macro_feature: MacroFeature) -> None:
    input_hub.setup_devices()
    input_hub.register(butterwalk.on_key_event)
    input_hub.register(hotkeys.on_key_event)
    input_hub.register(macro_feature.on_key_event)

    tasks: list[asyncio.Future[Any] | Coroutine[Any, Any, Any]] = list(
        input_hub.get_read_tasks()
    )
    tasks.append(butterwalk.injection_loop())
    tasks.append(spacebar.injection_loop())
    tasks.append(controller.injection_loop())
    tasks.append(macro_feature.hold_loop())
    tasks.append(focus_monitor())
    try:
        _ = await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass


def main(use_gui: bool = True) -> None:
    load_macros()
    macro_feature = MacroFeature()

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def run_loop() -> None:
        try:
            loop.run_until_complete(main_async(macro_feature))
        except (asyncio.CancelledError, RuntimeError):
            pass
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t: threading.Thread = threading.Thread(
        target=run_loop,
        daemon=True,
    )
    t.start()

    if use_gui:
        try:
            from gui.app import run_gui
            run_gui(macro_feature, loop)
        except ImportError:
            print("CustomTkinter not found, falling back to TUI...")
            curses.wrapper(lambda stdscr: main_tui(stdscr, macro_feature, loop))
    else:
        curses.wrapper(lambda stdscr: main_tui(stdscr, macro_feature, loop))

    state["running"] = False

    def _shutdown() -> None:
        for task in asyncio.all_tasks(loop):
            task.cancel()

    if loop.is_running():
        loop.call_soon_threadsafe(_shutdown)

    t.join(timeout=1.0)
    input_hub.cleanup_devices()


def main_tui(stdscr: curses.window, macro_feature: MacroFeature, loop: asyncio.AbstractEventLoop) -> None:
    _ = locale.setlocale(locale.LC_ALL, "")
    theme.init()
    draw_ui(stdscr, macro_feature)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DarkAges Linux Tool")
    parser.add_argument("--tui", action="store_true", help="Run in TUI mode")
    args = parser.parse_args()

    if not os.access("/dev/input/event0", os.R_OK):
        print(
            "ERROR: Permission denied for /dev/input/. Run 'sudo ./setup_permissions.sh' first."
        )
    else:
        main(use_gui=not args.tui)
