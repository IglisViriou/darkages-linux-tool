# Changelog

All notable changes to the DarkAges Linux Tool (DALT) project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to Semantic Versioning.

---

## [1.4] - 2026-10-16

### Features
* **Full Native Controller Mapping (Zero External Dependencies)**:
  * **Canonical Gamepad Input Layer (`input_hub.py`)**: Normalized all gamepad inputs across Xbox, PlayStation, Switch, and generic `evdev` controllers into canonical tokens (`BTN_SOUTH`, `BTN_EAST`, `BTN_WEST`, `BTN_NORTH`, `BTN_TL`, `BTN_TR`, `BTN_L2`, `BTN_R2`, `BTN_SELECT`, `BTN_START`, `BTN_MODE`, `BTN_THUMBL`, `BTN_THUMBR`, `BTN_DPAD_*`, and `BTN_JOY_*`), including analog trigger thresholding (`ABS_Z`/`ABS_RZ`/`ABS_GAS`/`ABS_BRAKE`) with hysteresis and hardware `AbsInfo` calibration.
  * **Configurable Controller Binding Engine (`features/controller.py`, `injector.py`, `state.py`)**: Every controller input can now be bound to a **Keyboard Key / Combo** (`key_down`/`key_up` hold & release, with automatic Butterwalk pulsing on directional arrows and Continuous Assail pulsing on `space`), **Mouse Action** (Left/Right/Middle hold & release or continuous Scroll Wheel Up/Down via `REL_WHEEL` / `xdotool`), **Modifier Layer Hold (Chord)** (`layer_hold`), **Macro Execution**, or **Unbound**.
  * **Modifier Layer (Chord) Support**: Holding any button bound to `Modifier Layer (Hold)` dynamically switches active controller inputs to a secondary binding map (`controller_layer_bindings`), enabling full hotbar (`1`–`0`) and function key (`F1`–`F12`) access on a standard gamepad with clean state release on chord transitions.
  * **Automatic Controller Hotplugging & Device Classification**: Separated `_controllers` from `_keyboards` and `_mice` in `input_hub.py` and added a background `hotplug_monitor()` coroutine that automatically attaches newly connected USB/Bluetooth controllers and cleans up disconnected devices without restarting DALT.
  * **Interactive Visual Controller Remapper (`gui/app.py` & `ui/tabs.py`)**: Rebuilt the Controller Inputs tab with a single-canvas interactive 2D gamepad diagram and callout badge mapper (supporting left-click to select/configure, right-click to unbind, live green button/direction press highlights, and a live Right Analog Stick position indicator), alongside connected controller status, independent Left/Right Stick deadzone sliders, Base vs. Modifier Layer switcher, interactive `"Press Pad Input to Select"` hardware detector, inline binding editor, and built-in presets (*Dark Ages Default* and *Movement Only*).

### Bug Fixes
* **Controller Directional Inputs Using Butterwalk When Disabled**:
  * Fixed an issue where holding a direction on the analog stick or DPAD continuously spammed rapid tap-and-release pulses (`injector.key()`) even when Butterwalk was turned off.
  * Added `injector.key_down()` and `injector.key_up()` (`uinput` with `xdotool keydown`/`keyup` fallback) so controller directional inputs press and hold the corresponding arrow key continuously when Butterwalk is disabled, matching physical arrow key behavior.
  * Ensured held virtual directional keys are cleanly released when returning the stick/DPAD to neutral, toggling Butterwalk on, disabling controller mapping, losing client window focus, or exiting the application.
  * Updated controller Butterwalk pulsing when enabled to respect the configured `butterwalk_delay_ms` repeat speed without stalling Right Analog Stick mouse cursor movement.
* **DPAD Hat State Transitions**:
  * Fixed `ABS_HAT0X` and `ABS_HAT0Y` event handling in `input_hub.py` so direct opposite-axis transitions (`-1 ↔ 1`) always release the previous DPAD direction before pressing the new one.
* **Macro Editor Step Stack Scrolling & Dynamic Warning Wrapping**:
  * Fixed `_on_linux_mousewheel` in `gui/app.py` to resolve the innermost `CTkScrollableFrame` under the mouse cursor rather than matching the first outer ancestor in registration order, allowing the Macro Stack step list (and nested scrollable frames) to scroll independently when hovered instead of scrolling the entire Macro Editor window.
  * Added debounced dynamic text wrapping to the Macro Editor timing warning so long text wraps cleanly as the window is resized without causing `<Configure>` layout feedback freezes.

