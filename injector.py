import asyncio
import string
from evdev import ecodes
import input_hub

# Mapping of xdotool key names to evdev keycodes
XKEY_TO_EVDEV = {
    # Arrows
    "left": ecodes.KEY_LEFT,
    "right": ecodes.KEY_RIGHT,
    "up": ecodes.KEY_UP,
    "down": ecodes.KEY_DOWN,
    # Common names
    "space": ecodes.KEY_SPACE,
    "return": ecodes.KEY_ENTER,
    "enter": ecodes.KEY_ENTER,
    "tab": ecodes.KEY_TAB,
    "escape": ecodes.KEY_ESC,
    "esc": ecodes.KEY_ESC,
    "backspace": ecodes.KEY_BACKSPACE,
    "delete": ecodes.KEY_DELETE,
    "del": ecodes.KEY_DELETE,
    "insert": ecodes.KEY_INSERT,
    "ins": ecodes.KEY_INSERT,
    "home": ecodes.KEY_HOME,
    "end": ecodes.KEY_END,
    "pageup": ecodes.KEY_PAGEUP,
    "pgup": ecodes.KEY_PAGEUP,
    "pagedown": ecodes.KEY_PAGEDOWN,
    "pgdn": ecodes.KEY_PAGEDOWN,
    "prior": ecodes.KEY_PAGEUP,
    "next": ecodes.KEY_PAGEDOWN,
    "minus": ecodes.KEY_MINUS,
    "-": ecodes.KEY_MINUS,
    "equal": ecodes.KEY_EQUAL,
    "=": ecodes.KEY_EQUAL,
    "grave": ecodes.KEY_GRAVE,
    "asciitilde": ecodes.KEY_GRAVE,
    "tilde": ecodes.KEY_GRAVE,
    "`": ecodes.KEY_GRAVE,
    # Modifiers
    "shift": ecodes.KEY_LEFTSHIFT,
    "leftshift": ecodes.KEY_LEFTSHIFT,
    "rightshift": ecodes.KEY_RIGHTSHIFT,
    "ctrl": ecodes.KEY_LEFTCTRL,
    "control": ecodes.KEY_LEFTCTRL,
    "leftctrl": ecodes.KEY_LEFTCTRL,
    "rightctrl": ecodes.KEY_RIGHTCTRL,
    "alt": ecodes.KEY_LEFTALT,
    "leftalt": ecodes.KEY_LEFTALT,
    "rightalt": ecodes.KEY_RIGHTALT,
}

# Add standard letters, digits, and function keys dynamically
for i in range(1, 13):
    XKEY_TO_EVDEV[f"f{i}"] = getattr(ecodes, f"KEY_F{i}", None)

for i in range(10):
    XKEY_TO_EVDEV[str(i)] = getattr(ecodes, f"KEY_{i}", None)

for c in string.ascii_lowercase:
    XKEY_TO_EVDEV[c] = getattr(ecodes, f"KEY_{c.upper()}", None)


def _resolve_key_codes(key_name: str) -> tuple[list[int], str]:
    """Resolve a single key or 'mod + key' combo into evdev keycodes and an xdotool fallback string."""
    raw = key_name.strip()
    if "+" in raw and len(raw) > 1:
        parts = [p.strip() for p in raw.split("+") if p.strip()]
    else:
        parts = [raw]

    codes: list[int] = []
    xdotool_parts: list[str] = []
    for p in parts:
        p_lower = p.lower()
        if p_lower in ("~", "asciitilde"):
            if ecodes.KEY_LEFTSHIFT not in codes:
                codes.append(ecodes.KEY_LEFTSHIFT)
            codes.append(ecodes.KEY_GRAVE)
            xdotool_parts.append("asciitilde")
            continue

        if len(p) == 1 and p.isupper():
            if ecodes.KEY_LEFTSHIFT not in codes:
                codes.append(ecodes.KEY_LEFTSHIFT)
        code = XKEY_TO_EVDEV.get(p_lower)
        if code is None:
            return [], "+".join(parts)
        if code not in codes:
            codes.append(code)
        xdotool_parts.append(p)

    return codes, "+".join(xdotool_parts)


