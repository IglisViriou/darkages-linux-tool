import asyncio
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
    "insert": ecodes.KEY_INSERT,
    "home": ecodes.KEY_HOME,
    "end": ecodes.KEY_END,
    "pageup": ecodes.KEY_PAGEUP,
    "pagedown": ecodes.KEY_PAGEDOWN,
    "prior": ecodes.KEY_PAGEUP,
    "next": ecodes.KEY_PAGEDOWN,
    "minus": ecodes.KEY_MINUS,
    "equal": ecodes.KEY_EQUAL,
}

# Add standard letters, digits, and function keys dynamically
for i in range(1, 13):
    XKEY_TO_EVDEV[f"f{i}"] = getattr(ecodes, f"KEY_F{i}", None)

for i in range(10):
    XKEY_TO_EVDEV[str(i)] = getattr(ecodes, f"KEY_{i}", None)

import string
for c in string.ascii_lowercase:
    XKEY_TO_EVDEV[c] = getattr(ecodes, f"KEY_{c.upper()}", None)


async def key(key_name: str, hold_s: float = 0.004, gap_s: float = 0.002) -> None:
    # Try using virtual input (uinput) first for high performance and low latency
    if input_hub._uinput is not None:
        key_lower = key_name.lower()
        code = XKEY_TO_EVDEV.get(key_lower)
        if code is not None:
            try:
                # Automatically send Shift for capitalized letters
                use_shift = len(key_name) == 1 and key_name.isupper()
                
                if use_shift:
                    input_hub._uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
                
                input_hub._uinput.write(ecodes.EV_KEY, code, 1)
                input_hub._uinput.syn()
                # Fast pulse hold ensures the game registers key down without stalling the macro
                if hold_s > 0:
                    await asyncio.sleep(hold_s)
                
                input_hub._uinput.write(ecodes.EV_KEY, code, 0)
                if use_shift:
                    input_hub._uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                input_hub._uinput.syn()
                # Inter-key gap ensures consecutive identical keys register distinctly
                if gap_s > 0:
                    await asyncio.sleep(gap_s)
                return
            except Exception:
                pass  # Fallback to xdotool if writing to uinput fails

    # Fallback to xdotool
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "key", key_name,
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

