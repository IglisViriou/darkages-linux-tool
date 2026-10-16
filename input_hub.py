from __future__ import annotations
import asyncio
from typing import Callable, Any
from collections.abc import Coroutine
import evdev
from evdev import ecodes, InputDevice, UInput
from evdev.events import InputEvent

EventCallback = Callable[[InputEvent, str], None]

_callbacks: list[EventCallback] = []
_keyboards: list[InputDevice[str]] = []
_mice: list[InputDevice[str]] = []
_controllers: list[InputDevice[str]] = []
_active_device_paths: set[str] = set()
_uinput: UInput | None = None

# Canonical gamepad EV_KEY code mapping across Xbox, PlayStation, Switch, and generic controllers
_GAMEPAD_CODE_MAP: dict[int, str] = {
    ecodes.BTN_SOUTH: "BTN_SOUTH",
    ecodes.BTN_EAST: "BTN_EAST",
    ecodes.BTN_NORTH: "BTN_NORTH",
    ecodes.BTN_WEST: "BTN_WEST",
    ecodes.BTN_TL: "BTN_TL",
    ecodes.BTN_TR: "BTN_TR",
    ecodes.BTN_TL2: "BTN_L2",
    ecodes.BTN_TR2: "BTN_R2",
    ecodes.BTN_SELECT: "BTN_SELECT",
    ecodes.BTN_START: "BTN_START",
    ecodes.BTN_MODE: "BTN_MODE",
    ecodes.BTN_THUMBL: "BTN_THUMBL",
    ecodes.BTN_THUMBR: "BTN_THUMBR",
    getattr(ecodes, "BTN_DPAD_UP", 544): "BTN_DPAD_UP",
    getattr(ecodes, "BTN_DPAD_DOWN", 545): "BTN_DPAD_DOWN",
    getattr(ecodes, "BTN_DPAD_LEFT", 546): "BTN_DPAD_LEFT",
    getattr(ecodes, "BTN_DPAD_RIGHT", 547): "BTN_DPAD_RIGHT",
    # Direct trigger / generic joystick button fallbacks
    ecodes.BTN_C: "BTN_C",
    ecodes.BTN_Z: "BTN_Z",
}

_CONTROLLER_KEY_CODES: set[int] = set(_GAMEPAD_CODE_MAP.keys()) | {
    getattr(ecodes, "BTN_GAMEPAD", 304),
    getattr(ecodes, "BTN_JOYSTICK", 288),
}


def register(cb: EventCallback) -> None:
    _callbacks.append(cb)


def _normalize_key_name(code: int) -> str | None:
    if code in _GAMEPAD_CODE_MAP:
        return _GAMEPAD_CODE_MAP[code]

    try:
        names = ecodes.lookup(code, (ecodes.EV_KEY,))
        if names:
            return names[0] if isinstance(names[0], str) else names[0][0]
    except Exception:
        pass
    
    try:
        raw = ecodes.KEY[code]
        return raw if isinstance(raw, str) else raw[0]
    except (KeyError, IndexError, TypeError):
        pass
        
    return f"CODE_{code}"


def _fire_callbacks(event: InputEvent, key_name: str, device_name: str = "Unknown", value_override: int | None = None) -> None:
    from state import state
    val = value_override if value_override is not None else event.value
    type_code = getattr(event, 'type', ecodes.EV_KEY)
    type_name = ecodes.EV[type_code] if type_code in ecodes.EV else str(type_code)
    state["last_event"] = f"[{type_name}] {key_name} ({device_name})"
    
    # Record last pressed controller input for interactive UI highlighting/binding
    if key_name.startswith("BTN_") and key_name not in ("BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE"):
        if val == 1:
            state["last_controller_input"] = key_name
            if state.get("listening_for_controller_input"):
                state["captured_controller_input"] = key_name
                state["listening_for_controller_input"] = False

    # We allow EV_KEY and specifically mapped EV_ABS (pseudo-keys)
    # callbacks like MacroFeature.on_key_event check event.value
    for cb in _callbacks:
        try:
            if value_override is not None:
                # Create a minimal proxy object that has the expected attributes
                class MappedEvent:
                    def __init__(self, t, c, v):
                        self.type = t
                        self.code = c
                        self.value = v
                cb(MappedEvent(type_code, getattr(event, 'code', 0), val), key_name)
            else:
                cb(event, key_name)
        except Exception:
            pass


