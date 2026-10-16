from __future__ import annotations
import asyncio
import time
from typing import Callable, Any
from state import state, ControllerBinding
import injector


CONTROLLER_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Movement & Sticks",
        [
            ("BTN_JOY_LY_NEG", "Left Stick Up"),
            ("BTN_JOY_LY_POS", "Left Stick Down"),
            ("BTN_JOY_LX_NEG", "Left Stick Left"),
            ("BTN_JOY_LX_POS", "Left Stick Right"),
            ("BTN_DPAD_UP", "DPAD Up"),
            ("BTN_DPAD_DOWN", "DPAD Down"),
            ("BTN_DPAD_LEFT", "DPAD Left"),
            ("BTN_DPAD_RIGHT", "DPAD Right"),
            ("BTN_THUMBL", "L3 (Left Stick Click)"),
            ("BTN_THUMBR", "R3 (Right Stick Click)"),
            ("BTN_JOY_RY_NEG", "Right Stick Up (No Mouse)"),
            ("BTN_JOY_RY_POS", "Right Stick Down (No Mouse)"),
            ("BTN_JOY_RX_NEG", "Right Stick Left (No Mouse)"),
            ("BTN_JOY_RX_POS", "Right Stick Right (No Mouse)"),
        ],
    ),
    (
        "Face Buttons",
        [
            ("BTN_SOUTH", "A / Cross (South)"),
            ("BTN_EAST", "B / Circle (East)"),
            ("BTN_WEST", "X / Square (West)"),
            ("BTN_NORTH", "Y / Triangle (North)"),
        ],
    ),
    (
        "Bumpers & Triggers",
        [
            ("BTN_TL", "L1 / LB (Left Bumper)"),
            ("BTN_TR", "R1 / RB (Right Bumper)"),
            ("BTN_L2", "L2 / LT (Left Trigger)"),
            ("BTN_R2", "R2 / RT (Right Trigger)"),
        ],
    ),
    (
        "Center Buttons",
        [
            ("BTN_SELECT", "Select / Back / Share"),
            ("BTN_START", "Start / Options"),
            ("BTN_MODE", "Guide / Home"),
        ],
    ),
]

CONTROLLER_INPUT_LABELS: dict[str, str] = {
    code: label
    for _, items in CONTROLLER_GROUPS
    for code, label in items
}

MOUSE_ACTION_LABELS: dict[str, str] = {
    "left_click": "Left Click",
    "right_click": "Right Click",
    "middle_click": "Middle Click",
    "scroll_up": "Scroll Up",
    "scroll_down": "Scroll Down",
}

MOUSE_BUTTON_CODES: dict[str, int] = {
    "left_click": 1,
    "middle_click": 2,
    "right_click": 3,
}

_macro_runner: Callable[[dict[str, Any]], None] | None = None


def set_macro_runner(runner: Callable[[dict[str, Any]], None]) -> None:
    global _macro_runner
    _macro_runner = runner


def format_binding(binding: ControllerBinding | dict[str, Any] | None) -> str:
    if not binding:
        return "Unbound"
    kind = binding.get("kind", "none")
    val = str(binding.get("value", ""))
    if kind == "none" or (kind != "layer_hold" and not val):
        return "Unbound"
    if kind == "layer_hold":
        return "Modifier Layer (Hold)"
    if kind == "mouse":
        return f"Mouse: {MOUSE_ACTION_LABELS.get(val, val)}"
    if kind == "macro":
        for m in state.get("macros", []):
            if m.get("id") == val or m.get("name") == val:
                return f"Macro: {m.get('name', val)}"
        return f"Macro: {val}"
    return f"Key: {val}"


def is_layer_active() -> bool:
    if not state.get("controller_enabled"):
        return False
    base_map = state.get("controller_bindings", {})
    for k in list(state.get("physical_keys_down", set())):
        b = base_map.get(k)
        if b and b.get("kind") == "layer_hold":
            return True
    return False


def should_suppress_macro_for_controller(key_name: str) -> bool:
    """Return True if a controller button event is currently consumed by the active Modifier Layer."""
    if not key_name.startswith("BTN_"):
        return False
    if not is_layer_active():
        return False
    layer_map = state.get("controller_layer_bindings", {})
    b = layer_map.get(key_name)
    return bool(b and b.get("kind", "none") != "none")


def _has_direct_enabled_macro(btn_name: str) -> bool:
    for m in state.get("macros", []):
        if m.get("enabled", True) and m.get("trigger") == btn_name:
            return True
    return False


async def _release_held_state(held_keys: set[str], held_mouse: set[int]) -> None:
    for k in list(held_keys):
        await injector.key_up(k)
    held_keys.clear()
    for b in list(held_mouse):
        await injector.mouse_up(b)
    held_mouse.clear()


