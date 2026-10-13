# Changelog

All notable changes to the DarkAges Linux Tool (DALT) project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to Semantic Versioning.

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