### Tweaks and Optimizations
* Added more detail to the innate delays DALT uses for macros when there are no manual delays inserted.
* **Native Tkinter Widget Standardization**: Converted `CTkFrame`, `CTkLabel`, `CTkButton`, and `CTkFont` widgets across `gui/app.py` to standard `tk.Frame`, `tk.Label`, and `tk.Button` widgets for uniform button styling and zero CustomTkinter canvas-redraw overhead.
* **Single-Canvas Visual Controller Mapper**: Replaced the 25-row multi-widget controller binding list (125+ X11 sub-windows) with a single native `tk.Canvas` interactive gamepad diagram, cutting first-open Controller tab load time by ~65% while providing real-time input highlights.
* **Macro Editor Instance & Step Row Pooling**: Cached the `MacroEditor` window instance (`withdraw()`/`deiconify()`) and pooled step row widgets in `refresh_steps_display()`, reducing subsequent Macro Editor open times from ~1.25s to ~2ms and step edits to <5ms.
* **Targeted Macro Card Updates & Lazy Tab Loading**: Updated `save_edited_macro` and `delete_macro` to mutate or remove individual macro cards in place rather than rebuilding the full list, and deferred non-home tab widget construction until first visited.
* **Dirty-Checked GUI Polling (`update_gui`)**: Added state caching (`_gui_cache`) to `update_gui()` so labels, switches, sliders, and canvas indicators only reconfigure when their underlying values change.
* **Autofollowing Tab Clarification**: Added explicit clarification under the Autofollowing tab explaining that DALT is designed strictly for active windows (requiring held hotkeys to loop macros and excluding autofollowing).

---

## [1.3.1] - 2026-10-13

### Added
* **Macro Editor Drag-and-Drop Reordering**: Click-and-drag step reordering with real-time drop indicator line.
* **Macro Editor Step Shift Controls**: Added move up / down arrow buttons (`▲` / `▼`) to shift steps up or down one position.
* **Inline Step Editing**: Direct editing panel for selected macro steps, enabling changes to keystrokes, delay durations, or coordinates without re-recording.
* **Split Step Insertion Buttons**: Split "Add Left Click", "Add Right Click", "Add Keys", and "Add Delay" into explicit "Before" and "After" placement buttons relative to the selected step.
* **Timing Warning**: Added advisory text explaining that mouse clicks require a delay afterwards to prevent input issues.
* **Button Renaming**: Renamed click position recorder button to "Record Mouse Position in Client".

### Changed
* **Macro Management Button Polish**: Restyled the `+ New Macro`, `Edit`, and `×` (Delete) buttons in the Macro Management tab using CustomTkinter `CTkButton` components with rounded corners, theme hover colors, and matching container cards to align with the Home tab design.
* **Version Indicator**: Updated sidebar header version indicator to `Version 1.3.1`.

### Fixed
* **Macro Jamming & Missed Left Clicks (e.g. on Rulkallos)**:
  * Increased default mouse click hold duration from 5ms to 25ms and gap from 3ms to 20ms to ensure clicks span Wine/X11 frame boundaries.
  * Replaced instantaneous `xdotool click` with chained `mousedown`, `sleep`, and `mouseup`.
  * Added automatic pre-click transition buffer (minimum 25ms) when a mouse click follows a keystroke, allowing the game client sufficient time to open the targeting reticle before the confirmation click arrives.
* **Macro Tab & Editor Performance**: Patched `CTkScrollbar._draw` removing synchronous `update_idletasks()` calls, speeding up macro tab load times from ~4.3s to ~16ms (250x+ acceleration).

---

## [1.3.0] - 2026-10-10

### Added
* **Dedicated Tool Tabs**: Separated Butterwalk, Continuous Assail (Spacebar Repeat), and Controller Inputs into dedicated tabs in both GUI and TUI.
* **Continuous Assail (Spacebar Repeat)**: Independent tool that continuously repeats spacebar inputs while held down, even during macro execution, allowing players to attack/interact while executing macros concurrently.
* **Right Analog Stick Mouse Emulation**: Toggleable right stick mouse cursor movement targeting client windows with dynamic 1%–100% DPI sensitivity scaling, deadzone filtering, and sub-pixel precision.
* **Customizable In-Game Toggle Hotkeys & Combinations**:
  * Global toggle hotkeys and multi-key combinations: Butterwalk (`Ctrl + Del` default), Controller (`Ctrl + PgUp` default), Spacebar Repeat (`Ctrl + PgDn` default).
  * Interactive live hotkey recording in GUI and TUI (`k` shortcut).