async def key(key_name: str, hold_s: float = 0.004, gap_s: float = 0.002) -> None:
    codes, xdo_spec = _resolve_key_codes(key_name)
    # Try using virtual input (uinput) first for high performance and low latency
    if input_hub._uinput is not None and codes:
        try:
            for c in codes:
                input_hub._uinput.write(ecodes.EV_KEY, c, 1)
            input_hub._uinput.syn()
            # Fast pulse hold ensures the game registers key down without stalling the macro
            if hold_s > 0:
                await asyncio.sleep(hold_s)
            
            for c in reversed(codes):
                input_hub._uinput.write(ecodes.EV_KEY, c, 0)
            input_hub._uinput.syn()
            # Inter-key gap ensures consecutive identical keys register distinctly
            if gap_s > 0:
                await asyncio.sleep(gap_s)
            return
        except Exception:
            pass  # Fallback to xdotool if writing to uinput fails

    # Fallback to xdotool
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "key", xdo_spec,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def key_down(key_name: str) -> None:
    codes, xdo_spec = _resolve_key_codes(key_name)
    if input_hub._uinput is not None and codes:
        try:
            for c in codes:
                input_hub._uinput.write(ecodes.EV_KEY, c, 1)
            input_hub._uinput.syn()
            return
        except Exception:
            pass

    proc = await asyncio.create_subprocess_exec(
        "xdotool", "keydown", xdo_spec,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def key_up(key_name: str) -> None:
    codes, xdo_spec = _resolve_key_codes(key_name)
    if input_hub._uinput is not None and codes:
        try:
            for c in reversed(codes):
                input_hub._uinput.write(ecodes.EV_KEY, c, 0)
            input_hub._uinput.syn()
            return
        except Exception:
            pass

    proc = await asyncio.create_subprocess_exec(
        "xdotool", "keyup", xdo_spec,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def mouse_down(button: int) -> None:
    if input_hub._uinput is not None:
        button_map = {
            1: ecodes.BTN_LEFT,
            2: ecodes.BTN_MIDDLE,
            3: ecodes.BTN_RIGHT,
        }
        code = button_map.get(button)
        if code is not None:
            try:
                input_hub._uinput.write(ecodes.EV_KEY, code, 1)
                input_hub._uinput.syn()
                return
            except Exception:
                pass

    proc = await asyncio.create_subprocess_exec(
        "xdotool", "mousedown", str(button),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def mouse_up(button: int) -> None:
    if input_hub._uinput is not None:
        button_map = {
            1: ecodes.BTN_LEFT,
            2: ecodes.BTN_MIDDLE,
            3: ecodes.BTN_RIGHT,
        }
        code = button_map.get(button)
        if code is not None:
            try:
                input_hub._uinput.write(ecodes.EV_KEY, code, 0)
                input_hub._uinput.syn()
                return
            except Exception:
                pass

    proc = await asyncio.create_subprocess_exec(
        "xdotool", "mouseup", str(button),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def mouse_scroll(direction: int) -> None:
    """Scroll mouse wheel: direction > 0 for Scroll Up, direction < 0 for Scroll Down."""
    if direction == 0:
        return
    step = 1 if direction > 0 else -1
    if input_hub._uinput is not None:
        try:
            input_hub._uinput.write(ecodes.EV_REL, ecodes.REL_WHEEL, step)
            input_hub._uinput.syn()
            return
        except Exception:
            pass

    btn = "4" if step > 0 else "5"
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "click", btn,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def mouse_click(button: int, x: int | None = None, y: int | None = None, hold_s: float = 0.025, gap_s: float = 0.020) -> None:
    if x is not None and y is not None:
        from state import state
        wid = state.get("active_window_id")
        if not wid:
            try:
                proc_w = await asyncio.create_subprocess_exec(
                    "xdotool", "getactivewindow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                out_w, _ = await proc_w.communicate()
                wid = out_w.decode().strip() or None
            except Exception:
                wid = None

        args = ["xdotool", "mousemove"]
        if wid:
            args.extend(["--window", wid])
        args.extend([str(x), str(y), "mousedown", str(button)])
        if hold_s > 0:
            args.extend(["sleep", f"{hold_s:.3f}"])
        args.extend(["mouseup", str(button)])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        if gap_s > 0:
            await asyncio.sleep(gap_s)
    else:
        # Try using virtual input (uinput) first for high performance and low latency
        if input_hub._uinput is not None:
            button_map = {
                1: ecodes.BTN_LEFT,
                2: ecodes.BTN_MIDDLE,
                3: ecodes.BTN_RIGHT,
            }
            code = button_map.get(button)
            if code is not None:
                try:
                    # Press mouse button
                    input_hub._uinput.write(ecodes.EV_KEY, code, 1)
                    input_hub._uinput.syn()
                    
                    if hold_s > 0:
                        await asyncio.sleep(hold_s)
                    
                    # Release mouse button
                    input_hub._uinput.write(ecodes.EV_KEY, code, 0)
                    input_hub._uinput.syn()
                    
                    if gap_s > 0:
                        await asyncio.sleep(gap_s)
                    return
                except Exception:
                    pass  # Fallback to xdotool if writing to uinput fails

        # Fallback to xdotool
        args = ["xdotool", "mousedown", str(button)]
        if hold_s > 0:
            args.extend(["sleep", f"{hold_s:.3f}"])
        args.extend(["mouseup", str(button)])
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        if gap_s > 0:
            await asyncio.sleep(gap_s)


async def mouse_move_relative(dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return

    # Try using virtual input (uinput) first for high performance and low latency
    if input_hub._uinput is not None:
        try:
            input_hub._uinput.write(ecodes.EV_REL, ecodes.REL_X, dx)
            input_hub._uinput.write(ecodes.EV_REL, ecodes.REL_Y, dy)
            input_hub._uinput.syn()
            return
        except Exception:
            pass

    # Fallback to xdotool
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "mousemove_relative", "--", str(dx), str(dy),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()

