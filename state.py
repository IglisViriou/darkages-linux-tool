from __future__ import annotations
import os
import json
from typing import TypedDict, Literal, Any
from dotenv import load_dotenv
from features.shortcuts import Shortcut, load_shortcuts

_ = load_dotenv()

CONFIG_DIR = os.path.expanduser("~/.config/darkages-linux-tool")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_MULTIPLIER: int = 1
DEFAULT_LOOP_INTERVAL: float = 0.01
DEFAULT_DARKAGES_WINDOW_NAMES: str = "Unora"


class ControllerBinding(TypedDict):
    kind: Literal["none", "key", "mouse", "layer_hold", "macro"]
    value: str


def get_default_controller_bindings() -> dict[str, ControllerBinding]:
    return {
        # Left Stick
        "BTN_JOY_LY_NEG": {"kind": "key", "value": "Up"},
        "BTN_JOY_LY_POS": {"kind": "key", "value": "Down"},
        "BTN_JOY_LX_NEG": {"kind": "key", "value": "Left"},
        "BTN_JOY_LX_POS": {"kind": "key", "value": "Right"},
        # DPAD
        "BTN_DPAD_UP": {"kind": "key", "value": "Up"},
        "BTN_DPAD_DOWN": {"kind": "key", "value": "Down"},
        "BTN_DPAD_LEFT": {"kind": "key", "value": "Left"},
        "BTN_DPAD_RIGHT": {"kind": "key", "value": "Right"},
        # Stick Clicks
        "BTN_THUMBL": {"kind": "none", "value": ""},
        "BTN_THUMBR": {"kind": "mouse", "value": "middle_click"},
        # Face Buttons
        "BTN_SOUTH": {"kind": "mouse", "value": "left_click"},
        "BTN_EAST": {"kind": "mouse", "value": "right_click"},
        "BTN_WEST": {"kind": "key", "value": "space"},
        "BTN_NORTH": {"kind": "key", "value": "Tab"},
        # Bumpers & Triggers
        "BTN_TL": {"kind": "layer_hold", "value": "modifier_layer"},
        "BTN_TR": {"kind": "key", "value": "Escape"},
        "BTN_L2": {"kind": "mouse", "value": "right_click"},
        "BTN_R2": {"kind": "mouse", "value": "left_click"},
        # Center Buttons
        "BTN_SELECT": {"kind": "key", "value": "Escape"},
        "BTN_START": {"kind": "key", "value": "Return"},
        "BTN_MODE": {"kind": "none", "value": ""},
        # Right Stick Directions (used when Right Stick Mouse Control is off)
        "BTN_JOY_RY_NEG": {"kind": "none", "value": ""},
        "BTN_JOY_RY_POS": {"kind": "none", "value": ""},
        "BTN_JOY_RX_NEG": {"kind": "none", "value": ""},
        "BTN_JOY_RX_POS": {"kind": "none", "value": ""},
    }


def get_minimal_controller_bindings() -> dict[str, ControllerBinding]:
    bindings = {k: {"kind": "none", "value": ""} for k in get_default_controller_bindings()}
    bindings["BTN_JOY_LY_NEG"] = {"kind": "key", "value": "Up"}
    bindings["BTN_JOY_LY_POS"] = {"kind": "key", "value": "Down"}
    bindings["BTN_JOY_LX_NEG"] = {"kind": "key", "value": "Left"}
    bindings["BTN_JOY_LX_POS"] = {"kind": "key", "value": "Right"}
    bindings["BTN_DPAD_UP"] = {"kind": "key", "value": "Up"}
    bindings["BTN_DPAD_DOWN"] = {"kind": "key", "value": "Down"}
    bindings["BTN_DPAD_LEFT"] = {"kind": "key", "value": "Left"}
    bindings["BTN_DPAD_RIGHT"] = {"kind": "key", "value": "Right"}
    return bindings


