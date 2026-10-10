from __future__ import annotations
import asyncio
from state import state
import injector


CONTROLLER_KEY_MAP: dict[str, str] = {
    # DPAD
    "BTN_DPAD_LEFT": "Left",
    "BTN_DPAD_RIGHT": "Right",
    "BTN_DPAD_UP": "Up",
    "BTN_DPAD_DOWN": "Down",
    # Joysticks / Left Thumbstick
    "BTN_JOY_LX_NEG": "Left",
    "BTN_JOY_LX_POS": "Right",
    "BTN_JOY_LY_NEG": "Up",
    "BTN_JOY_LY_POS": "Down",
}


async def injection_loop() -> None:
    """Continuous injection loop for Controller Inputs and Right Stick Mouse Control."""
    acc_x = 0.0
    acc_y = 0.0

    while state["running"]:
        if state["controller_enabled"] and state["active"]:
            # 1. Directional Movement (DPAD & Left Thumbstick)
            if state["physical_keys_down"]:
                active_targets: set[str] = set()
                for k in state["physical_keys_down"]:
                    if k in CONTROLLER_KEY_MAP:
                        if k.startswith("BTN_DPAD_") and not state["dpad_enabled"]:
                            continue
                        if k.startswith("BTN_JOY_") and not state["joystick_enabled"]:
                            continue
                        active_targets.add(CONTROLLER_KEY_MAP[k])

                if active_targets:
                    multiplier = state["multiplier"] if state["butterwalk"] else 1
                    for target in active_targets:
                        for _ in range(multiplier):
                            await injector.key(target)

            # 2. Right Analog Stick -> Mouse Cursor Movement
            if state.get("right_stick_mouse_enabled", False):
                rx = state.get("right_stick_x", 0.0)
                ry = state.get("right_stick_y", 0.0)
                if rx != 0.0 or ry != 0.0:
                    # Quadratic response curve for precision near center
                    tilt_x = rx * abs(rx)
                    tilt_y = ry * abs(ry)

                    # Sensitivity: 1% to 100% of hardware mouse DPI settings
                    sens_percent = max(1, min(100, state.get("mouse_sensitivity", 50)))
                    base_dpi = max(100, state.get("mouse_dpi", 1600))
                    interval = state.get("loop_interval", 0.01)

                    speed_scale = (sens_percent / 100.0) * (base_dpi * interval)

                    acc_x += tilt_x * speed_scale
                    acc_y += tilt_y * speed_scale

                    dx = int(acc_x)
                    dy = int(acc_y)
                    acc_x -= dx
                    acc_y -= dy

                    if dx != 0 or dy != 0:
                        await injector.mouse_move_relative(dx, dy)
                else:
                    acc_x = 0.0
                    acc_y = 0.0
            else:
                acc_x = 0.0
                acc_y = 0.0
        else:
            acc_x = 0.0
            acc_y = 0.0
            await asyncio.sleep(0.05)
            continue

        await asyncio.sleep(state["loop_interval"])
