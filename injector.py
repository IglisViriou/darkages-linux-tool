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


async def key(key_name: str) -> None:
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
                # A small delay is required to ensure the target game/application
                # registers the key down state before it is released.
                await asyncio.sleep(0.015)
                
                input_hub._uinput.write(ecodes.EV_KEY, code, 0)
                if use_shift:
                    input_hub._uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                input_hub._uinput.syn()
                # A small gap delay is required to ensure the target game/application
                # processes the key release before the next key event.
                await asyncio.sleep(0.015)
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


async def mouse_click(button: int, x: int | None = None, y: int | None = None) -> None:
    if x is not None and y is not None:
        # Move relative to the current active window and click
        # Using shell=True for the subshell expansion
        cmd = f"xdotool mousemove --window $(xdotool getactivewindow) {x} {y} click {button}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
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
                    # Send a tiny 0-motion event to force X11/libinput to synchronize
                    # the virtual pointer location with the physical/active mouse cursor.
                    input_hub._uinput.write(ecodes.EV_REL, ecodes.REL_X, 0)
                    input_hub._uinput.write(ecodes.EV_REL, ecodes.REL_Y, 0)
                    
                    # Press mouse button
                    input_hub._uinput.write(ecodes.EV_KEY, code, 1)
                    input_hub._uinput.syn()
                    
                    # 25ms hold duration
                    await asyncio.sleep(0.025)
                    
                    # Release mouse button
                    input_hub._uinput.write(ecodes.EV_KEY, code, 0)
                    input_hub._uinput.syn()
                    
                    # 25ms release gap before next input
                    await asyncio.sleep(0.025)
                    return
                except Exception:
                    pass  # Fallback to xdotool if writing to uinput fails

        # Fallback to xdotool
        proc = await asyncio.create_subprocess_exec(
            "xdotool", "click", str(button),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()


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