def _classify_and_add_device(d: InputDevice[str]) -> bool:
    """Classify an evdev InputDevice into _controllers, _mice, or _keyboards. Returns True if added."""
    if d.name == "DarkAges-Virtual-Input" or d.path in _active_device_paths:
        return False

    try:
        caps = d.capabilities()
    except Exception:
        return False

    if ecodes.EV_KEY not in caps and ecodes.EV_REL not in caps and ecodes.EV_ABS not in caps:
        return False

    ev_key_codes: list[int] = []
    if ecodes.EV_KEY in caps:
        ev_key_codes = [c[0] if isinstance(c, tuple) else c for c in caps[ecodes.EV_KEY]]

    ev_abs_codes: list[int] = []
    if ecodes.EV_ABS in caps:
        ev_abs_codes = [c[0] if isinstance(c, tuple) else c for c in caps[ecodes.EV_ABS]]

    is_controller = (
        any(code in _CONTROLLER_KEY_CODES for code in ev_key_codes)
        or (ecodes.ABS_X in ev_abs_codes and ecodes.ABS_Y in ev_abs_codes and ecodes.BTN_LEFT not in ev_key_codes)
        or ecodes.ABS_HAT0X in ev_abs_codes
    )

    _active_device_paths.add(d.path)
    if is_controller:
        _controllers.append(d)
    elif ecodes.BTN_LEFT in ev_key_codes or ecodes.EV_REL in caps:
        _mice.append(d)
    else:
        _keyboards.append(d)
    return True


def setup_devices() -> None:
    global _uinput
    try:
        # Define capabilities for a composite keyboard + mouse pointer device
        keys = [
            ecodes.KEY_LEFT, ecodes.KEY_RIGHT, ecodes.KEY_UP, ecodes.KEY_DOWN,
            ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_TAB, ecodes.KEY_ESC,
            ecodes.KEY_BACKSPACE, ecodes.KEY_DELETE, ecodes.KEY_INSERT,
            ecodes.KEY_HOME, ecodes.KEY_END, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN,
            ecodes.KEY_MINUS, ecodes.KEY_EQUAL, ecodes.KEY_GRAVE,
            ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE,
            ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
            ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
            ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
        ]
        
        # Standard letters A-Z
        for c in range(ord("A"), ord("Z") + 1):
            keys.append(getattr(ecodes, f"KEY_{chr(c)}"))
        # Digits 0-9
        for i in range(10):
            keys.append(getattr(ecodes, f"KEY_{i}"))
        # Function keys F1-F12
        for i in range(1, 13):
            keys.append(getattr(ecodes, f"KEY_F{i}"))
            
        cap = {
            ecodes.EV_KEY: keys,
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]
        }

        all_devices: list[InputDevice[str]] = []
        for path in evdev.list_devices():
            try:
                all_devices.append(evdev.InputDevice(path))
            except Exception:
                pass

        # Create virtual device for re-emission
        _uinput = UInput(events=cap, name="DarkAges-Virtual-Input")
    except Exception:
        all_devices = []

    for d in all_devices:
        if not _classify_and_add_device(d):
            try:
                d.close()
            except Exception:
                pass


def toggle_suppression(enabled: bool) -> None:
    for kb in _keyboards:
        try:
            if enabled: kb.grab()
            else: kb.ungrab()
        except Exception:
            pass


