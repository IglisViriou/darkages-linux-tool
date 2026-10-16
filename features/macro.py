from __future__ import annotations
import asyncio
import curses
import json
import os
import uuid
import subprocess
from typing import Any
from evdev.events import InputEvent
from state import state, Macro, MacroStep
import injector
from ui.canvas import Canvas, Chunk
from ui import theme

MACRO_CONFIG_PATH = os.path.expanduser("~/.config/darkages-linux-tool/macros.json")

_TRIGGER_MAP: dict[str, str] = {
    "enter": "KEY_RETURN",
    "return": "KEY_RETURN",
    "space": "KEY_SPACE",
    "tab": "KEY_TAB",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
    "insert": "KEY_INSERT",
    "home": "KEY_HOME",
    "end": "KEY_END",
    "pageup": "KEY_PAGEUP",
    "pgup": "KEY_PAGEUP",
    "pagedown": "KEY_PAGEDOWN",
    "pgdn": "KEY_PAGEDOWN",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "dpad_up": "BTN_DPAD_UP",
    "dpad_down": "BTN_DPAD_DOWN",
    "dpad_left": "BTN_DPAD_LEFT",
    "dpad_right": "BTN_DPAD_RIGHT",
    "pad_a": "BTN_SOUTH",
    "south": "BTN_SOUTH",
    "pad_b": "BTN_EAST",
    "east": "BTN_EAST",
    "pad_x": "BTN_WEST",
    "west": "BTN_WEST",
    "pad_y": "BTN_NORTH",
    "north": "BTN_NORTH",
    "l1": "BTN_TL",
    "lb": "BTN_TL",
    "r1": "BTN_TR",
    "rb": "BTN_TR",
    "l2": "BTN_L2",
    "lt": "BTN_L2",
    "r2": "BTN_R2",
    "rt": "BTN_R2",
    "l3": "BTN_THUMBL",
    "thumbl": "BTN_THUMBL",
    "r3": "BTN_THUMBR",
    "thumbr": "BTN_THUMBR",
    "select": "BTN_SELECT",
    "start": "BTN_START",
    "mode": "BTN_MODE",
    "grave": "KEY_GRAVE",
    "tilde": "KEY_GRAVE",
    "`": "KEY_GRAVE",
    "~": "KEY_GRAVE",
    **{f"f{i}": f"KEY_F{i}" for i in range(1, 13)},
    **{str(i): f"KEY_{i}" for i in range(10)},
    **{chr(c): f"KEY_{chr(c).upper()}" for c in range(ord("a"), ord("z") + 1)},
}

_SPECIAL_XDOTOOL: dict[str, str] = {
    "grave": "grave",
    "tilde": "asciitilde",
    "`": "grave",
    "~": "asciitilde",
    "enter": "Return",
    "return": "Return",
    "space": "space",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pgup": "Prior",
    "pagedown": "Next",
    "pgdn": "Next",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "arrow_up": "Up",
    "arrow_down": "Down",
    "arrow_left": "Left",
    "arrow_right": "Right",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}

DEFAULT_STEP_DELAY = 10


def _normalize_trigger(raw: str) -> str | None:
    key = raw.strip().lower()
    if key in _TRIGGER_MAP:
        return _TRIGGER_MAP[key]
    up = raw.strip().upper()
    if up.startswith("KEY_") or up.startswith("BTN_"):
        return up
    return None