async def injection_loop() -> None:
    """Continuous injection loop for Controller Inputs, Button/Layer Remapping, and Right Stick Mouse Control."""
    acc_x = 0.0
    acc_y = 0.0
    held_keys: set[str] = set()
    held_mouse: set[int] = set()
    prev_macro_buttons: set[str] = set()
    last_butterwalk_time = 0.0
    last_space_time = 0.0
    last_scroll_time = 0.0

    try:
        while state["running"]:
            if state["controller_enabled"] and state["active"]:
                keys_down = list(state["physical_keys_down"])
                layer_on = is_layer_active()
                base_map = state.get("controller_bindings", {})
                layer_map = state.get("controller_layer_bindings", {})

                desired_keys: set[str] = set()
                desired_mouse: set[int] = set()
                butterwalk_targets: set[str] = set()
                space_pulse_active = False
                scroll_dir = 0
                current_macro_buttons: set[str] = set()

                for k in keys_down:
                    if not k.startswith("BTN_"):
                        continue
                    if k.startswith("BTN_DPAD_") and not state["dpad_enabled"]:
                        continue
                    if k.startswith("BTN_JOY_L") and not state["joystick_enabled"]:
                        continue
                    if k.startswith("BTN_JOY_R") and state.get("right_stick_mouse_enabled", False):
                        continue

                    base_binding = base_map.get(k)
                    if base_binding and base_binding.get("kind") == "layer_hold":
                        continue

                    # Determine effective binding (Modifier Layer overrides Base Layer when held)
                    effective: ControllerBinding | None = None
                    if layer_on:
                        lb = layer_map.get(k)
                        if lb and lb.get("kind", "none") != "none":
                            effective = lb
                    if effective is None:
                        # If a user created a direct macro on this controller button in the Macros tab
                        # and the Modifier Layer is not overriding it, let MacroFeature handle it.
                        if _has_direct_enabled_macro(k):
                            continue
                        effective = base_binding

                    if not effective:
                        continue

                    kind = effective.get("kind", "none")
                    val = str(effective.get("value", "")).strip()
                    if kind == "none" or not val:
                        continue

                    if kind == "key":
                        if val in ("Left", "Right", "Up", "Down") and state["butterwalk"]:
                            butterwalk_targets.add(val)
                        elif val.lower() == "space" and state.get("space_enabled", False):
                            space_pulse_active = True
                        else:
                            desired_keys.add(val)

                    elif kind == "mouse":
                        if val in MOUSE_BUTTON_CODES:
                            desired_mouse.add(MOUSE_BUTTON_CODES[val])
                        elif val == "scroll_up":
                            scroll_dir = 1
                        elif val == "scroll_down":
                            scroll_dir = -1

                    elif kind == "macro":
                        current_macro_buttons.add(k)
                        target_macro = next(
                            (m for m in state.get("macros", []) if m.get("id") == val or m.get("name") == val),
                            None,
                        )
                        if target_macro and target_macro.get("enabled", True) and _macro_runner is not None:
                            is_hold = target_macro.get("trigger_mode", "once") == "hold"
                            if is_hold or k not in prev_macro_buttons:
                                _macro_runner(target_macro)

                prev_macro_buttons = current_macro_buttons

                # Release any keys or mouse buttons no longer held
                for k in list(held_keys - desired_keys):
                    await injector.key_up(k)
                    held_keys.discard(k)

                for b in list(held_mouse - desired_mouse):
                    await injector.mouse_up(b)
                    held_mouse.discard(b)

                # Press newly held keys and mouse buttons
                for k in desired_keys - held_keys:
                    await injector.key_down(k)
                    held_keys.add(k)

                for b in desired_mouse - held_mouse:
                    await injector.mouse_down(b)
                    held_mouse.add(b)

                # Pulse Butterwalk directional targets when Butterwalk is enabled
                now = time.monotonic()
                if butterwalk_targets:
                    bw_delay = max(1, min(100, state.get("butterwalk_delay_ms", 10))) / 1000.0
                    if now - last_butterwalk_time >= bw_delay:
                        for target in butterwalk_targets:
                            for _ in range(state["multiplier"]):
                                await injector.key(target)
                        last_butterwalk_time = time.monotonic()

                # Pulse Spacebar when Continuous Assail is enabled and a controller button mapped to space is held
                if space_pulse_active:
                    sp_delay = max(1, min(100, state.get("space_delay_ms", 10))) / 1000.0
                    if now - last_space_time >= sp_delay:
                        for _ in range(state.get("space_multiplier", 1)):
                            await injector.key("space")
                        last_space_time = time.monotonic()

                # Pulse Scroll Wheel if bound and held
                if scroll_dir != 0 and now - last_scroll_time >= 0.08:
                    await injector.mouse_scroll(scroll_dir)
                    last_scroll_time = time.monotonic()

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
                if held_keys or held_mouse:
                    await _release_held_state(held_keys, held_mouse)
                prev_macro_buttons.clear()
                acc_x = 0.0
                acc_y = 0.0
                await asyncio.sleep(0.05)
                continue

            await asyncio.sleep(state["loop_interval"])
    finally:
        if held_keys or held_mouse:
            await _release_held_state(held_keys, held_mouse)

