# <img src="icon.png" width="32" height="32"> DALT (DarkAges Linux Tool)

<p align="center">
  <img src="icon_big.png" alt="DarkAges Linux Tool Logo" width="300">
</p>

This project is a significantly enhanced and hardened fork of `ughlis` and the original `ugh-i-cant-use-linux-because` movement and input automation tool. It has been modernized for high performance, reliability, and accessibility under Linux (Wine / X11).

For a complete history of changes across all versions, see [CHANGELOG.md](CHANGELOG.md).

## ✨ Features Overview

*   **Butterwalk (Movement Multiplication)**: Directional movement multiplication supporting Arrow keys, `ZXCV`, and analog joysticks with customizable multipliers (1x, 2x, 3x).
*   **Continuous Assail (Spacebar Repeat)**: Independent tool that continuously repeats Spacebar inputs while held down, even during macro execution.
*   **Controller Inputs & Mouse Emulation**: Dedicated tab for master mapping, DPAD, thumbstick controls, and Right Analog Stick mouse cursor emulation with dynamic DPI sensitivity scaling.
*   **Advanced Macro System**: Full macro creation with keystroke sequences, window-relative coordinate clicks, drag-and-drop reordering, inline step editing, and individual macro enable/disable toggles.
*   **Customizable In-Game Hotkeys**: Global toggle hotkeys and multi-key combinations with live interactive recording (`Ctrl + Del` for Butterwalk, `Ctrl + PgUp` for Controller, `Ctrl + PgDn` for Spacebar).
*   **Non-Invasive Window Hooks**: Exact client window title matching so inputs only route to targeted windows.
*   **Quick Launch (Clients & Tools)**: Home tab shortcut launcher with automated icon extraction from `.exe`, `.desktop`, and image files.
*   **Dual Interfaces**: Modern CustomTkinter graphical interface with dark mode and adaptive scrolling, plus a lightweight Curses terminal UI (TUI).

## 🛠 Prerequisites

*   **OS**: Linux (X11 recommended)
*   **Dependencies**: `xdotool`, `python3-evdev`, `python3-tk`
*   **Permissions**: Access to `/dev/input/` (Run `sudo ./setup_permissions.sh`)

## 📖 Usage

1.  Initialize the environment: `./setup.sh`
2.  Start the tools: `./start.sh`
3.  **Toggle Butterwalk**: `Ctrl + Del` (default hotkey), `b` (TUI), or use the GUI switch.
4.  **Continuous Assail**: `Ctrl + PgDn` (default hotkey), navigate to the dedicated tab (`s` in TUI or GUI switch) to configure repeat multiplier, speed delay, or rebind hotkey.
5.  **Controller Inputs**: `Ctrl + PgUp` (default hotkey), navigate to the Controller Inputs tab (`c` in TUI or GUI switch) to toggle controller, DPAD, thumbstick mapping, Right Analog Stick mouse cursor emulation, or rebind hotkey.
6.  **Manage Macros**: Navigate to the Macros tab to record clicks, edit steps, or bind triggers.

---

*Note: This fork prioritizes reliability and performance, ensuring that automation tools feel like a native extension of your workflow.*