def get_default_layer_bindings() -> dict[str, ControllerBinding]:
    bindings: dict[str, ControllerBinding] = {
        k: {"kind": "none", "value": ""} for k in get_default_controller_bindings()
    }
    bindings["BTN_SOUTH"] = {"kind": "key", "value": "F1"}
    bindings["BTN_EAST"] = {"kind": "key", "value": "F2"}
    bindings["BTN_WEST"] = {"kind": "key", "value": "F3"}
    bindings["BTN_NORTH"] = {"kind": "key", "value": "F4"}
    bindings["BTN_DPAD_UP"] = {"kind": "key", "value": "1"}
    bindings["BTN_DPAD_RIGHT"] = {"kind": "key", "value": "2"}
    bindings["BTN_DPAD_DOWN"] = {"kind": "key", "value": "3"}
    bindings["BTN_DPAD_LEFT"] = {"kind": "key", "value": "4"}
    bindings["BTN_TR"] = {"kind": "key", "value": "F5"}
    bindings["BTN_L2"] = {"kind": "key", "value": "F6"}
    bindings["BTN_R2"] = {"kind": "key", "value": "F7"}
    bindings["BTN_START"] = {"kind": "key", "value": "F8"}
    return bindings


def _merge_bindings(
    defaults: dict[str, ControllerBinding],
    loaded: dict[str, Any] | None,
) -> dict[str, ControllerBinding]:
    merged: dict[str, ControllerBinding] = {
        k: {"kind": v["kind"], "value": v["value"]} for k, v in defaults.items()
    }
    if isinstance(loaded, dict):
        for k, v in loaded.items():
            if isinstance(v, dict) and "kind" in v and "value" in v:
                merged[k] = {"kind": v["kind"], "value": str(v["value"])}
    return merged