def _raw_normalize_axis(value: int, abs_info: Any = None) -> float:
    if abs_info is not None and getattr(abs_info, "max", 0) > getattr(abs_info, "min", 0):
        center = (abs_info.max + abs_info.min) / 2.0
        half_range = (abs_info.max - abs_info.min) / 2.0
        norm = (value - center) / half_range
    else:
        norm = value / 32767.0
    return max(-1.0, min(1.0, norm))


def _normalize_stick_axis(value: int, abs_info: Any = None, deadzone: float = 0.12) -> float:
    norm = _raw_normalize_axis(value, abs_info)
    dz = max(0.02, min(0.60, deadzone))
    if abs(norm) < dz:
        return 0.0
    sign = 1.0 if norm > 0 else -1.0
    return sign * ((abs(norm) - dz) / (1.0 - dz))


def _normalize_trigger_axis(value: int, abs_info: Any = None) -> float:
    if abs_info is not None and getattr(abs_info, "max", 0) > getattr(abs_info, "min", 0):
        span = abs_info.max - abs_info.min
        norm = (value - abs_info.min) / float(span)
    else:
        norm = value / 255.0
    return max(0.0, min(1.0, norm))


# Allowed keys for "Suppress Trigger Keys":
# - Tilde (` and ~): KEY_GRAVE, KEY_TILDE
# - F keys: KEY_F1 to KEY_F24
# - Home cluster above arrow keys: KEY_HOME, KEY_DELETE, KEY_END, KEY_INSERT
STANDARD_SUPPRESSIBLE_KEYS: set[str] = {
    # Tilde key (` and ~)
    "KEY_GRAVE",
    "KEY_TILDE",
    # Home cluster above arrow keys (home, del, end, ins)
    "KEY_HOME",
    "KEY_DELETE",
    "KEY_END",
    "KEY_INSERT",
    # Function keys (F keys)
    *(f"KEY_F{i}" for i in range(1, 25)),
}

PGUP_PGDN_KEYS: set[str] = {
    "KEY_PAGEUP",
    "KEY_PAGEDOWN",
}


def _is_macro_trigger(key_name: str, state: dict) -> bool:
    """Check if key_name is an active trigger for an enabled macro."""
    macros = state.get("macros", [])
    for m in macros:
        if m.get("enabled", True):
            trig = m.get("trigger", "")
            if trig == key_name or trig == key_name.replace("KEY_", "").lower():
                return True
    return False


def _is_feature_hotkey_trigger(key_name: str, state: dict) -> bool:
    """Check if key_name matches Butterwalk, Controller, or Continuous Assail hotkeys."""
    from features.hotkeys import matches_hotkey
    keys_down = state.get("physical_keys_down", set())

    for hk_name in ("butterwalk_hotkey", "controller_hotkey", "space_hotkey"):
        hk = state.get(hk_name)
        if hk and matches_hotkey(hk, key_name, keys_down):
            return True

    return False


def should_suppress_key(key_name: str | None, state: dict) -> bool:
    """
    Determine if key_name should be suppressed from reaching the game:
    - pgup and pgdn are ONLY suppressed if a currently enabled macro uses them as a trigger,
      including Butterwalk, Controller, and Continuous Assail hotkeys.
    - Tilde, F keys, and Home cluster (Home, Del, End, Ins) are suppressed if they trigger
      an enabled macro or feature hotkey.
    - Other keys are never suppressed.
    """
    if not key_name or not state.get("suppress_triggers") or not state.get("active"):
        return False

    norm = key_name.upper()

    # Exception for PageUp and PageDown: ONLY suppress if bound to an enabled macro or feature hotkey
    if norm in PGUP_PGDN_KEYS:
        if _is_macro_trigger(norm, state):
            return True
        if _is_feature_hotkey_trigger(norm, state):
            return True
        return False

    # Standard suppressible keys
    if norm in STANDARD_SUPPRESSIBLE_KEYS:
        if _is_macro_trigger(norm, state):
            return True
        if _is_feature_hotkey_trigger(norm, state):
            return True
        return False

    return False


