from __future__ import annotations
import asyncio
from evdev.events import InputEvent
from state import state
import injector


KEY_MAP: dict[str, str] = {
    "KEY_LEFT": "Left",
    "KEY_RIGHT": "Right",
    "KEY_UP": "Up",
    "KEY_DOWN": "Down",
    "KEY_Z": "Left",
    "KEY_X": "Down",
    "KEY_C": "Up",
    "KEY_V": "Right",
}


def on_key_event(event: InputEvent, key_name: str) -> None:
    if event.value == 1:
        state["physical_keys_down"].add(key_name)
    elif event.value == 0:
        state["physical_keys_down"].discard(key_name)


async def injection_loop() -> None:
    while state["running"]:
        if state["butterwalk"] and state["active"] and state["physical_keys_down"]:
            active_targets: set[str] = set()
            for k in state["physical_keys_down"]:
                # Check physical arrow/zxcv keys
                if k in KEY_MAP:
                    if (
                        k in ("KEY_Z", "KEY_X", "KEY_C", "KEY_V")
                        and not state["zxcv_enabled"]
                    ):
                        continue
                    active_targets.add(KEY_MAP[k])
                
                # Check keybinds for virtual arrow keys
                for macro in state["macros"]:
                    if (
                        macro.get("enabled", True)
                        and macro.get("kind") == "keybind"
                        and macro["trigger"] == k
                    ):
                        if macro["steps"]:
                            val = macro["steps"][0]["value"]
                            valid_targets = ["Left", "Right", "Up", "Down"]
                            if val in valid_targets:
                                active_targets.add(val)

            if active_targets:
                for target in active_targets:
                    for _ in range(state["multiplier"]):
                        await injector.key(target)
                delay = max(1, min(100, state.get("butterwalk_delay_ms", 10))) / 1000.0
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.05)

