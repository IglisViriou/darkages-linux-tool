from __future__ import annotations
import curses
import time
from state import state
from features.macro import MacroFeature
from ui import theme
from ui.canvas import Canvas, Chunk

TAB_NAMES = ["Home", "Butterwalk", "Continuous Assail", "Controller", "Macros", "Autofollowing", "Credits"]
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
        "Multiplier",
        (f"{state['multiplier']}x", theme.warn(bold=True)),
        ("  [+/-]", theme.muted()),
        (" (Repeats per trigger at selected ms)", theme.muted()),
    )
    row += 2

    _field(
        canvas,
        row,
        "Repeat Speed",
        (f"{state['butterwalk_delay_ms']} ms", theme.warn(bold=True)),
        ("  [[/]]", theme.muted()),
        (" (Wait time in ms between repeats)", theme.muted()),
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
    elif ch in (ord("-"), ord("_")):
        state["multiplier"] = max(1, state["multiplier"] - 1)
        from state import save_config
        save_config()
    elif ch in (ord("+"), ord("=")):
        state["multiplier"] = min(5, state["multiplier"] + 1)
        from state import save_config
        save_config()
    elif ch == ord("["):
        state["butterwalk_delay_ms"] = max(1, state["butterwalk_delay_ms"] - 5)
        from state import save_config
        save_config()
    elif ch == ord("]"):
        state["butterwalk_delay_ms"] = min(100, state["butterwalk_delay_ms"] + 5)
        from state import save_config
        save_config()
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
        "Continuous Assail",
        *_pill(state["space_enabled"]),
        ("  [s]", theme.muted()),
    )
    row += 2

    _field(
        canvas,
        row,
        "Multiplier",
        (f"{state['space_multiplier']}x", theme.warn(bold=True)),
        ("  [+/-]", theme.muted()),
        (" (Repeats per trigger at selected ms)", theme.muted()),
    )
    row += 2

    _field(
        canvas,
        row,
        "Repeat Speed",
        (f"{state['space_delay_ms']} ms", theme.warn(bold=True)),
        ("  [[/]]", theme.muted()),
        (" (Wait time in ms between repeats)", theme.muted()),
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
    elif ch == ord("["):
        state["space_delay_ms"] = max(1, state["space_delay_ms"] - 5)
        from state import save_config
        save_config()
    elif ch == ord("]"):
        state["space_delay_ms"] = min(100, state["space_delay_ms"] + 5)
        from state import save_config
        save_config()
    elif ch in (ord("k"), ord("K")):
        state["listening_for_hotkey"] = "space"
        state["last_event"] = "Press keys to bind Continuous Assail hotkey..."
    elif ch == 27 and state.get("listening_for_hotkey") == "space":
        state["listening_for_hotkey"] = None


_TUI_CTRL_INDEX = 0
_TUI_CTRL_LAYER = "base"


def _get_flat_controller_inputs() -> list[tuple[str, str]]:
    from features.controller import CONTROLLER_GROUPS
    items: list[tuple[str, str]] = []
    for _, group_items in CONTROLLER_GROUPS:
        items.extend(group_items)
    return items


def _draw_controller(canvas: Canvas, top: int) -> None:
    import input_hub
    from features.controller import format_binding, is_layer_active

    # Process captured controller output key if recorded in TUI
    captured = state.get("captured_hotkey")
    if captured and captured[0] == "controller_output":
        _, combo = captured
        state["captured_hotkey"] = None
        flat = _get_flat_controller_inputs()
        if 0 <= _TUI_CTRL_INDEX < len(flat):
            inp_code = flat[_TUI_CTRL_INDEX][0]
            bmap_key = "controller_layer_bindings" if _TUI_CTRL_LAYER == "layer" else "controller_bindings"
            state[bmap_key][inp_code] = {"type": "key", "value": combo}
            from state import save_config
            save_config()

    row = top + 1
    ctrl_count = input_hub.get_controller_count()
    ctrl_names = input_hub.get_controller_names()
    dev_str = f"  ({ctrl_count} pad: {', '.join(ctrl_names[:1])})" if ctrl_count > 0 else "  (no pad detected)"
    _field(
        canvas,
        row,
        "Controller",
        *_pill(state["controller_enabled"]),
        ("  [c]", theme.muted()),
        (dev_str, theme.success() if ctrl_count > 0 else theme.muted()),
    )
    row += 1

    dpad_chunk = ("enabled [d]", theme.success(bold=True)) if state["dpad_enabled"] else ("disabled [d]", theme.muted())
    ls_chunk = (f"enabled ({state.get('left_stick_deadzone', 25)}%) [j]", theme.success(bold=True)) if state["joystick_enabled"] else ("disabled [j]", theme.muted())
    rs_chunk = (f"enabled ({state['mouse_sensitivity']}% / DZ {state.get('right_stick_deadzone', 12)}%) [r]", theme.success(bold=True)) if state["right_stick_mouse_enabled"] else ("disabled [r]", theme.muted())
    _field(
        canvas,
        row,
        "Inputs",
        ("DPAD: ", theme.muted()), dpad_chunk,
        ("  ·  LS: ", theme.muted()), ls_chunk,
        ("  ·  RS Mouse: ", theme.muted()), rs_chunk,
        ("  [[/]] sens", theme.muted()),
    )
    row += 1

    bind_hint = " (PRESS KEYS...)" if state.get("listening_for_hotkey") == "controller" else " [k]"
    _field(
        canvas,
        row,
        "Hotkey",
        (state["controller_hotkey"], theme.accent(bold=True)),
        (bind_hint, theme.warn() if state.get("listening_for_hotkey") == "controller" else theme.muted()),
        ("  ·  Presets: [p] Dark Ages Default  [m] Movement Only", theme.muted()),
    )
    row += 1

    layer_str = "BASE LAYER" if _TUI_CTRL_LAYER == "base" else "MODIFIER LAYER (CHORD)"
    live_layer = "  [MODIFIER HELD]" if is_layer_active() else ""
    _field(
        canvas,
        row,
        "Edit Layer",
        (layer_str, theme.warn(bold=True) if _TUI_CTRL_LAYER == "layer" else theme.accent(bold=True)),
        ("  [l] toggle layer  ·  [↑/↓] select  ·  [Enter] bind key  ·  [b] cycle mouse/layer  ·  [u] unbind", theme.muted()),
        (live_layer, theme.success(bold=True)),
    )
    row += 2

    flat = _get_flat_controller_inputs()
    bmap = state.get("controller_layer_bindings" if _TUI_CTRL_LAYER == "layer" else "controller_bindings", {})
    max_rows = max(3, canvas.h - row - 2)
    start_idx = max(0, min(_TUI_CTRL_INDEX - max_rows // 2, len(flat) - max_rows))
    visible = flat[start_idx : start_idx + max_rows]

    for idx_offset, (inp_code, inp_label) in enumerate(visible):
        actual_idx = start_idx + idx_offset
        is_sel = actual_idx == _TUI_CTRL_INDEX
        binding = bmap.get(inp_code)
        b_text = format_binding(binding)
        is_Wait = is_sel and state.get("listening_for_hotkey") == "controller_output"
        if is_Wait:
            b_text = "PRESS KEY COMBO..."
        prefix = "▸ " if is_sel else "  "
        _ = canvas.line(
            row,
            4,
            (prefix, theme.accent(bold=True) if is_sel else theme.muted()),
            (f"{inp_label:<28}", curses.A_BOLD if is_sel else theme.muted()),
            (b_text, theme.warn(bold=True) if is_Wait else (theme.accent(bold=True) if binding and binding.get("type", "none") != "none" else theme.muted())),
        )
        row += 1


def _handle_controller_input(ch: int) -> None:
    global _TUI_CTRL_INDEX, _TUI_CTRL_LAYER
    from state import save_config, get_default_controller_bindings, get_default_layer_bindings, get_minimal_controller_bindings

    flat = _get_flat_controller_inputs()
    bmap_key = "controller_layer_bindings" if _TUI_CTRL_LAYER == "layer" else "controller_bindings"

    if ch == 27 and state.get("listening_for_hotkey") in ("controller", "controller_output"):
        state["listening_for_hotkey"] = None
        return

    if ch in (ord("c"), ord("C")):
        state["controller_enabled"] = not state["controller_enabled"]
        save_config()
    elif ch in (ord("d"), ord("D")):
        state["dpad_enabled"] = not state["dpad_enabled"]
        save_config()
    elif ch in (ord("j"), ord("J")):
        state["joystick_enabled"] = not state["joystick_enabled"]
        save_config()
    elif ch in (ord("r"), ord("R")):
        state["right_stick_mouse_enabled"] = not state["right_stick_mouse_enabled"]
        save_config()
    elif ch == ord("["):
        state["mouse_sensitivity"] = max(1, state["mouse_sensitivity"] - 5)
        save_config()
    elif ch == ord("]"):
        state["mouse_sensitivity"] = min(100, state["mouse_sensitivity"] + 5)
        save_config()
    elif ch in (ord("k"), ord("K")):
        state["listening_for_hotkey"] = "controller"
        state["last_event"] = "Press keys to bind Controller hotkey..."
    elif ch in (ord("l"), ord("L")):
        _TUI_CTRL_LAYER = "layer" if _TUI_CTRL_LAYER == "base" else "base"
    elif ch in (ord("p"), ord("P")):
        state["controller_bindings"] = get_default_controller_bindings()
        state["controller_layer_bindings"] = get_default_layer_bindings()
        save_config()
    elif ch in (ord("m"), ord("M")):
        state["controller_bindings"] = get_minimal_controller_bindings()
        state["controller_layer_bindings"] = {}
        save_config()
    elif ch == curses.KEY_UP:
        _TUI_CTRL_INDEX = max(0, _TUI_CTRL_INDEX - 1)
    elif ch == curses.KEY_DOWN:
        _TUI_CTRL_INDEX = min(len(flat) - 1, _TUI_CTRL_INDEX + 1)
    elif ch in (10, 13, curses.KEY_ENTER):
        state["listening_for_hotkey"] = "controller_output"
    elif ch in (ord("u"), ord("U")):
        if 0 <= _TUI_CTRL_INDEX < len(flat):
            inp_code = flat[_TUI_CTRL_INDEX][0]
            state[bmap_key][inp_code] = {"type": "none", "value": ""}
            save_config()
    elif ch in (ord("b"), ord("B")):
        if 0 <= _TUI_CTRL_INDEX < len(flat):
            inp_code = flat[_TUI_CTRL_INDEX][0]
            cycle = [
                {"type": "mouse", "value": "left"},
                {"type": "mouse", "value": "right"},
                {"type": "mouse", "value": "middle"},
                {"type": "mouse", "value": "scroll_up"},
                {"type": "mouse", "value": "scroll_down"},
                {"type": "layer_hold", "value": "1"},
            ]
            curr = state[bmap_key].get(inp_code, {"type": "none", "value": ""})
            next_b = cycle[0]
            for i, item in enumerate(cycle):
                if item.get("type") == curr.get("type") and item.get("value") == curr.get("value"):
                    next_b = cycle[(i + 1) % len(cycle)]
                    break
            state[bmap_key][inp_code] = next_b
            save_config()


def _draw_autofollowing(canvas: Canvas, top: int) -> None:
    row = top + 2
    canvas.put(row, 4, "Autofollowing Features will not be added to DALT.", theme.warn(bold=True))
    row += 2
    canvas.put(row, 4, "Please use an alternative program to control autofollowing.", theme.muted())
    row += 2
    canvas.put(row, 4, "DALT is not intended to be used on inactive windows, hence no auto-following and no looped macros without holding your hotkey.", theme.muted())
    row += 2
    canvas.put(row, 4, "The only reason this tab exists is solely so I don't get messages asking for this feature.", theme.muted())


def _draw_credits(canvas: Canvas, top: int) -> None:
    row = top + 2
    canvas.put(row, 4, "DALT is brought to you by the following Aislings", theme.warn(bold=True))
    row += 2
    canvas.put(row, 4, """Initial Coding and Setup, Initial Macro and Butterwalk implementation: Phever - https://github.com/phever
GUI Implementation and Troubleshooting: Aon - https://github.com/FreyaNile
Feature implementation, Optimization, and Polishing: Iglis - https://github.com/IglisViriou""", theme.muted())


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
        elif active == 5:
            _draw_autofollowing(canvas, content_top)
        elif active == 6:
            _draw_credits(canvas, content_top)

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
                        elif y == content_top + 3:
                            state["multiplier"] = (state["multiplier"] % 5) + 1
                            from state import save_config
                            save_config()
                        elif y == content_top + 5:
                            delays = [5, 10, 25, 50, 100]
                            curr = state["butterwalk_delay_ms"]
                            next_delay = delays[0]
                            for d in delays:
                                if d > curr:
                                    next_delay = d
                                    break
                            state["butterwalk_delay_ms"] = next_delay
                            from state import save_config
                            save_config()
                        elif y == content_top + 7:
                            state["zxcv_enabled"] = not state["zxcv_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 9:
                            state["listening_for_hotkey"] = "butterwalk"
                            state["last_event"] = "Press keys to bind Butterwalk hotkey..."
                    elif active == 2:
                        if y == content_top + 1:
                            state["space_enabled"] = not state["space_enabled"]
                            from state import save_config
                            save_config()
                        elif y == content_top + 3:
                            state["space_multiplier"] = (state["space_multiplier"] % 5) + 1
                            from state import save_config
                            save_config()
                        elif y == content_top + 5:
                            delays = [5, 10, 25, 50, 100]
                            curr = state["space_delay_ms"]
                            next_delay = delays[0]
                            for d in delays:
                                if d > curr:
                                    next_delay = d
                                    break
                            state["space_delay_ms"] = next_delay
                            from state import save_config
                            save_config()
                        elif y == content_top + 7:
                            state["listening_for_hotkey"] = "space"
                            state["last_event"] = "Press keys to bind Continuous Assail hotkey..."
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
        elif ch == ord("6"):
            active = 5
        elif ch == ord("7"):
            active = 6
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
