from __future__ import annotations
import re
from typing import Any
from evdev.events import InputEvent
from state import state, save_config

CANONICAL_MODIFIERS: dict[str, set[str]] = {
    "ctrl": {"KEY_LEFTCTRL", "KEY_RIGHTCTRL"},
    "alt": {"KEY_LEFTALT", "KEY_RIGHTALT"},
    "shift": {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"},
    "super": {"KEY_LEFTMETA", "KEY_RIGHTMETA"},
}

MODIFIER_MAP: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "win": "super",
    "meta": "super",
}

MODIFIER_ORDER = ["ctrl", "alt", "shift", "super"]

ALL_MODIFIER_KEYS: set[str] = {
    "KEY_LEFTCTRL", "KEY_RIGHTCTRL",
    "KEY_LEFTALT", "KEY_RIGHTALT",
    "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
    "KEY_LEFTMETA", "KEY_RIGHTMETA",
}

KEY_ALIASES: dict[str, set[str]] = {
    "del": {"KEY_DELETE", "KEY_KPDELETE"},
    "delete": {"KEY_DELETE", "KEY_KPDELETE"},
    "pgup": {"KEY_PAGEUP", "KEY_KP9"},
    "pageup": {"KEY_PAGEUP", "KEY_KP9"},
    "pgdn": {"KEY_PAGEDOWN", "KEY_KP3"},
    "pagedown": {"KEY_PAGEDOWN", "KEY_KP3"},
    "ins": {"KEY_INSERT", "KEY_KP0"},
    "insert": {"KEY_INSERT", "KEY_KP0"},
    "home": {"KEY_HOME", "KEY_KP7"},
    "end": {"KEY_END", "KEY_KP1"},
    "enter": {"KEY_ENTER", "KEY_KPENTER"},
    "return": {"KEY_ENTER", "KEY_KPENTER"},
    "esc": {"KEY_ESC"},
    "escape": {"KEY_ESC"},
    "space": {"KEY_SPACE"},
    "spacebar": {"KEY_SPACE"},
    "tab": {"KEY_TAB"},
    "backspace": {"KEY_BACKSPACE"},
    "up": {"KEY_UP"},
    "down": {"KEY_DOWN"},
    "left": {"KEY_LEFT"},
    "right": {"KEY_RIGHT"},
    "minus": {"KEY_MINUS", "KEY_KPMINUS"},
    "equal": {"KEY_EQUAL", "KEY_KPPLUS"},
    "plus": {"KEY_EQUAL", "KEY_KPPLUS"},
    # Gamepad buttons
    "dpad_up": {"BTN_DPAD_UP"},
    "dpad_down": {"BTN_DPAD_DOWN"},
    "dpad_left": {"BTN_DPAD_LEFT"},
    "dpad_right": {"BTN_DPAD_RIGHT"},
    "btn_a": {"BTN_SOUTH", "BTN_A"},
    "btn_b": {"BTN_EAST", "BTN_B"},
    "btn_x": {"BTN_NORTH", "BTN_X"},
    "btn_y": {"BTN_WEST", "BTN_Y"},
    "l1": {"BTN_TL"},
    "r1": {"BTN_TR"},
    "l2": {"BTN_TL2", "BTN_L2"},
    "r2": {"BTN_TR2", "BTN_R2"},
    "select": {"BTN_SELECT"},
    "start": {"BTN_START"},
}

# Function keys F1-F12
for i in range(1, 13):
    KEY_ALIASES[f"f{i}"] = {f"KEY_F{i}"}

# Digits 0-9
for i in range(10):
    KEY_ALIASES[str(i)] = {f"KEY_{i}", f"KEY_KP{i}"}

# Letters a-z
for c in range(ord("a"), ord("z") + 1):
    KEY_ALIASES[chr(c)] = {f"KEY_{chr(c).upper()}"}