def _parse_sequence(seq: str, default_delay_ms: int = 0) -> list[MacroStep]:
    """Parse a sequence string into MacroSteps.
    Applies the default delay to steps (except explicit wait steps).
    """
    steps: list[MacroStep] = []
    i = 0

    while i < len(seq):
        ch = seq[i]
        if ch == "{":
            j = seq.find("}", i + 1)
            if j == -1:
                i += 1
                continue
            inner = seq[i + 1 : j].strip().lower()
            if inner in ("click", "lclick", "mouse_left"):
                steps.append(MacroStep(kind="mouse_left", value="", delay_ms=default_delay_ms, x=None, y=None))
            elif inner in ("rclick", "mouse_right"):
                steps.append(MacroStep(kind="mouse_right", value="", delay_ms=default_delay_ms, x=None, y=None))
            elif inner.startswith("wait:"):
                try:
                    ms = int(inner.split(":")[1])
                    steps.append(MacroStep(kind="wait", value="", delay_ms=ms, x=None, y=None))
                except: pass
            elif inner in _SPECIAL_XDOTOOL:
                steps.append(
                    MacroStep(
                        kind="key", value=_SPECIAL_XDOTOOL[inner], delay_ms=default_delay_ms, x=None, y=None
                    )
                )
            i = j + 1
        elif ch.isalpha() or ch.isdigit() or ch in "-=":
            val = ch
            if ch == "-": val = "minus"
            elif ch == "=": val = "equal"
            steps.append(MacroStep(kind="key", value=val, delay_ms=default_delay_ms, x=None, y=None))
            i += 1
        else:
            i += 1

    return steps