async def _read_device(device: InputDevice[str]) -> None:
    from state import state
    axis_states: dict[int, int] = {}
    digital_pseudo_down: set[str] = set()

    abs_dict: dict[int, Any] = {}
    try:
        caps = device.capabilities()
        if ecodes.EV_ABS in caps:
            for item in caps[ecodes.EV_ABS]:
                if isinstance(item, tuple) and len(item) == 2:
                    abs_dict[item[0]] = item[1]
    except Exception:
        pass

    def _set_pseudo_key(event: InputEvent, pseudo_name: str, pressed: bool) -> None:
        if pressed and pseudo_name not in digital_pseudo_down:
            digital_pseudo_down.add(pseudo_name)
            _fire_callbacks(event, pseudo_name, device.name, value_override=1)
        elif not pressed and pseudo_name in digital_pseudo_down:
            digital_pseudo_down.discard(pseudo_name)
            _fire_callbacks(event, pseudo_name, device.name, value_override=0)

    try:
        async for event in device.async_read_loop():
            if not state["running"]: break

            suppressed = False
            
            if event.type == ecodes.EV_KEY:
                key_name = _normalize_key_name(event.code)
                if key_name:
                    if should_suppress_key(key_name, state):
                        suppressed = True
                    
                    _fire_callbacks(event, key_name, device.name)

            elif event.type == ecodes.EV_ABS:
                # Always report raw ABS changes to the footer for debugging
                old_val = axis_states.get(event.code, 0)
                if abs(event.value - old_val) > 10: # Small noise gate
                    _fire_callbacks(event, f"ABS_{event.code}={event.value}", device.name)

                # Track continuous analog Right Stick for mouse cursor movement
                rs_dz = state.get("right_stick_deadzone", 12) / 100.0
                if event.code == ecodes.ABS_RX:
                    state["right_stick_x"] = _normalize_stick_axis(event.value, abs_dict.get(ecodes.ABS_RX), deadzone=rs_dz)
                elif event.code == ecodes.ABS_RY:
                    state["right_stick_y"] = _normalize_stick_axis(event.value, abs_dict.get(ecodes.ABS_RY), deadzone=rs_dz)

                # Handle DPAD (Hats)
                if event.code == ecodes.ABS_HAT0X:
                    _set_pseudo_key(event, "BTN_DPAD_LEFT", event.value == -1)
                    _set_pseudo_key(event, "BTN_DPAD_RIGHT", event.value == 1)
                    axis_states[event.code] = event.value
                elif event.code == ecodes.ABS_HAT0Y:
                    _set_pseudo_key(event, "BTN_DPAD_UP", event.value == -1)
                    _set_pseudo_key(event, "BTN_DPAD_DOWN", event.value == 1)
                    axis_states[event.code] = event.value
                
                # Handle Joystick Axes (Normalized with hysteresis and user deadzone)
                elif event.code in (ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_RX, ecodes.ABS_RY):
                    axis_map = {ecodes.ABS_X: "LX", ecodes.ABS_Y: "LY", ecodes.ABS_RX: "RX", ecodes.ABS_RY: "RY"}
                    axis_name = axis_map[event.code]
                    is_left_stick = event.code in (ecodes.ABS_X, ecodes.ABS_Y)
                    dz = (state.get("left_stick_deadzone", 12) if is_left_stick else state.get("right_stick_deadzone", 12)) / 100.0
                    norm = _raw_normalize_axis(event.value, abs_dict.get(event.code))

                    press_thresh = max(dz + 0.15, 0.45)
                    release_thresh = max(dz + 0.05, 0.30)

                    pos_name = f"BTN_JOY_{axis_name}_POS"
                    neg_name = f"BTN_JOY_{axis_name}_NEG"

                    if norm >= press_thresh:
                        _set_pseudo_key(event, pos_name, True)
                    elif norm <= release_thresh:
                        _set_pseudo_key(event, pos_name, False)

                    if norm <= -press_thresh:
                        _set_pseudo_key(event, neg_name, True)
                    elif norm >= -release_thresh:
                        _set_pseudo_key(event, neg_name, False)
                    
                    axis_states[event.code] = event.value
                
                # Handle Analog Triggers (Normalized 0.0..1.0 with hysteresis)
                elif event.code in (ecodes.ABS_Z, ecodes.ABS_RZ, ecodes.ABS_GAS, ecodes.ABS_BRAKE):
                    is_left = event.code in (ecodes.ABS_Z, ecodes.ABS_BRAKE)
                    trig_name = "BTN_L2" if is_left else "BTN_R2"
                    norm_t = _normalize_trigger_axis(event.value, abs_dict.get(event.code))
                    if norm_t >= 0.20:
                        _set_pseudo_key(event, trig_name, True)
                    elif norm_t <= 0.10:
                        _set_pseudo_key(event, trig_name, False)
                    axis_states[event.code] = event.value

                axis_states[event.code] = event.value

            # Re-emit only if suppression is active (keyboard is grabbed)
            if _uinput and state["suppress_triggers"] and not suppressed and device in _keyboards:
                if event.type == ecodes.EV_SYN:
                    # Write the hardware sync event data first, then flush the packet
                    _uinput.write_event(event)
                    _uinput.syn()
                elif event.type != ecodes.EV_ABS:
                    # Pass normal key/relative events through without forcing an early flush
                    _uinput.write_event(event)

    except Exception:
        pass
    finally:
        # Release any pseudo-keys that were held down if the device disconnects mid-input
        for pseudo_name in list(digital_pseudo_down):
            try:
                state["physical_keys_down"].discard(pseudo_name)
            except Exception:
                pass
        if device in _controllers:
            state["right_stick_x"] = 0.0
            state["right_stick_y"] = 0.0
            _controllers.remove(device)
        if device in _keyboards:
            _keyboards.remove(device)
        if device in _mice:
            _mice.remove(device)
        _active_device_paths.discard(device.path)
        try: device.ungrab()
        except Exception: pass
        try: device.close()
        except Exception: pass


