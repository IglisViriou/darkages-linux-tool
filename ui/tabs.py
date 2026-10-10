from __future__ import annotations
import curses
import time
from state import state
from features.macro import MacroFeature
from ui import theme
from ui.canvas import Canvas, Chunk

TAB_NAMES = ["Home", "Butterwalk", "Spacebar", "Controller", "Macros"]
APP_TITLE = "DarkAges Linux Tool"

_FOOTER = "q quit  ·  Tab switch  ·  Mouse supported"

_MACRO_WIZARD_FOOTER = "Enter confirm  ·  Esc cancel  ·  Tab switch field"


# ── chrome ────────────────────────────────────────────────────────────────


def _draw_title_bar(canvas: Canvas) -> None:
    bar_attr = theme.bar(bold=True)
    canvas.fill(0, bar_attr)
    _ = canvas.put(0, 2, APP_TITLE, bar_attr)


def _draw_tab_strip(canvas: Canvas, active: int) -> None:
    col = 2
    for i, name in enumerate(TAB_NAMES):
        label = f"  {i + 1}  {name}  "
        if i == active:
            col = canvas.put(1, col, label, theme.accent(bold=True) | curses.A_REVERSE)
        else:
            col = canvas.put(1, col, label, theme.muted())
        col += 1
    canvas.hrule(2, theme.muted())


def _draw_footer(canvas: Canvas, hint: str) -> None:
    row = canvas.h - 1
    # Left: Hotkeys
    _ = canvas.put(row, 2, hint, theme.muted())

    # Right: Status & Client
    if state["active"]:
        status: list[Chunk] = [
            ("● ", theme.success(bold=True)),
            ("ACTIVE", theme.success(bold=True)),
        ]
    else:
        status = [("○ ", theme.muted()), ("idle", theme.muted())]

    _ = canvas.right(
        row,
        *status,
        ("  ·  ", theme.muted()),
        (state["client_name"], theme.muted(bold=True)),
    )


# ── tabs ──────────────────────────────────────────────────────────────────


def _pill(on: bool, label_on: str = "ON", label_off: str = "OFF") -> list[Chunk]:
    if on:
        return [("● ", theme.success(bold=True)), (label_on, theme.success(bold=True))]
    return [("○ ", theme.danger(bold=True)), (label_off, theme.danger(bold=True))]


def _field(canvas: Canvas, row: int, label: str, *value: Chunk) -> None:
    _ = canvas.line(row, 4, (f"{label:<14}", theme.muted()), *value)


def _draw_main(canvas: Canvas, top: int) -> None:
    row = top + 1
    _field(canvas, row, "Client", (state["client_name"], curses.A_BOLD))
    row += 1
    _field(
        canvas,
        row,
        "Search titles",
        (", ".join(state["window_hooks"]), theme.muted()),
    )
    row += 1

    if state["active"]:
        _field(
            canvas,
            row,
            "Status",
            ("● ", theme.success(bold=True)),
            ("ACTIVE", theme.success(bold=True)),
        )
    else:
        _field(
            canvas,
            row,
            "Status",
            ("○ ", theme.danger(bold=True)),
            ("inactive", theme.danger()),
            ("  (focus Unora to arm)", theme.muted()),
        )
    row += 2

    _field(
        canvas,
        row,
        "Macros loaded",
        (str(len(state["macros"])), curses.A_BOLD),
    )
    row += 1
    _field(
        canvas,
        row,
        "Butterwalk",
        *_pill(state["butterwalk"]),
    )
    row += 1
    _field(
        canvas,
        row,
        "Space Repeat",
        *_pill(state["space_enabled"]),
    )
    row += 1
    _field(
        canvas,
        row,
        "Controller",
        *_pill(state["controller_enabled"]),
    )
    row += 2
    
    _field(canvas, row, "Active Hooks", (", ".join(state["window_hooks"]), curses.A_BOLD))