REVERSE_KEY_MAP: dict[str, str] = {
    "KEY_LEFTCTRL": "ctrl",
    "KEY_RIGHTCTRL": "ctrl",
    "KEY_LEFTALT": "alt",
    "KEY_RIGHTALT": "alt",
    "KEY_LEFTSHIFT": "shift",
    "KEY_RIGHTSHIFT": "shift",
    "KEY_LEFTMETA": "super",
    "KEY_RIGHTMETA": "super",
    "KEY_DELETE": "del",
    "KEY_KPDELETE": "del",
    "KEY_PAGEUP": "pgup",
    "KEY_KP9": "pgup",
    "KEY_PAGEDOWN": "pgdn",
    "KEY_KP3": "pgdn",
    "KEY_INSERT": "ins",
    "KEY_KP0": "0",
    "KEY_HOME": "home",
    "KEY_KP7": "7",
    "KEY_END": "end",
    "KEY_KP1": "1",
    "KEY_ENTER": "enter",
    "KEY_KPENTER": "enter",
    "KEY_ESC": "esc",
    "KEY_SPACE": "space",
    "KEY_TAB": "tab",
    "KEY_BACKSPACE": "backspace",
    "KEY_UP": "up",
    "KEY_DOWN": "down",
    "KEY_LEFT": "left",
    "KEY_RIGHT": "right",
}


def normalize_hotkey_str(raw: str) -> str:
    """Normalize user hotkey string into canonical 'ctrl + alt + key' form."""
    if not raw or not raw.strip():
        return ""
    parts = [p.strip().lower() for p in re.split(r'[\+\s]+', raw.strip()) if p.strip()]
    if not parts:
        return ""

    mods: list[str] = []
    keys: list[str] = []

    for p in parts:
        if p in ("ctrl", "control"):
            if "ctrl" not in mods: mods.append("ctrl")
        elif p == "alt":
            if "alt" not in mods: mods.append("alt")
        elif p == "shift":
            if "shift" not in mods: mods.append("shift")
        elif p in ("super", "win", "meta"):
            if "super" not in mods: mods.append("super")
        else:
            norm_k = p
            if norm_k in ("delete", "del"): norm_k = "del"
            elif norm_k in ("pageup", "pgup"): norm_k = "pgup"
            elif norm_k in ("pagedown", "pgdn"): norm_k = "pgdn"
            elif norm_k in ("insert", "ins"): norm_k = "ins"
            elif norm_k in ("return", "enter"): norm_k = "enter"
            elif norm_k in ("escape", "esc"): norm_k = "esc"
            elif norm_k in ("spacebar", "space"): norm_k = "space"
            keys.append(norm_k)

    sorted_mods = [m for m in MODIFIER_ORDER if m in mods]
    combo = sorted_mods + keys
    return " + ".join(combo)


