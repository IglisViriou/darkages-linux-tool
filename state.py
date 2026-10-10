from __future__ import annotations
import os
import json
from typing import TypedDict, Literal, Any
from dotenv import load_dotenv

_ = load_dotenv()

CONFIG_DIR = os.path.expanduser("~/.config/darkages-linux-tool")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_MULTIPLIER: int = 1
DEFAULT_LOOP_INTERVAL: float = 0.01
DEFAULT_DARKAGES_WINDOW_NAMES: str = "Unora"


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
            "space_enabled": state["space_enabled"],
            "space_multiplier": state["space_multiplier"],
            "butterwalk_hotkey": state["butterwalk_hotkey"],
            "controller_hotkey": state["controller_hotkey"],
            "space_hotkey": state["space_hotkey"],
            "suppress_triggers": state["suppress_triggers"],
            "multiplier": state["multiplier"]
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
    physical_keys_down: set[str]
    zxcv_enabled: bool
    # controller inputs
    controller_enabled: bool
    dpad_enabled: bool
    joystick_enabled: bool
    right_stick_mouse_enabled: bool
    mouse_sensitivity: int
    mouse_dpi: int
    right_stick_x: float
    right_stick_y: float
    # spacebar uninterrupted repeat
    space_enabled: bool
    space_multiplier: int
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


loaded_config = load_config()

state: State = {
    "running": True,
    "active": False,
    "client_name": "Searching...",
    "loop_interval": float(os.getenv("LOOP_INTERVAL") or DEFAULT_LOOP_INTERVAL),
    "window_hooks": loaded_config.get("window_hooks", (os.getenv("DARKAGES_WINDOW_NAMES") or DEFAULT_DARKAGES_WINDOW_NAMES).split(",")),
    "butterwalk": False,
    "multiplier": loaded_config.get("multiplier", int(os.getenv("DEFAULT_MULTIPLIER") or DEFAULT_MULTIPLIER)),
    "physical_keys_down": set(),
    "zxcv_enabled": loaded_config.get("zxcv_enabled", False),
    "controller_enabled": loaded_config.get("controller_enabled", True),
    "dpad_enabled": loaded_config.get("dpad_enabled", False),
    "joystick_enabled": loaded_config.get("joystick_enabled", True),
    "right_stick_mouse_enabled": loaded_config.get("right_stick_mouse_enabled", False),
    "mouse_sensitivity": loaded_config.get("mouse_sensitivity", 50),
    "mouse_dpi": loaded_config.get("mouse_dpi", 1600),
    "right_stick_x": 0.0,
    "right_stick_y": 0.0,
    "space_enabled": loaded_config.get("space_enabled", False),
    "space_multiplier": loaded_config.get("space_multiplier", 1),
    "butterwalk_hotkey": loaded_config.get("butterwalk_hotkey", "ctrl + del"),
    "controller_hotkey": loaded_config.get("controller_hotkey", "ctrl + pgup"),
    "space_hotkey": loaded_config.get("space_hotkey", "ctrl + pgdn"),
    "listening_for_hotkey": None,
    "captured_hotkey": None,
    "macros": [],
    "macro_playing": set(),
    "active_macro_tasks": {},
    "recording_mouse": False,
    "recording_start_time": 0.0,
    "captured_click": None,
    "last_event": "None",
    "listening_for_trigger": False,
    "captured_trigger": None,
    "suppress_triggers": loaded_config.get("suppress_triggers", False),
}