def _draw_butterwalk(canvas: Canvas, top: int) -> None:
    row = top + 1
    _field(
        canvas, row, "Butterwalk", *_pill(state["butterwalk"]), ("  [b]", theme.muted())
    )
    row += 2

    _field(
        canvas,
        row,
        "Level",
        (str(state["multiplier"]), theme.warn(bold=True)),
        ("  [+/- on physical keys]", theme.muted()),
    )
    row += 2

    if state["zxcv_enabled"]:
        _field(
            canvas,
            row,
            "ZXCV",
            ("● ", theme.success(bold=True)),
            ("enabled", theme.success(bold=True)),
            ("  [m]", theme.muted()),
        )
    else:
        _field(
            canvas,
            row,
            "ZXCV",
            ("○ ", theme.muted(bold=True)),
            ("disabled", theme.muted()),
            ("  (arrows only)", theme.muted()),
            ("  [m]", theme.muted()),
        )
    row += 2

    bind_hint = "  (PRESS KEYS...)" if state.get("listening_for_hotkey") == "butterwalk" else "  [k]"
    _field(
        canvas,
        row,
        "Hotkey",
        (state["butterwalk_hotkey"], theme.accent(bold=True)),
        (bind_hint, theme.warn() if state.get("listening_for_hotkey") == "butterwalk" else theme.muted()),
    )
    row += 2

    keys = ", ".join(k.replace("KEY_", "") for k in list(state["physical_keys_down"])) or "—"
    _field(canvas, row, "Input", (keys, curses.A_BOLD))


def _handle_butterwalk_input(ch: int) -> None:
    if ch in (ord("b"), ord("B")):
        state["butterwalk"] = not state["butterwalk"]
    elif ch in (ord("m"), ord("M")):
        state["zxcv_enabled"] = not state["zxcv_enabled"]
        from state import save_config
        save_config()
    elif ch in (ord("k"), ord("K")):
        state["listening_for_hotkey"] = "butterwalk"
        state["last_event"] = "Press keys to bind Butterwalk hotkey..."
    elif ch == 27 and state.get("listening_for_hotkey") == "butterwalk":
        state["listening_for_hotkey"] = None


def _draw_spacebar(canvas: Canvas, top: int) -> None:
    row = top + 1
    _field(
        canvas,
        row,
        "Space Repeat",
        *_pill(state["space_enabled"]),
        ("  [s]", theme.muted()),
    )
    row += 2

    _field(
        canvas,
        row,
        "Multiplier",
        (str(state["space_multiplier"]), theme.warn(bold=True)),
        ("  [+/-]", theme.muted()),
    )
    row += 2

    bind_hint = "  (PRESS KEYS...)" if state.get("listening_for_hotkey") == "space" else "  [k]"
    _field(
        canvas,
        row,
        "Hotkey",
        (state["space_hotkey"], theme.accent(bold=True)),
        (bind_hint, theme.warn() if state.get("listening_for_hotkey") == "space" else theme.muted()),
    )
    row += 2

    keys = ", ".join(k.replace("KEY_", "") for k in list(state["physical_keys_down"])) or "—"
    _field(canvas, row, "Input", (keys, curses.A_BOLD))


def _handle_spacebar_input(ch: int) -> None:
    if ch in (ord("s"), ord("S")):
        state["space_enabled"] = not state["space_enabled"]
        from state import save_config
        save_config()
    elif ch in (ord("-"), ord("_")):
        state["space_multiplier"] = max(1, state["space_multiplier"] - 1)
        from state import save_config
        save_config()
    elif ch in (ord("+"), ord("=")):
        state["space_multiplier"] = min(5, state["space_multiplier"] + 1)
        from state import save_config
        save_config()
    elif ch in (ord("k"), ord("K")):
        state["listening_for_hotkey"] = "space"
        state["last_event"] = "Press keys to bind Spacebar hotkey..."
    elif ch == 27 and state.get("listening_for_hotkey") == "space":
        state["listening_for_hotkey"] = None