def format_hotkey_from_keys(keys_down: set[str], trigger_key: str | None = None) -> str:
    """Format a set of held keys and/or trigger key into canonical hotkey string."""
    all_keys = set(keys_down)
    if trigger_key:
        all_keys.add(trigger_key)

    mods: list[str] = []
    if any(k in ("KEY_LEFTCTRL", "KEY_RIGHTCTRL") for k in all_keys):
        mods.append("ctrl")
    if any(k in ("KEY_LEFTALT", "KEY_RIGHTALT") for k in all_keys):
        mods.append("alt")
    if any(k in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT") for k in all_keys):
        mods.append("shift")
    if any(k in ("KEY_LEFTMETA", "KEY_RIGHTMETA") for k in all_keys):
        mods.append("super")

    non_mods: list[str] = []
    candidates = [trigger_key] if trigger_key and trigger_key not in ALL_MODIFIER_KEYS else []
    for k in sorted(all_keys):
        if k not in ALL_MODIFIER_KEYS and k not in candidates:
            candidates.append(k)

    for k in candidates:
        if not k: continue
        name = REVERSE_KEY_MAP.get(k)
        if not name:
            if k.startswith("KEY_"):
                name = k[4:].lower()
            elif k.startswith("BTN_"):
                name = k.lower()
            else:
                name = k.lower()
        if name not in non_mods:
            non_mods.append(name)

    combo = mods + non_mods
    return " + ".join(combo)


def parse_hotkey_requirements(hotkey_str: str) -> tuple[set[str], list[set[str]]] | None:
    norm = normalize_hotkey_str(hotkey_str)
    if not norm:
        return None
    tokens = [t.strip() for t in norm.split("+")]
    required_mods: set[str] = set()
    required_key_sets: list[set[str]] = []

    for t in tokens:
        if t in MODIFIER_MAP:
            required_mods.add(MODIFIER_MAP[t])
        elif t in KEY_ALIASES:
            required_key_sets.append(KEY_ALIASES[t])
        else:
            up = t.upper()
            if not up.startswith("KEY_") and not up.startswith("BTN_"):
                up = f"KEY_{up}"
            required_key_sets.append({up})

    return required_mods, required_key_sets


def matches_hotkey(hotkey_str: str, key_name: str, keys_down: set[str]) -> bool:
    """Check if the key event combined with current held keys matches the hotkey definition."""
    parsed = parse_hotkey_requirements(hotkey_str)
    if not parsed:
        return False
    required_mods, required_key_sets = parsed
    current_keys = set(keys_down) | {key_name}

    # 1. key_name must be relevant to the hotkey
    is_relevant = False
    for mod in required_mods:
        if key_name in CANONICAL_MODIFIERS[mod]:
            is_relevant = True
            break
    if not is_relevant:
        for kset in required_key_sets:
            if key_name in kset:
                is_relevant = True
                break
    if not is_relevant:
        return False

    # 2. Check required modifiers
    for mod in required_mods:
        if not any(k in current_keys for k in CANONICAL_MODIFIERS[mod]):
            return False

    # 3. Check forbidden modifiers
    for mod_name, mod_keys in CANONICAL_MODIFIERS.items():
        if mod_name not in required_mods:
            if any(k in current_keys for k in mod_keys):
                return False

    # 4. Check required target keys
    for kset in required_key_sets:
        if not any(k in current_keys for k in kset):
            return False

    return True


def on_key_event(event: InputEvent, key_name: str) -> bool:
    """Global event listener for capturing or executing hotkeys."""
    if event.value == 1:
        state["physical_keys_down"].add(key_name)
    elif event.value == 0:
        state["physical_keys_down"].discard(key_name)

    # 1. Handle interactive hotkey recording/binding mode
    target = state.get("listening_for_hotkey")
    if target:
        if key_name in ("BTN_LEFT", "CODE_272"):
            return False

        if event.value == 1:
            if key_name not in ALL_MODIFIER_KEYS:
                combo = format_hotkey_from_keys(state["physical_keys_down"], key_name)
                state["captured_hotkey"] = (target, combo)
                state["listening_for_hotkey"] = None
                state["last_event"] = f"Bound {target} to {combo}"
                save_config()
                return True
        elif event.value == 0:
            if key_name in ALL_MODIFIER_KEYS and len(state["physical_keys_down"]) <= 1:
                mod_name = REVERSE_KEY_MAP.get(key_name, "ctrl")
                state["captured_hotkey"] = (target, mod_name)
                state["listening_for_hotkey"] = None
                state["last_event"] = f"Bound {target} to {mod_name}"
                save_config()
                return True
        return True

    # 2. Check hotkey triggers on key down (event.value == 1)
    if event.value == 1:
        is_allowed = False
        if state.get("active", False):
            is_allowed = True
        else:
            cname = state.get("client_name", "").lower()
            if "darkages" in cname or "dalt" in cname:
                is_allowed = True

        # Check Butterwalk hotkey
        bw_hotkey = state.get("butterwalk_hotkey", "ctrl + del")
        if bw_hotkey:
            has_mods = any(m in bw_hotkey for m in ("ctrl", "alt", "shift", "super"))
            if (is_allowed or has_mods) and matches_hotkey(bw_hotkey, key_name, state["physical_keys_down"]):
                state["butterwalk"] = not state["butterwalk"]
                state["last_event"] = f"Butterwalk {'ON' if state['butterwalk'] else 'OFF'} ({bw_hotkey})"
                return True

        # Check Controller hotkey
        ctrl_hotkey = state.get("controller_hotkey", "ctrl + pgup")
        if ctrl_hotkey:
            has_mods = any(m in ctrl_hotkey for m in ("ctrl", "alt", "shift", "super"))
            if (is_allowed or has_mods) and matches_hotkey(ctrl_hotkey, key_name, state["physical_keys_down"]):
                state["controller_enabled"] = not state["controller_enabled"]
                save_config()
                state["last_event"] = f"Controller {'ON' if state['controller_enabled'] else 'OFF'} ({ctrl_hotkey})"
                return True

        # Check Spacebar hotkey
        space_hotkey = state.get("space_hotkey", "ctrl + pgdn")
        if space_hotkey:
            has_mods = any(m in space_hotkey for m in ("ctrl", "alt", "shift", "super"))
            if (is_allowed or has_mods) and matches_hotkey(space_hotkey, key_name, state["physical_keys_down"]):
                state["space_enabled"] = not state["space_enabled"]
                save_config()
                state["last_event"] = f"Spacebar Repeat {'ON' if state['space_enabled'] else 'OFF'} ({space_hotkey})"
                return True

    return False