def save_config() -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config = {
            "window_hooks": state["window_hooks"],
            "zxcv_enabled": state["zxcv_enabled"],
            "controller_enabled": state["controller_enabled"],
            "dpad_enabled": state["dpad_enabled"],
            "joystick_enabled": state["joystick_enabled"],
            "right_stick_mouse_enabled": state["right_stick_mouse_enabled"],
            "mouse_sensitivity": state["mouse_sensitivity"],
            "mouse_dpi": state["mouse_dpi"],
            "left_stick_deadzone": state["left_stick_deadzone"],
            "right_stick_deadzone": state["right_stick_deadzone"],
            "controller_bindings": state["controller_bindings"],
            "controller_layer_bindings": state["controller_layer_bindings"],
            "space_enabled": state["space_enabled"],
            "space_multiplier": state["space_multiplier"],
            "space_delay_ms": state["space_delay_ms"],
            "butterwalk_hotkey": state["butterwalk_hotkey"],
            "controller_hotkey": state["controller_hotkey"],
            "space_hotkey": state["space_hotkey"],
            "suppress_triggers": state["suppress_triggers"],
            "multiplier": state["multiplier"],
            "butterwalk_delay_ms": state["butterwalk_delay_ms"]
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        state["last_event"] = f"Config Error: {str(e)}"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class MacroStep(TypedDict):
    kind: Literal["key", "mouse_left", "mouse_right", "wait"]
    value: str  # xdotool key name (only used for "key" kind)
    delay_ms: int  # milliseconds to wait BEFORE executing this step
    x: int | None
    y: int | None


class Macro(TypedDict):
    id: str
    name: str
    enabled: bool
    kind: Literal["macro", "keybind"]
    trigger_mode: Literal["once", "hold"]
    trigger: str  # evdev key name e.g. "KEY_F5"
    interruptible: bool
    steps: list[MacroStep]


class State(TypedDict):
    running: bool
    active: bool
    client_name: str
    loop_interval: float
    window_hooks: list[str]
    # butterwalk
    butterwalk: bool
    multiplier: int
    butterwalk_delay_ms: int
    physical_keys_down: set[str]
    zxcv_enabled: bool
    # controller inputs
    controller_enabled: bool
    dpad_enabled: bool
    joystick_enabled: bool
    right_stick_mouse_enabled: bool
    mouse_sensitivity: int
    mouse_dpi: int
    left_stick_deadzone: int
    right_stick_deadzone: int
    right_stick_x: float
    right_stick_y: float
    controller_bindings: dict[str, ControllerBinding]
    controller_layer_bindings: dict[str, ControllerBinding]
    last_controller_input: str | None
    listening_for_controller_input: bool
    captured_controller_input: str | None
    # spacebar uninterrupted repeat
    space_enabled: bool
    space_multiplier: int
    space_delay_ms: int
    # macros
    macros: list[Macro]
    macro_playing: set[str]
    active_macro_tasks: dict[str, Any]
    macros_holding: set[str] # Tracking macros currently in 'hold' repeat loop
    recording_mouse: bool
    recording_start_time: float
    captured_click: dict | None
    last_event: str
    listening_for_trigger: bool
    captured_trigger: str | None
    # suppression
    suppress_triggers: bool
    # hotkeys
    butterwalk_hotkey: str
    controller_hotkey: str
    space_hotkey: str
    listening_for_hotkey: str | None
    captured_hotkey: tuple[str, str] | None
    # quick launch shortcuts
    shortcuts: list[Shortcut]
    active_window_id: str | None


loaded_config = load_config()

state: State = {
    "running": True,
    "active": False,
    "client_name": "Searching...",
    "active_window_id": None,
    "loop_interval": float(os.getenv("LOOP_INTERVAL") or DEFAULT_LOOP_INTERVAL),
    "window_hooks": loaded_config.get("window_hooks", (os.getenv("DARKAGES_WINDOW_NAMES") or DEFAULT_DARKAGES_WINDOW_NAMES).split(",")),
    "butterwalk": False,
    "multiplier": loaded_config.get("multiplier", int(os.getenv("DEFAULT_MULTIPLIER") or DEFAULT_MULTIPLIER)),
    "butterwalk_delay_ms": loaded_config.get("butterwalk_delay_ms", 10),
    "physical_keys_down": set(),
    "zxcv_enabled": loaded_config.get("zxcv_enabled", False),
    "controller_enabled": loaded_config.get("controller_enabled", True),
    "dpad_enabled": loaded_config.get("dpad_enabled", False),
    "joystick_enabled": loaded_config.get("joystick_enabled", True),
    "right_stick_mouse_enabled": loaded_config.get("right_stick_mouse_enabled", False),
    "mouse_sensitivity": loaded_config.get("mouse_sensitivity", 50),
    "mouse_dpi": loaded_config.get("mouse_dpi", 1600),
    "left_stick_deadzone": loaded_config.get("left_stick_deadzone", 12),
    "right_stick_deadzone": loaded_config.get("right_stick_deadzone", 12),
    "right_stick_x": 0.0,
    "right_stick_y": 0.0,
    "controller_bindings": _merge_bindings(get_default_controller_bindings(), loaded_config.get("controller_bindings")),
    "controller_layer_bindings": _merge_bindings(get_default_layer_bindings(), loaded_config.get("controller_layer_bindings")),
    "last_controller_input": None,
    "listening_for_controller_input": False,
    "captured_controller_input": None,
    "space_enabled": loaded_config.get("space_enabled", False),
    "space_multiplier": loaded_config.get("space_multiplier", 1),
    "space_delay_ms": loaded_config.get("space_delay_ms", 10),
    "butterwalk_hotkey": loaded_config.get("butterwalk_hotkey", "ctrl + del"),
    "controller_hotkey": loaded_config.get("controller_hotkey", "ctrl + pgup"),
    "space_hotkey": loaded_config.get("space_hotkey", "ctrl + pgdn"),
    "listening_for_hotkey": None,
    "captured_hotkey": None,
    "macros": [],
    "macro_playing": set(),
    "active_macro_tasks": {},
    "macros_holding": set(),
    "recording_mouse": False,
    "recording_start_time": 0.0,
    "captured_click": None,
    "last_event": "None",
    "listening_for_trigger": False,
    "captured_trigger": None,
    "suppress_triggers": loaded_config.get("suppress_triggers", False),
    "shortcuts": load_shortcuts(),
}
