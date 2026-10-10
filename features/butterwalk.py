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

    if event.value == 1:
        if key_name in ("KEY_KPMINUS", "KEY_MINUS"):
            state["multiplier"] = max(1, state["multiplier"] - 1)
        elif key_name in ("KEY_KPPLUS", "KEY_EQUAL"):
            state["multiplier"] = min(5, state["multiplier"] + 1)


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

            for target in active_targets:
                for _ in range(state["multiplier"]):
                    await injector.key(target)

        await asyncio.sleep(state["loop_interval"])