def load_macros() -> None:
    try:
        with open(MACRO_CONFIG_PATH) as f:
            state["macros"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_macros() -> None:
    os.makedirs(os.path.dirname(MACRO_CONFIG_PATH), exist_ok=True)
    with open(MACRO_CONFIG_PATH, "w") as f:
        json.dump(state["macros"], f, indent=2)


class MacroFeature:
    name: str = "Macros"

    def __init__(self) -> None:
        self._selected: int = 0
        self.phase: str | None = None  # None | "name" | "trigger" | "steps"
        self._buf: str = ""  # name / trigger input
        self._draft_name: str = ""
        self._draft_trigger: str = ""
        self._seq_buf: str = ""  # sequence string
        self._delay_buf: str = str(DEFAULT_STEP_DELAY)
        self._seq_focus: bool = True  # True = sequence field, False = delay field
        self._error: str = ""
        from features import controller
        controller.set_macro_runner(self.trigger_macro)

    def trigger_macro(self, macro: Macro | dict[str, Any]) -> None:
        if macro.get("kind") == "keybind" and macro.get("steps"):
            try:
                asyncio.get_running_loop().create_task(injector.key(macro["steps"][0]["value"]))
            except RuntimeError:
                pass
            return

        mid = macro["id"]
        if mid not in state["macro_playing"]:
            state["macro_playing"].add(mid)
            try:
                _ = asyncio.get_running_loop().create_task(
                    self._play_macro(macro)  # type: ignore[arg-type]
                )
            except RuntimeError:
                state["macro_playing"].discard(mid)
    
    async def hold_loop(self) -> None:
        """Background loop to handle 'hold' mode macros."""
        from features import controller
        while state["running"]:
            if state["active"] and state["physical_keys_down"]:
                for macro in state["macros"]:
                    trig = macro.get("trigger", "")
                    if (
                        macro.get("enabled", True)
                        and macro.get("trigger_mode") == "hold"
                        and trig in state["physical_keys_down"]
                        and macro["id"] not in state["macro_playing"]
                    ):
                        if controller.should_suppress_macro_for_controller(trig):
                            continue
                        state["macro_playing"].add(macro["id"])
                        try:
                            _ = asyncio.get_running_loop().create_task(
                                self._play_macro(macro)
                            )
                        except RuntimeError:
                            state["macro_playing"].discard(macro["id"])
                await asyncio.sleep(state["loop_interval"])
            else:
                await asyncio.sleep(0.05)

    def on_key_event(self, event: InputEvent, key_name: str) -> None:
        # Handle Trigger Binding Mode
        if state.get("listening_for_trigger") and event.value == 1:
            if key_name in ("BTN_LEFT", "CODE_272"):
                state["last_event"] = "Safety: Left Click rejected as trigger"
                return

            state["captured_trigger"] = key_name
            state["listening_for_trigger"] = False
            return

        if state.get("recording_mouse") and event.value == 1:
            asyncio.get_running_loop().create_task(self._record_mouse_click_async(key_name))
            state["recording_mouse"] = False
            return

        if state["active"] and event.value == 1:
            from features import controller
            if controller.should_suppress_macro_for_controller(key_name):
                return
            for macro in state["macros"]:
                if (
                    macro.get("enabled", True)
                    and macro["trigger"] == key_name
                    and macro["id"] not in state["macro_playing"]
                ):
                    # Only trigger 'once' macros here. 'hold' macros are handled by hold_loop.
                    if macro.get("trigger_mode", "once") == "hold":
                        continue

                    self.trigger_macro(macro)

    async def _play_macro(self, macro: Macro) -> None:
        # Cancel any other interruptible macros
        for mid in list(state["macro_playing"]):
            if mid == macro["id"]: continue
            # Find the macro object
            other = next((m for m in state["macros"] if m["id"] == mid), None)
            if other and other.get("interruptible", True):
                task = state.get("active_macro_tasks", {}).get(mid)
                if task:
                    task.cancel()

        state["macro_playing"].add(macro["id"])
        # Store current task
        if "active_macro_tasks" not in state: state["active_macro_tasks"] = {}
        state["active_macro_tasks"][macro["id"]] = asyncio.current_task()

        try:
            loop = asyncio.get_running_loop()
            last_key_end_time = 0.0

            for step in macro["steps"]:
                if not state["running"]:
                    break

                # If this is a mouse click following a key (e.g. spell hotkey -> target confirmation),
                # guarantee a minimum pre-click delay (25ms) so the game client has time to open the targeting reticle.
                if step["kind"] in ("mouse_left", "mouse_right") and last_key_end_time > 0.0:
                    elapsed = loop.time() - last_key_end_time
                    step_delay = (step.get("delay_ms", 0) or 0) / 1000.0
                    min_transition = 0.025
                    remaining = min_transition - (elapsed + step_delay)
                    if remaining > 0:
                        await asyncio.sleep(remaining)

                if step.get("delay_ms", 0) > 0:
                    await asyncio.sleep(step["delay_ms"] / 1000.0)
                
                if step["kind"] == "key" and step["value"]:
                    await injector.key(step["value"])
                    last_key_end_time = loop.time()
                elif step["kind"] == "mouse_left":
                    await injector.mouse_click(1, step.get("x"), step.get("y"))
                    last_key_end_time = 0.0
                elif step["kind"] == "mouse_right":
                    await injector.mouse_click(3, step.get("x"), step.get("y"))
                    last_key_end_time = 0.0
                elif step["kind"] == "wait":
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            state["macro_playing"].discard(macro["id"])
            if macro["id"] in state.get("active_macro_tasks", {}):
                del state["active_macro_tasks"][macro["id"]]

    def handle_input(self, ch: int) -> None:
        self._error = ""

        if self.phase == "name":
            if ch in (ord("\n"), 10, curses.KEY_ENTER):
                self._draft_name = self._buf.strip() or "Unnamed"
                self._buf = ""
                self.phase = "trigger"
            elif ch == 27:
                self.phase = None
                self._buf = ""
            elif ch in (curses.KEY_BACKSPACE, 127):
                self._buf = self._buf[:-1]
            elif 32 <= ch < 127:
                self._buf += chr(ch)
            return

        if self.phase == "trigger":
            if ch in (ord("\n"), 10, curses.KEY_ENTER):
                evdev_key = _normalize_trigger(self._buf)
                if evdev_key:
                    self._draft_trigger = evdev_key
                    self._seq_buf = ""
                    self._delay_buf = str(DEFAULT_STEP_DELAY)
                    self._seq_focus = True
                    self.phase = "steps"
                else:
                    self._error = f"Unknown key '{self._buf}'. Try: F1-F12, a-z, enter, esc, up..."
            elif ch == 27:
                self.phase = "name"
                self._buf = self._draft_name
            elif ch in (curses.KEY_BACKSPACE, 127):
                self._buf = self._buf[:-1]
            elif 32 <= ch < 127:
                self._buf += chr(ch)
            return

        if self.phase == "steps":
            if ch == 27:
                self.phase = None
            elif ch in (ord("\n"), 10, curses.KEY_ENTER):
                delay = (
                    int(self._delay_buf)
                    if self._delay_buf.isdigit()
                    else DEFAULT_STEP_DELAY
                )
                steps = _parse_sequence(self._seq_buf, delay)
                if not steps:
                    self._error = "Sequence is empty. Type at least one letter."
                    return
                macro = Macro(
                    id=str(uuid.uuid4()),
                    name=self._draft_name,
                    enabled=True,
                    trigger=self._draft_trigger,
                    interruptible=True,
                    steps=steps,
                )
                state["macros"].append(macro)
                save_macros()
                self._selected = len(state["macros"]) - 1
                self.phase = None
            elif ch == 9:  # Tab — switch between seq and delay fields
                self._seq_focus = not self._seq_focus
            elif ch in (curses.KEY_BACKSPACE, 127):
                if self._seq_focus:
                    self._seq_buf = self._seq_buf[:-1]
                else:
                    self._delay_buf = self._delay_buf[:-1]
            elif 32 <= ch < 127:
                c = chr(ch)
                if self._seq_focus:
                    if c.isalpha() or c.isdigit() or c in "{}-=":
                        self._seq_buf += c
                elif c.isdigit():
                    self._delay_buf += c
            return

        macros = state["macros"]
        if ch in (ord("n"), ord("N")):
            self.phase = "name"
            self._buf = ""
            self._draft_name = ""
            self._draft_trigger = ""
        elif ch == curses.KEY_UP:
            self._selected = max(0, self._selected - 1)
        elif ch == curses.KEY_DOWN:
            self._selected = min(len(macros) - 1, self._selected + 1)
        elif ch in (ord("d"), ord("D")) and macros:
            if 0 <= self._selected < len(macros):
                del macros[self._selected]
                self._selected = min(self._selected, max(0, len(macros) - 1))
                save_macros()
        elif ch in (ord("t"), ord("T")) and macros:
            if 0 <= self._selected < len(macros):
                macro = macros[self._selected]
                macro["enabled"] = not macro.get("enabled", True)
                save_macros()
        elif ch == ord(" ") and macros:
            if 0 <= self._selected < len(macros):
                macro = macros[self._selected]
                if macro["id"] not in state["macro_playing"]:
                    state["macro_playing"].add(macro["id"])
                    try:
                        _ = asyncio.get_running_loop().create_task(
                            self._play_macro(macro)
                        )
                    except RuntimeError:
                        state["macro_playing"].discard(macro["id"])

    def handle_mouse(self, x: int, y: int) -> None:
        if self.phase is not None:
            return

        if y == 0:
            if 2 <= x < 8:  # n new
                self.handle_input(ord("n"))
            elif 10 <= x < 20:  # d delete
                self.handle_input(ord("d"))
            elif 21 <= x < 31:  # t toggle
                self.handle_input(ord("t"))
            elif 32 <= x < 42:  # space play
                self.handle_input(ord(" "))
        elif y >= 3:
            idx = y - 3
            if 0 <= idx < len(state["macros"]):
                if self._selected == idx:
                    # Double click or click on selected -> Play
                    self.handle_input(ord(" "))
                else:
                    self._selected = idx

    def draw(self, win: curses.window) -> None:
        win.erase()
        canvas = Canvas(win)

        if self.phase == "name":
            self._draw_wizard_name(canvas, theme)
        elif self.phase == "trigger":
            self._draw_wizard_trigger(canvas, theme)
        elif self.phase == "steps":
            self._draw_wizard_steps(canvas, theme)
        else:
            self._draw_list(canvas, theme)

    # ── wizard screens ───────────────────────────────────────────────

    def _wizard_header(self, canvas: Canvas, theme: Any, step: int, title: str) -> None:
        _ = canvas.line(
            0,
            2,
            ("new macro", theme.accent(bold=True)),
            ("  ·  ", theme.muted()),
            (f"step {step}/3", theme.muted()),
            ("  ·  ", theme.muted()),
            (title, theme.accent(bold=True)),
        )
        canvas.hrule(1, theme.muted())

    def _draw_wizard_name(self, canvas: Canvas, theme: Any) -> None:
        self._wizard_header(canvas, theme, 1, "name")
        _ = canvas.line(
            3,
            4,
            ("Name  ", theme.muted()),
            (self._buf, curses.A_BOLD),
            ("▏", theme.accent(bold=True)),
        )
        self._draw_error(canvas, theme, 5)

    def _draw_wizard_trigger(self, canvas: Canvas, theme: Any) -> None:
        self._wizard_header(canvas, theme, 2, f'trigger for "{self._draft_name}"')
        _ = canvas.line(
            3,
            4,
            ("Trigger  ", theme.muted()),
            (self._buf, curses.A_BOLD),
            ("▏", theme.accent(bold=True)),
        )
        _ = canvas.line(
            5,
            4,
            ("accepts  ", theme.muted()),
            (
                "F1-F12  a-z  0-9  enter  space  tab  esc  up  down  left  right",
                theme.warn(),
            ),
        )
        self._draw_error(canvas, theme, 7)

    def _draw_wizard_steps(self, canvas: Canvas, theme: Any) -> None:
        self._wizard_header(canvas, theme, 3, f'sequence for "{self._draft_name}"')

        seq_focus = self._seq_focus
        seq_marker = "▸ " if seq_focus else "  "
        delay_marker = "  " if seq_focus else "▸ "

        _ = canvas.line(
            3,
            2,
            (seq_marker, theme.accent(bold=True) if seq_focus else theme.muted()),
            ("Sequence  ", theme.muted()),
            (
                self._seq_buf,
                curses.A_BOLD if seq_focus else curses.A_UNDERLINE,
            ),
            ("▏", theme.accent(bold=True) if seq_focus else theme.muted()),
        )
        _ = canvas.line(
            4,
            2,
            (delay_marker, theme.accent(bold=True) if not seq_focus else theme.muted()),
            ("Delay     ", theme.muted()),
            (
                self._delay_buf,
                curses.A_BOLD if not seq_focus else curses.A_UNDERLINE,
            ),
            ("▏", theme.accent(bold=True) if not seq_focus else theme.muted()),
            (" ms between steps", theme.muted()),
        )

        _ = canvas.line(
            6,
            4,
            ("letters and digits press directly; wrap specials in {}", theme.warn()),
        )
        _ = canvas.line(
            7,
            4,
            ("specials  ", theme.muted()),
            (
                "{F1}–{F12} {enter} {space} {tab} {esc} {up} {down} {left} {right} {click} {rclick}",
                theme.warn(),
            ),
        )
        _ = canvas.line(
            8, 4, ("example   ", theme.muted()), ("{F1}f1  →  F1, f, 1", theme.warn())
        )

        # Preview
        delay = (
            int(self._delay_buf) if self._delay_buf.isdigit() else DEFAULT_STEP_DELAY
        )
        steps = _parse_sequence(self._seq_buf, delay)
        if steps:
            _ = canvas.line(
                10, 2, ("preview", theme.accent(bold=True) | curses.A_UNDERLINE)
            )
            for i, step in enumerate(steps):
                row = 11 + i
                if row >= canvas.h - 1:
                    break
                label = step["value"] if step["kind"] == "key" else step["kind"]
                _ = canvas.line(
                    row,
                    4,
                    (f"{i + 1:>2}. ", theme.muted()),
                    (label, curses.A_BOLD),
                    (f"  {step['delay_ms']}ms", theme.muted()),
                )

        self._draw_error(canvas, theme, canvas.h - 2)

    def _draw_error(self, canvas: Canvas, theme: Any, row: int) -> None:
        if self._error and row < canvas.h:
            _ = canvas.line(
                row, 4, ("! ", theme.danger(bold=True)), (self._error, theme.danger())
            )

    # ── list screen ──────────────────────────────────────────────────

    def _draw_list(self, canvas: Canvas, theme: Any) -> None:
        _ = canvas.line(
            0,
            2,
            ("n", theme.accent(bold=True)),
            (" new   ", theme.muted()),
            ("d", theme.accent(bold=True)),
            (" delete   ", theme.muted()),
            ("t", theme.accent(bold=True)),
            (" toggle   ", theme.muted()),
            ("space", theme.accent(bold=True)),
            (" play   ", theme.muted()),
            ("↑↓", theme.accent(bold=True)),
            (" select", theme.muted()),
        )

        header = f"  {'Name':<18} {'Kind':<6} {'Trigger':<12} {'Steps':>5} {'Status':>8}"
        _ = canvas.line(
            2,
            0,
            (header, theme.muted() | curses.A_UNDERLINE),
        )

        macros = state["macros"]
        if not macros:
            _ = canvas.line(
                4,
                4,
                ("no macros yet — press ", theme.muted()),
                ("n", theme.accent(bold=True)),
                (" to create one", theme.muted()),
            )
            return

        for i, macro in enumerate(macros):
            row = 3 + i
            if row >= canvas.h - 1:
                break
            selected = i == self._selected
            enabled = macro.get("enabled", True)
            playing = macro["id"] in state["macro_playing"]
            trigger = (
                macro["trigger"].replace("KEY_", "") if macro["trigger"] else "(none)"
            )
            kind = macro.get("kind", "macro")[:4]

            dot: Chunk = ("●", theme.success(bold=True)) if playing else (" ", 0)
            base_attr = curses.A_REVERSE if selected else 0
            
            # Dim the text if disabled and not selected
            dim_attr = theme.muted() if not enabled and not selected else 0
            
            status_text = "  On" if enabled else " Off"
            status_attr = base_attr | (theme.success() if enabled and not selected else (theme.danger() if not enabled and not selected else 0))

            _ = canvas.line(
                row,
                0,
                (" ", base_attr),
                dot,
                ("  ", base_attr),
                (
                    f"{macro['name']:<18}",
                    base_attr | dim_attr | (curses.A_BOLD if selected else 0),
                ),
                (" ", base_attr),
                (f"{kind:<6}", base_attr | dim_attr | (theme.accent() if not selected and enabled else 0)),
                (" ", base_attr),
                (f"{trigger:<12}", base_attr | dim_attr | (theme.warn() if not selected and enabled else 0)),
                (" ", base_attr),
                (f"{len(macro['steps']):>5}", base_attr | dim_attr),
                (" ", base_attr),
                (f"{status_text:>8}", status_attr),
            )

    async def _record_mouse_click_async(self, key_name: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "getmouselocation", "--shell",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            m_out_raw, _ = await proc.communicate()
            m_out = m_out_raw.decode()
            
            m_data = {}
            for line in m_out.strip().split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    m_data[k] = v
            
            mx, my, mwid = int(m_data.get("X", 0)), int(m_data.get("Y", 0)), m_data.get("WINDOW")
            
            if mwid:
                try:
                    proc_search = await asyncio.create_subprocess_exec(
                        "xdotool", "search", "--name", "DarkAges Linux Tool",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    own_wids_raw, _ = await proc_search.communicate()
                    own_wids = own_wids_raw.decode().strip().split("\n")
                    if mwid in own_wids:
                        state["recording_mouse"] = True
                        return
                except:
                    pass
                
                proc_geom = await asyncio.create_subprocess_exec(
                    "xdotool", "getwindowgeometry", "--shell", mwid,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                w_out_raw, _ = await proc_geom.communicate()
                w_out = w_out_raw.decode()
                
                w_data = {}
                for line in w_out.strip().split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        w_data[k] = v
                
                wx, wy = int(w_data.get("X", 0)), int(w_data.get("Y", 0))
                kind = "mouse_left" if "LEFT" in key_name or "0" in key_name or "MOUSE" in key_name else "mouse_right"
                state["captured_click"] = {
                    "kind": kind,
                    "x": mx - wx,
                    "y": my - wy
                }
        except Exception as e:
            state["last_event"] = f"ERR: {str(e)}"