def _draw_controller(canvas: Canvas, top: int) -> None:
    row = top + 1
    _field(
        canvas,
        row,
        "Controller",
        *_pill(state["controller_enabled"]),
        ("  [c]", theme.muted()),
    )
    row += 2

    if state["dpad_enabled"]:
        _field(
            canvas,
            row,
            "DPAD",
            ("● ", theme.success(bold=True)),
            ("enabled", theme.success(bold=True)),
            ("  [d]", theme.muted()),
        )
    else:
        _field(
            canvas,
            row,
            "DPAD",
            ("○ ", theme.muted(bold=True)),
            ("disabled", theme.muted()),
            ("  [d]", theme.muted()),
        )
    row += 2

    if state["joystick_enabled"]:
        _field(
            canvas,
            row,
            "Left Stick",
            ("● ", theme.success(bold=True)),
            ("enabled", theme.success(bold=True)),
            ("  [j]", theme.muted()),
        )
    else:
        _field(
            canvas,
            row,
            "Left Stick",
            ("○ ", theme.muted(bold=True)),
            ("disabled", theme.muted()),
            ("  [j]", theme.muted()),
        )
    row += 2

    if state["right_stick_mouse_enabled"]:
        _field(
            canvas,
            row,
            "RS Mouse",
            ("● ", theme.success(bold=True)),
            ("enabled", theme.success(bold=True)),
            ("  [r]", theme.muted()),
        )
    else:
        _field(
            canvas,
            row,
            "RS Mouse",
            ("○ ", theme.muted(bold=True)),
            ("disabled", theme.muted()),
            ("  [r]", theme.muted()),
        )
    row += 2

    _field(
        canvas,
        row,
        "Sensitivity",
        (f"{state['mouse_sensitivity']}%", theme.warn(bold=True)),
        (f" of {state['mouse_dpi']} DPI", theme.muted()),
        ("  [[/]]", theme.muted()),
    )
    row += 2

    bind_hint = "  (PRESS KEYS...)" if state.get("listening_for_hotkey") == "controller" else "  [k]"
    _field(
        canvas,
        row,
        "Hotkey",
        (state["controller_hotkey"], theme.accent(bold=True)),
        (bind_hint, theme.warn() if state.get("listening_for_hotkey") == "controller" else theme.muted()),
    )
    row += 2

    keys = ", ".join(k.replace("KEY_", "") for k in list(state["physical_keys_down"])) or "—"
    rx, ry = state.get("right_stick_x", 0.0), state.get("right_stick_y", 0.0)
    stick_info = f" | RS: ({rx:+.2f}, {ry:+.2f})" if (rx != 0.0 or ry != 0.0) else ""
    _field(canvas, row, "Input", (f"{keys}{stick_info}", curses.A_BOLD))


def _handle_controller_input(ch: int) -> None:
    if ch in (ord("c"), ord("C")):
        state["controller_enabled"] = not state["controller_enabled"]
        from state import save_config
        save_config()
    elif ch in (ord("d"), ord("D")):
        state["dpad_enabled"] = not state["dpad_enabled"]
        from state import save_config
        save_config()
    elif ch in (ord("j"), ord("J")):
        state["joystick_enabled"] = not state["joystick_enabled"]
        from state import save_config
        save_config()
    elif ch in (ord("r"), ord("R")):
        state["right_stick_mouse_enabled"] = not state["right_stick_mouse_enabled"]
        from state import save_config
        save_config()
    elif ch == ord("["):
        state["mouse_sensitivity"] = max(1, state["mouse_sensitivity"] - 5)
        from state import save_config
        save_config()
    elif ch == ord("]"):
        state["mouse_sensitivity"] = min(100, state["mouse_sensitivity"] + 5)
        from state import save_config
        save_config()
    elif ch in (ord("k"), ord("K")):
        state["listening_for_hotkey"] = "controller"
        state["last_event"] = "Press keys to bind Controller hotkey..."
    elif ch == 27 and state.get("listening_for_hotkey") == "controller":
        state["listening_for_hotkey"] = None


# ── main loop ─────────────────────────────────────────────────────────────