async def hotplug_monitor() -> None:
    """Periodically scan /dev/input for newly connected or reconnected controllers/devices."""
    from state import state
    while state["running"]:
        await asyncio.sleep(2.5)
        if not state["running"]:
            break
        try:
            current_paths = set(evdev.list_devices())
            new_paths = current_paths - _active_device_paths
            for path in new_paths:
                try:
                    dev = evdev.InputDevice(path)
                    if _classify_and_add_device(dev):
                        if state.get("suppress_triggers") and dev in _keyboards:
                            try:
                                dev.grab()
                            except Exception:
                                pass
                        asyncio.get_running_loop().create_task(_read_device(dev))
                    else:
                        dev.close()
                except Exception:
                    pass
        except Exception:
            pass


def get_device_counts() -> tuple[int, int]:
    return len(_keyboards), len(_mice)


def get_controller_count() -> int:
    return len(_controllers)


def get_controller_names() -> list[str]:
    return [d.name for d in _controllers]


def get_device_names() -> list[str]:
    return [d.name for d in _keyboards + _mice + _controllers]


def get_read_tasks() -> list[Coroutine[Any, Any, None]]:
    tasks: list[Coroutine[Any, Any, None]] = [_read_device(d) for d in _keyboards + _mice + _controllers]
    tasks.append(hotplug_monitor())
    return tasks


def cleanup_devices() -> None:
    global _uinput
    try:
        toggle_suppression(False)
    except Exception:
        pass
    if _uinput is not None:
        try:
            _uinput.close()
        except Exception:
            pass
        _uinput = None
    for d in list(_keyboards + _mice + _controllers):
        try:
            d.close()
        except Exception:
            pass
    _keyboards.clear()
    _mice.clear()
    _controllers.clear()
    _active_device_paths.clear()
