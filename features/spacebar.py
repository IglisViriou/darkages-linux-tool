from __future__ import annotations
import asyncio
from state import state
import injector


async def injection_loop() -> None:
    """Continuous injection loop for Spacebar Uninterrupted Repeat."""
    while state["running"]:
        if state["space_enabled"] and state["active"] and state["physical_keys_down"]:
            should_repeat = False

            # Check physical Space key
            if "KEY_SPACE" in state["physical_keys_down"]:
                should_repeat = True
            else:
                # Check keybinds configured to output Space
                for macro in state["macros"]:
                    if (
                        macro.get("enabled", True)
                        and macro.get("kind") == "keybind"
                        and macro.get("trigger") in state["physical_keys_down"]
                    ):
                        if macro.get("steps") and macro["steps"][0].get("value") == "space":
                            should_repeat = True
                            break

            if should_repeat:
                multiplier = state.get("space_multiplier", 1)
                for _ in range(multiplier):
                    await injector.key("space")

        await asyncio.sleep(state["loop_interval"])