def _too_small(canvas: Canvas) -> bool:
    return canvas.h < 6 or canvas.w < 32


def _get_tab_at(x: int, y: int) -> int | None:
    if y != 1:
        return None
    col = 2
    for i, name in enumerate(TAB_NAMES):
        label = f"  {i + 1}  {name}  "
        width = len(label)
        if col <= x < col + width:
            return i
        col += width + 1
    return None


def draw_ui(stdscr: curses.window, macro_feature: MacroFeature) -> None:
    _ = curses.curs_set(0)
    _ = curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    active = 0

    while state["running"]:
        stdscr.erase()
        canvas = Canvas(stdscr)

        if _too_small(canvas):
            _ = canvas.put(0, 0, "terminal too small", theme.warn())
            stdscr.refresh()
            time.sleep(0.1)
            _ = _consume_key(stdscr)
            continue

        _draw_title_bar(canvas)
        _draw_tab_strip(canvas, active)

        content_top = 3
        content_h = canvas.h - content_top - 1

        if active == 0:
            _draw_main(canvas, content_top)
        elif active == 1:
            _draw_butterwalk(canvas, content_top)
        elif active == 2:
            _draw_spacebar(canvas, content_top)
        elif active == 3:
            _draw_controller(canvas, content_top)
        elif active == 4 and content_h > 0:
            try:
                sub = stdscr.subwin(content_h, canvas.w, content_top, 0)
                macro_feature.draw(sub)
            except curses.error:
                pass

        in_macro_input = active == 4 and macro_feature.phase is not None
        _draw_footer(canvas, _MACRO_WIZARD_FOOTER if in_macro_input else _FOOTER)

        stdscr.refresh()

        ch = _consume_key(stdscr)

        if ch == curses.KEY_MOUSE:
            try:
                _, x, y, _, bstate = curses.getmouse()
                if bstate & curses.BUTTON1_CLICKED:
                    tab = _get_tab_at(x, y)
                    if tab is not None:
                        active = tab
                    elif active == 1:
                        if y == content_top + 1:
                            state["butterwalk"] = not state["butterwalk"]
                        elif y == content_top + 5:
                            state["zxcv_enabled"] = not state["zxcv_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 7:
                            state["listening_for_hotkey"] = "butterwalk"
                            state["last_event"] = "Press keys to bind Butterwalk hotkey..."
                    elif active == 2:
                        if y == content_top + 1:
                            state["space_enabled"] = not state["space_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 5:
                            state["listening_for_hotkey"] = "space"
                            state["last_event"] = "Press keys to bind Spacebar hotkey..."
                    elif active == 3:
                        if y == content_top + 1:
                            state["controller_enabled"] = not state["controller_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 3:
                            state["dpad_enabled"] = not state["dpad_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 5:
                            state["joystick_enabled"] = not state["joystick_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 7:
                            state["right_stick_mouse_enabled"] = not state["right_stick_mouse_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 11:
                            state["listening_for_hotkey"] = "controller"
                            state["last_event"] = "Press keys to bind Controller hotkey..."
                    elif active == 4:
                        macro_feature.handle_mouse(x, y - content_top)
            except curses.error:
                pass
        elif ch == ord("q") and not in_macro_input:
            state["running"] = False
        elif in_macro_input:
            macro_feature.handle_input(ch)
        elif ch == ord("1"):
            active = 0
        elif ch == ord("2"):
            active = 1
        elif ch == ord("3"):
            active = 2
        elif ch == ord("4"):
            active = 3
        elif ch == ord("5"):
            active = 4
        elif ch == 9:  # Tab
            active = (active + 1) % len(TAB_NAMES)
        elif active == 1:
            _handle_butterwalk_input(ch)
        elif active == 2:
            _handle_spacebar_input(ch)
        elif active == 3:
            _handle_controller_input(ch)
        elif active == 4:
            macro_feature.handle_input(ch)

        time.sleep(0.05)


def _consume_key(stdscr: curses.window) -> int:
    try:
        return stdscr.getch()
    except Exception:
        return -1