* **Quick Launch Clients & Tools**:
  * Home tab Quick Launch container to launch game clients and tools directly from DALT.
  * Automated application icon extraction from Windows `.exe`, Linux `.desktop`, and local assets.
* **Window Hooks & Trigger Suppression**:
  * Scrollable container for Active Window Hooks (capped at 5 visible before scrolling).
  * Selective hardware trigger key suppression for Tilde, F-keys, and Home cluster with conditional PgUp/PgDn handling.
* **Credits Tab**: Added dedicated Credits tab in GUI and TUI.

### Performance
* **Latency Reductions**: Streamlined pulse durations and deduplicated multi-endpoint triggers.
* **Startup/Shutdown Optimization**: Added lazy tab initialization and instant task cancellation on exit.

---

## [1.2.0] - 2026-06-25

*First release of DarkAges Linux Tool (DALT), a hardened fork of Ughlis.*

### Added
* **Exact Name Match Window Hooks**: Non-invasive window searching that matches exact client window names instead of broad substrings, preventing unintended inputs sent to background apps or browser tabs.
* **Macro Toggling (Enable / Disable)**: Toggle switches for individual macros so the same trigger key can be assigned to different macros across characters or situations without interference.
* **High-Performance Virtual Input (`uinput`)**: Low-latency `/dev/uinput` virtual device emission for hardware-level key and mouse injection, with automatic fallback to `xdotool`.

### Changed
* **Project Restructuring**: Reorganized root file layout and standardized permission setup scripts (`setup_permissions.sh`).

---

## [1.1.0] - 2026-05-24

*Ughlis fork of ugh-i-cant-use-linux-because.*

### Security & Hardening
* **Async Process Execution**: Replaced legacy synchronous `subprocess.run` calls with `asyncio.create_subprocess_exec` and `await proc.communicate()`, preventing application hangs.
* **Non-Blocking Input Subsystem**: Migrated low-level `evdev` device loops to cooperative asyncio tasks, keeping input processing lag flat at near 0ms.
* **Shell Bypass**: Switched from shell-string execution to direct argument arrays to eliminate shell-injection risks.
* **Event Debouncing**: Implemented UI time-debouncing for macro lists to prevent layout thrashing and freezing.
* **Double-Input & Feedback Loop Prevention**: Added verification gates for virtual input re-emission and window-ID checks to avoid infinite input loops when clicking within the GUI.
* **Fail-Safe Device Initialization**: Localized exception capture for `/dev/input/` permission issues.

### Controller Support
* **Analog Joysticks**: Butterwalk movement multiplication integrated with analog sticks (`ABS_X`/`ABS_Y`).
* **DPAD Support**: Toggleable DPAD movement support.
* **Virtual Buttons**: Automatic translation of analog thresholds into digital events for macro triggering.

### Macro Engine
* **Coordinate Clicks**: Support for window-relative Left and Right mouse clicks.
* **Execution Modes**: Added "Once" (trigger on press) and "Hold" (repeat while held) modes.
* **Trigger Safety Reject**: Safety logic preventing accidental binding of essential inputs (like Left Click) as triggers.
* **Async Key Injection**: Background task wrapping for virtual keystroke emissions.

### Interface
* **CustomTkinter GUI**: Modern graphical interface with dark appearance mode.
* **Adaptive Tiling & Linux Scrolling**: Scrollable frame wrappers for window tiling and Linux X11 mouse wheel support.
* **Classic Curses TUI**: Full terminal UI for minimal-overhead environments.

---

## [1.0.0] - 2026-05-23

*Initial release of ugh-i-cant-use-linux-because.*

### Core Features
* **Butterwalk**: Movement multiplication injecting extra movement commands per keypress with Arrow and `ZXCV` keys across 1x, 2x, and 3x multipliers.
* **Context-Aware Window Hooks**: Automated activation when focused window matches configured search titles.
* **Combat Macros**: Wizard-based macro creation in Curses TUI supporting keystrokes, mouse clicks, and delays saved to `macros.json`.
* **Terminal UI (TUI)**: Multi-tab curses interface with Home, Butterwalk, and Macros management.
* **Linux Environment Setup**: Helper scripts (`setup.sh`, `setup_permissions.sh`) for python virtual environment and `/dev/input/` access.
