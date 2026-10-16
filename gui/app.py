import customtkinter as ctk
import tkinter as tk
import os
from tkinter import filedialog
from state import state
from features.macro import (
    MacroFeature, 
    save_macros, 
    _normalize_trigger, 
    _parse_sequence, 
    Macro, 
    DEFAULT_STEP_DELAY,
    _SPECIAL_XDOTOOL
)
from features.shortcuts import (
    Shortcut,
    save_shortcuts,
    resolve_icon,
    launch_shortcut,
    ICONS_CACHE_DIR
)
import threading
import asyncio
import uuid
import subprocess

# Optimize CustomTkinter on Linux: CTkScrollbar._draw calls update_idletasks() synchronously,
# which causes massive UI freezing on Linux when multiple widgets or unmapped frames exist.
_orig_scrollbar_draw = ctk.CTkScrollbar._draw

def _fast_scrollbar_draw(self, no_color_updates=False):
    super(ctk.CTkScrollbar, self)._draw(no_color_updates)
    corrected_start_value, corrected_end_value = self._get_scrollbar_values_for_minimum_pixel_size()
    requires_recoloring = self._draw_engine.draw_rounded_scrollbar(
        self._apply_widget_scaling(self._current_width),
        self._apply_widget_scaling(self._current_height),
        self._apply_widget_scaling(self._corner_radius),
        self._apply_widget_scaling(self._border_spacing),
        corrected_start_value,
        corrected_end_value,
        self._orientation
    )
    if no_color_updates is False or requires_recoloring:
        if self._hover_state is True:
            self._canvas.itemconfig(
                "scrollbar_parts",
                fill=self._apply_appearance_mode(self._button_hover_color),
                outline=self._apply_appearance_mode(self._button_hover_color)
            )
        else:
            self._canvas.itemconfig(
                "scrollbar_parts",
                fill=self._apply_appearance_mode(self._button_color),
                outline=self._apply_appearance_mode(self._button_color)
            )
        if self._fg_color == "transparent":
            self._canvas.configure(bg=self._apply_appearance_mode(self._bg_color))
            self._canvas.itemconfig(
                "border_parts",
                fill=self._apply_appearance_mode(self._bg_color),
                outline=self._apply_appearance_mode(self._bg_color)
            )
        else:
            self._canvas.configure(bg=self._apply_appearance_mode(self._fg_color))
            self._canvas.itemconfig(
                "border_parts",
                fill=self._apply_appearance_mode(self._fg_color),
                outline=self._apply_appearance_mode(self._fg_color)
            )
    # Intentionally omitted self._canvas.update_idletasks() for zero-lag rendering on Linux

ctk.CTkScrollbar._draw = _fast_scrollbar_draw

_LINUX_SCROLL_FRAMES: list[ctk.CTkScrollableFrame] = []
_LINUX_SCROLL_INITIALIZED = False

def _on_linux_mousewheel(event):
    frame_lookup = {}
    for sf in list(_LINUX_SCROLL_FRAMES):
        try:
            if not sf.winfo_exists():
                _LINUX_SCROLL_FRAMES.remove(sf)
                continue
            frame_lookup[sf] = sf
            if hasattr(sf, "_parent_canvas"):
                frame_lookup[sf._parent_canvas] = sf
            if hasattr(sf, "_parent_frame"):
                frame_lookup[sf._parent_frame] = sf
        except Exception:
            pass

    curr = getattr(event, "widget", None)
    target_sf = None
    while curr is not None:
        if curr in frame_lookup:
            target_sf = frame_lookup[curr]
            break
        curr = getattr(curr, "master", None)

    if target_sf is not None:
        try:
            if target_sf._parent_canvas.yview() != (0.0, 1.0):
                if event.num == 4:
                    target_sf._parent_canvas.yview("scroll", -1, "units")
                elif event.num == 5:
                    target_sf._parent_canvas.yview("scroll", 1, "units")
        except Exception:
            pass

def enable_linux_scroll(scrollable_frame: ctk.CTkScrollableFrame):
    """Explicitly bind mouse wheel buttons for Linux compatibility with central handler."""
    global _LINUX_SCROLL_INITIALIZED
    if scrollable_frame not in _LINUX_SCROLL_FRAMES:
        _LINUX_SCROLL_FRAMES.append(scrollable_frame)
    if not _LINUX_SCROLL_INITIALIZED:
        try:
            scrollable_frame.bind_all("<Button-4>", _on_linux_mousewheel, add="+")
            scrollable_frame.bind_all("<Button-5>", _on_linux_mousewheel, add="+")
            _LINUX_SCROLL_INITIALIZED = True
        except Exception:
            pass

class MacroEditor(ctk.CTkToplevel):
    def __init__(self, parent, on_save, macro_to_edit=None):
        super().__init__(parent)
        
        # Set icon
        try:
            self.icon_img = tk.PhotoImage(file='icon.png')
            self.wm_iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self.close_editor)
        self.geometry("650x900")
        self.configure(fg_color="#242424")

        # Shared tuple fonts for zero-overhead Tcl font usage
        self._font_title = ("sans-serif", 16, "bold")
        self._font_sec = ("sans-serif", 13, "bold")
        self._font_bold = ("sans-serif", 10, "bold")
        self._font_12 = ("sans-serif", 10)
        self._font_12_bold = ("sans-serif", 10, "bold")
        self._font_11 = ("sans-serif", 9)
        self._font_11_bold = ("sans-serif", 9, "bold")
        self._font_10 = ("sans-serif", 8)

        self.macro_to_edit = None
        self.on_save = on_save
        self.current_steps = []
        self.bound_trigger = None
        self.kind = "macro"
        self.trigger_mode = "once"
        self.output_key = None
        self.listening_for = None  # "trigger" or "output"
        self.row_frames = []
        self._step_row_pool = []
        self._empty_stack_lbl = None
        self._drag_data = {"src": None, "active": False, "start_y": 0, "target": None}
        self.selected_step_index = None
        self._is_open = True
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.title_label = tk.Label(self, text="Configuration Editor", font=self._font_title, fg="#DCE4EE", bg="#242424")
        self.title_label.pack(pady=20)
        
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="#242424")
        self.main_container.pack(fill="both", expand=True, padx=30)
        enable_linux_scroll(self.main_container)

        # Mode Selector (Kind & Trigger)
        selector_frame = tk.Frame(self.main_container, bg="#242424")
        selector_frame.pack(fill="x", pady=(0, 15))
        
        # Kind
        kind_frame = tk.Frame(selector_frame, bg="#242424")
        kind_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(kind_frame, text="Type:", font=self._font_bold, fg="#DCE4EE", bg="#242424").pack(anchor="w")
        self.kind_selector = ctk.CTkSegmentedButton(kind_frame, values=["Macro", "Keybind"], command=self.toggle_kind)
        self.kind_selector.pack(pady=(5, 0), fill="x")

        # Trigger Mode
        mode_frame = tk.Frame(selector_frame, bg="#242424")
        mode_frame.pack(side="left", fill="both", expand=True, padx=10)
        tk.Label(mode_frame, text="Trigger Mode:", font=self._font_bold, fg="#DCE4EE", bg="#242424").pack(anchor="w")
        self.mode_selector = ctk.CTkSegmentedButton(mode_frame, values=["Once", "Hold"])
        self.mode_selector.pack(pady=(5, 0), fill="x")

        # Interruptible Toggle
        int_frame = tk.Frame(selector_frame, bg="#242424")
        int_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(int_frame, text="Options:", font=self._font_bold, fg="#DCE4EE", bg="#242424").pack(anchor="w")
        
        self.interrupt_var = ctk.BooleanVar(value=True)
        self.interrupt_switch = ctk.CTkSwitch(int_frame, text="Interrupt", variable=self.interrupt_var, bg_color="#242424")
        self.interrupt_switch.pack(pady=(5, 0))

        self.enabled_var = ctk.BooleanVar(value=True)
        self.enabled_switch = ctk.CTkSwitch(int_frame, text="Enabled", variable=self.enabled_var, bg_color="#242424")
        self.enabled_switch.pack(pady=(5, 0))

        # Name Field
        tk.Label(self.main_container, text="Name:", font=self._font_bold, fg="#DCE4EE", bg="#242424").pack(anchor="w")
        self.name_entry = ctk.CTkEntry(self.main_container, placeholder_text="e.g. Buff Sequence", width=400)
        self.name_entry.pack(pady=(5, 15), anchor="w")

        # Trigger Field (Interactive)
        tk.Label(self.main_container, text="Trigger Key:", font=self._font_bold, fg="#DCE4EE", bg="#242424").pack(anchor="w")
        trigger_frame = tk.Frame(self.main_container, bg="#242424")
        trigger_frame.pack(fill="x", pady=(5, 15))
        
        self.trigger_label = tk.Label(
            trigger_frame,
            text="Not Bound",
            font=self._font_bold,
            fg="#DCE4EE",
            bg="#333333",
            width=22,
            pady=5
        )
        self.trigger_label.pack(side="left", padx=(0, 10))
        
        self.bind_btn = tk.Button(
            trigger_frame,
            text="Click to Bind",
            font=self._font_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=lambda: self.start_binding("trigger")
        )
        self.bind_btn.pack(side="left")

        # --- ACTION BUTTONS ---
        self.action_frame = tk.Frame(self.main_container, bg="#242424")
        self.action_frame.pack(fill="x", pady=(10, 20))
        
        self.cancel_button = tk.Button(
            self.action_frame,
            text="Cancel",
            font=self._font_bold,
            fg="white",
            bg="#555555",
            activeforeground="white",
            activebackground="#666666",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.close_editor
        )
        self.cancel_button.pack(side="left")
        
        self.save_button = tk.Button(
            self.action_frame,
            text="Save Configuration",
            font=self._font_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.save
        )
        self.save_button.pack(side="right")

        # --- KEYBIND MODE SECTION ---
        self.keybind_section = tk.Frame(self.main_container, bg="#2b2b2b")
        
        tk.Label(self.keybind_section, text="Direct Keybind Settings", font=self._font_sec, fg="#DCE4EE", bg="#2b2b2b").pack(pady=10)
        
        tk.Label(self.keybind_section, text="Output Key (What to send):", font=self._font_bold, fg="#DCE4EE", bg="#2b2b2b").pack(anchor="w", padx=20)
        output_frame = tk.Frame(self.keybind_section, bg="#2b2b2b")
        output_frame.pack(fill="x", padx=20, pady=(5, 20))
        
        self.output_label = tk.Label(
            output_frame,
            text="Not Bound",
            font=self._font_bold,
            fg="#DCE4EE",
            bg="#333333",
            width=22,
            pady=5
        )
        self.output_label.pack(side="left", padx=(0, 10))
        
        self.output_bind_btn = tk.Button(
            output_frame,
            text="Click to Bind",
            font=self._font_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=lambda: self.start_binding("output")
        )
        self.output_bind_btn.pack(side="left")

        # --- STEP BUILDER SECTION ---
        self.macro_section = tk.Frame(self.main_container, bg="#2b2b2b")
        
        tk.Label(self.macro_section, text="Step Builder", font=self._font_sec, fg="#DCE4EE", bg="#2b2b2b").pack(pady=10)

        # Quick Add Buttons: Left Click & Right Click (Split into Before and After)
        click_frame_1 = tk.Frame(self.macro_section, bg="#2b2b2b")
        click_frame_1.pack(fill="x", padx=20, pady=(5, 3))
        
        self.add_left_before_btn = tk.Button(
            click_frame_1,
            text="Add Left Click (Before)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            width=19,
            pady=7,
            cursor="hand2",
            command=lambda: self.add_raw_step("mouse_left", "before")
        )
        self.add_left_before_btn.pack(side="left", padx=(0, 6))

        self.add_left_after_btn = tk.Button(
            click_frame_1,
            text="Add Left Click (After)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            width=19,
            pady=7,
            cursor="hand2",
            command=lambda: self.add_raw_step("mouse_left", "after")
        )
        self.add_left_after_btn.pack(side="left", padx=(0, 6))

        self.record_btn = tk.Button(
            click_frame_1,
            text="Record Mouse\nPosition in Client",
            font=self._font_11_bold,
            fg="black",
            bg="orange",
            activeforeground="black",
            activebackground="#CC8800",
            relief="flat",
            bd=0,
            width=18,
            pady=2,
            cursor="hand2",
            command=self.start_countdown
        )
        self.record_btn.pack(side="left")

        click_frame_2 = tk.Frame(self.macro_section, bg="#2b2b2b")
        click_frame_2.pack(fill="x", padx=20, pady=(3, 3))

        self.add_right_before_btn = tk.Button(
            click_frame_2,
            text="Add Right Click (Before)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            width=19,
            pady=7,
            cursor="hand2",
            command=lambda: self.add_raw_step("mouse_right", "before")
        )
        self.add_right_before_btn.pack(side="left", padx=(0, 6))

        self.add_right_after_btn = tk.Button(
            click_frame_2,
            text="Add Right Click (After)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            width=19,
            pady=7,
            cursor="hand2",
            command=lambda: self.add_raw_step("mouse_right", "after")
        )
        self.add_right_after_btn.pack(side="left")

        # Innate Timing & Mouse Click Delay Explanation
        self.click_delay_warning = tk.Label(
            self.macro_section,
            text=(
                "ℹ️ Innate Timing (when no manual Delay step is added):\n"
                "• Keystrokes: 4ms press hold + 2ms post-key gap (6ms total per key).\n"
                "• Key → Click Transition: Automatically inserts a 25ms pre-click buffer after a keystroke so the client targeting reticle can open.\n"
                "• Mouse Clicks: 25ms button hold + 20ms post-click recovery gap (45ms total). Add a manual Delay step (10ms+) only if the client needs extra time between actions."
            ),
            font=self._font_11_bold,
            fg="#FFAA33",
            bg="#2b2b2b",
            anchor="w",
            justify="left",
            wraplength=460
        )
        self.click_delay_warning.pack(fill="x", anchor="w", padx=20, pady=(4, 6))

        def _update_warning_wrap(event):
            if event.widget is not self:
                return
            win_w = int(event.width)
            if getattr(self, "_last_editor_win_w", None) == win_w:
                return
            self._last_editor_win_w = win_w
            new_wrap = max(180, win_w - 136)
            self.click_delay_warning.configure(wraplength=new_wrap)

        self.bind("<Configure>", _update_warning_wrap, add="+")

        # Input + Add Keys Buttons (Before & After)
        input_frame = tk.Frame(self.macro_section, bg="#2b2b2b")
        input_frame.pack(fill="x", padx=20, pady=12)
        
        self.step_input = ctk.CTkEntry(input_frame, placeholder_text="Type keys (e.g. {enter}, f, {F1})...")
        self.step_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.step_input.bind("<Return>", lambda e: self.add_segment("after"))

        self.add_keys_before_btn = tk.Button(
            input_frame,
            text="Add Keys (Before)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.add_segment("before")
        )
        self.add_keys_before_btn.pack(side="left", padx=(0, 6))

        self.add_keys_after_btn = tk.Button(
            input_frame,
            text="Add Keys (After)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.add_segment("after")
        )
        self.add_keys_after_btn.pack(side="left")

        # Syntax Hint
        tk.Label(
            self.macro_section,
            text="Syntax: {F1}, {enter}, {space}, {click}, {rclick}, {wait:100}",
            font=self._font_10,
            fg="#888888",
            bg="#2b2b2b"
        ).pack(pady=(0, 8))

        # Capture Status Label
        self.capture_status = tk.Label(self.macro_section, text="Status: Ready", font=self._font_11, fg="#888888", bg="#2b2b2b")
        self.capture_status.pack(pady=(0, 5))

        # Manual Delay Setting (Before & After)
        delay_frame = tk.Frame(self.macro_section, bg="#2b2b2b")
        delay_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(delay_frame, text="Delay (ms):", font=self._font_12, fg="#DCE4EE", bg="#2b2b2b").pack(side="left", padx=(0, 6))
        self.delay_input = ctk.CTkEntry(delay_frame, width=90, placeholder_text="100")
        self.delay_input.pack(side="left", padx=(0, 8))
        self.add_delay_before_btn = tk.Button(
            delay_frame,
            text="Add Delay (Before)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.add_delay_step("before")
        )
        self.add_delay_before_btn.pack(side="left", padx=(0, 6))
        self.add_delay_after_btn = tk.Button(
            delay_frame,
            text="Add Delay (After)",
            font=self._font_11_bold,
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.add_delay_step("after")
        )
        self.add_delay_after_btn.pack(side="left")

        # Selection & Editing Panel Bar
        self.selection_bar = tk.Frame(self.macro_section, bg="#1c2430")
        self.selection_bar.pack(fill="x", padx=20, pady=(6, 2))
        
        # Steps Display Area
        self.steps_display = ctk.CTkScrollableFrame(self.macro_section, label_text="Macro Stack (Click to select | Drag ⠿ or use ▲▼ to reorder)", height=250)
        self.steps_display.pack(fill="both", expand=True, padx=20, pady=10)
        enable_linux_scroll(self.steps_display)
        
        self.drop_indicator = tk.Frame(self.steps_display, height=3, bg="#3b8ed0", bd=0)

        self.load_macro_data(on_save, macro_to_edit)

    def load_macro_data(self, on_save, macro_to_edit=None):
        """Reset and populate editor fields in-place without recreating the window."""
        self._is_open = True
        self.on_save = on_save
        self.macro_to_edit = macro_to_edit
        self.title("Edit Macro/Keybind" if macro_to_edit else "New Configuration")
        self.title_label.configure(text="Configuration Editor", fg="#DCE4EE")

        self.current_steps = [dict(s) for s in macro_to_edit["steps"]] if macro_to_edit else []
        self.bound_trigger = macro_to_edit["trigger"] if macro_to_edit else None
        self.kind = macro_to_edit.get("kind", "macro") if macro_to_edit else "macro"
        self.trigger_mode = macro_to_edit.get("trigger_mode", "once") if macro_to_edit else "once"
        self.output_key = self.current_steps[0]["value"] if self.kind == "keybind" and self.current_steps else None
        self.listening_for = None
        state["listening_for_trigger"] = False
        state["recording_mouse"] = False
        self._drag_data = {"src": None, "active": False, "start_y": 0, "target": None}
        self.selected_step_index = None

        self.kind_selector.set("Macro" if self.kind == "macro" else "Keybind")
        self.mode_selector.set("Once" if self.trigger_mode == "once" else "Hold")
        self.interrupt_var.set(macro_to_edit.get("interruptible", True) if macro_to_edit else True)
        self.enabled_var.set(macro_to_edit.get("enabled", True) if macro_to_edit else True)

        self.name_entry.delete(0, "end")
        if macro_to_edit:
            self.name_entry.insert(0, macro_to_edit["name"])

        self.trigger_label.configure(text=self.bound_trigger or "Not Bound")
        self.bind_btn.configure(text="Click to Bind", state="normal")
        self.output_label.configure(text=self.output_key or "Not Bound")
        self.output_bind_btn.configure(text="Click to Bind", state="normal")
        self.capture_status.configure(text="Status: Ready", fg="#888888")
        self.step_input.delete(0, "end")
        self.delay_input.delete(0, "end")
        self.delay_input.configure(border_color="gray")

        self.toggle_kind(self.kind_selector.get())
        self.refresh_steps_display(focus_edit=False)
        self.poll_state()

    def close_editor(self):
        self._is_open = False
        self.listening_for = None
        state["listening_for_trigger"] = False
        state["recording_mouse"] = False
        try:
            self.grab_release()
        except Exception:
            pass
        self.withdraw()

    def toggle_kind(self, value):
        self.kind = value.lower()
        if self.kind == "keybind":
            self.macro_section.pack_forget()
            self.keybind_section.pack(fill="both", expand=True, pady=10)
        else:
            self.keybind_section.pack_forget()
            self.macro_section.pack(fill="both", expand=True, pady=10)

    def start_binding(self, target):
        self.listening_for = target
        state["listening_for_trigger"] = True
        state["captured_trigger"] = None
        if target == "trigger":
            self.bind_btn.configure(text="Press Any Key...", state="disabled")
        else:
            self.output_bind_btn.configure(text="Press Any Key...", state="disabled")

    def poll_state(self):
        if not self._is_open or not self.winfo_exists():
            return
        # 1. Check for captured triggers
        if state.get("captured_trigger"):
            key = state["captured_trigger"]
            state["captured_trigger"] = None
            state["listening_for_trigger"] = False
            
            if self.listening_for == "trigger":
                if key in ("BTN_LEFT", "CODE_272"):
                    self.capture_status.configure(text="Safety: Cannot bind Left Click as trigger!", fg="red")
                    self.bind_btn.configure(text="Click to Bind", state="normal")
                    self.listening_for = None
                    return

                self.bound_trigger = key
                self.trigger_label.configure(text=self.bound_trigger)
                self.bind_btn.configure(text="Click to Bind", state="normal")
            elif self.listening_for == "output":
                from features.macro import _SPECIAL_XDOTOOL
                norm_key = key.replace("KEY_", "").lower()
                if norm_key in _SPECIAL_XDOTOOL:
                    self.output_key = _SPECIAL_XDOTOOL[norm_key]
                else:
                    self.output_key = norm_key
                self.output_label.configure(text=self.output_key)
                self.output_bind_btn.configure(text="Click to Bind", state="normal")
            
            self.listening_for = None

        # 2. Check for captured clicks
        if state.get("captured_click"):
            data = state["captured_click"]
            state["captured_click"] = None
            idx = self._get_insert_index("after")
            self.current_steps.insert(idx, {
                "kind": data["kind"], "value": "", "delay_ms": 0, "x": data["x"], "y": data["y"]
            })
            self.selected_step_index = idx
            self.capture_status.configure(text=f"Status: Captured click at {data['x']},{data['y']}", fg="#44AA44")
            self.refresh_steps_display()

        # Reset record button if needed
        if not state.get("recording_mouse") and self.record_btn.cget("state") == "disabled":
            self.record_btn.configure(text="Record Mouse\nPosition in Client", state="normal")
        
        if self._is_open and self.winfo_exists():
            self.after(100, self.poll_state)

    def start_countdown(self, seconds=3):
        if not self._is_open:
            return
        if seconds > 0:
            self.record_btn.configure(text=f"Click Game in {seconds}s...", state="disabled")
            self.capture_status.configure(text=f"Status: Move mouse to target in {seconds}s...", fg="orange")
            self.after(1000, lambda: self.start_countdown(seconds - 1))
        else:
            self.perform_auto_capture()

    def perform_auto_capture(self):
        try:
            m_out = subprocess.check_output(["xdotool", "getmouselocation", "--shell"], stderr=subprocess.DEVNULL).decode()
            m_data = dict(line.split("=", 1) for line in m_out.strip().split("\n") if "=" in line)
            mx, my, mwid = int(m_data.get("X", 0)), int(m_data.get("Y", 0)), m_data.get("WINDOW")
            w_out = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", mwid], stderr=subprocess.DEVNULL).decode()
            w_data = dict(line.split("=", 1) for line in w_out.strip().split("\n") if "=" in line)
            wx, wy = int(w_data.get("X", 0)), int(w_data.get("Y", 0))

            idx = self._get_insert_index("after")
            self.current_steps.insert(idx, {
                "kind": "mouse_left", "value": "", 
                "delay_ms": 0,
                "x": mx - wx, "y": my - wy
            })
            self.selected_step_index = idx
            self.capture_status.configure(text=f"Status: Captured click at {mx-wx},{my-wy}", fg="#44AA44")
        except Exception as e:
            self.capture_status.configure(text=f"Status: Capture failed: {str(e)}", fg="red")
        self.record_btn.configure(text="Record Mouse\nPosition in Client", state="normal")
        self.refresh_steps_display()

    def _get_insert_index(self, position="after"):
        if not self.current_steps:
            return 0
        if self.selected_step_index is not None and 0 <= self.selected_step_index < len(self.current_steps):
            if position == "before":
                return self.selected_step_index
            else:
                return self.selected_step_index + 1
        else:
            if position == "before":
                return 0
            else:
                return len(self.current_steps)

    def parse_single_key(self, raw: str) -> str:
        raw = raw.strip()
        if not raw:
            return ""
        if raw.startswith("{") and raw.endswith("}") and len(raw) >= 2:
            inner = raw[1:-1].strip()
        else:
            inner = raw

        lower_inner = inner.lower()
        from features.macro import _SPECIAL_XDOTOOL
        if lower_inner in _SPECIAL_XDOTOOL:
            return _SPECIAL_XDOTOOL[lower_inner]
        if lower_inner == "-":
            return "minus"
        if lower_inner == "=":
            return "equal"

        steps = _parse_sequence(f"{{{lower_inner}}}")
        if steps and steps[0]["kind"] == "key" and steps[0]["value"]:
            return steps[0]["value"]

        steps = _parse_sequence(inner)
        if steps and steps[0]["kind"] == "key" and steps[0]["value"]:
            return steps[0]["value"]

        return inner

    def select_step(self, index, focus_edit=False):
        old_idx = self.selected_step_index
        if old_idx == index and not focus_edit:
            self.selected_step_index = None
        else:
            self.selected_step_index = index

        if len(self.row_frames) == len(self.current_steps):
            if old_idx is not None and 0 <= old_idx < len(self.current_steps):
                self._update_step_row_widget(old_idx)
            new_idx = self.selected_step_index
            if new_idx is not None and 0 <= new_idx < len(self.current_steps):
                self._update_step_row_widget(new_idx)
            self.update_selection_panel(focus_edit=focus_edit)
        else:
            self.refresh_steps_display(focus_edit=focus_edit)

    def clear_selection(self):
        old_idx = self.selected_step_index
        self.selected_step_index = None
        if len(self.row_frames) == len(self.current_steps):
            if old_idx is not None and 0 <= old_idx < len(self.current_steps):
                self._update_step_row_widget(old_idx)
            self.update_selection_panel(focus_edit=False)
        else:
            self.refresh_steps_display(focus_edit=False)

    def _focus_entry(self, widget):
        try:
            widget.focus_set()
            if hasattr(widget, "select_range"):
                widget.select_range(0, "end")
        except Exception:
            pass

    def update_selection_panel(self, focus_edit=False):
        for widget in self.selection_bar.winfo_children():
            widget.destroy()

        if self.selected_step_index is None or not (0 <= self.selected_step_index < len(self.current_steps)):
            lbl = tk.Label(
                self.selection_bar,
                text="Selected Input: None (Click any step below or ✎ to select & edit)",
                fg="#888888",
                bg="#1c2430",
                font=self._font_12
            )
            lbl.pack(pady=8, padx=10)
            return

        idx = self.selected_step_index
        step = self.current_steps[idx]
        kind = step.get("kind", "key")

        # Top header row
        header_frame = tk.Frame(self.selection_bar, bg="#1c2430")
        header_frame.pack(fill="x", padx=10, pady=(6, 2))

        kind_display = {
            "key": "Keystroke",
            "wait": "Delay / Wait",
            "mouse_left": "Mouse Left Click",
            "mouse_right": "Mouse Right Click"
        }.get(kind, kind.upper())

        title_lbl = tk.Label(
            header_frame,
            text=f"Edit Step #{idx + 1}: {kind_display}",
            font=self._font_12_bold,
            fg="#58a6ff",
            bg="#1c2430"
        )
        title_lbl.pack(side="left")

        deselect_btn = tk.Button(
            header_frame,
            text="Deselect",
            font=self._font_11,
            fg="white",
            bg="#4d4d4d",
            activeforeground="white",
            activebackground="#666666",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.clear_selection
        )
        deselect_btn.pack(side="right")

        # Edit controls row
        ctrl_frame = tk.Frame(self.selection_bar, bg="#1c2430")
        ctrl_frame.pack(fill="x", padx=10, pady=(2, 6))

        focus_target = None

        if kind == "key":
            tk.Label(ctrl_frame, text="Key:", font=self._font_12_bold, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 4))
            self.edit_key_entry = ctk.CTkEntry(ctrl_frame, width=120, placeholder_text="e.g. F1, space, a")
            self.edit_key_entry.insert(0, str(step.get("value", "")))
            self.edit_key_entry.pack(side="left", padx=(0, 10))
            self.edit_key_entry.bind("<Return>", lambda e: self.apply_step_edit())
            focus_target = self.edit_key_entry

            tk.Label(ctrl_frame, text="Delay (ms):", font=self._font_12, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 4))
            self.edit_delay_entry = ctk.CTkEntry(ctrl_frame, width=70, placeholder_text="0")
            self.edit_delay_entry.insert(0, str(step.get("delay_ms", 0)))
            self.edit_delay_entry.pack(side="left", padx=(0, 10))
            self.edit_delay_entry.bind("<Return>", lambda e: self.apply_step_edit())

        elif kind == "wait":
            tk.Label(ctrl_frame, text="Delay (ms):", font=self._font_12_bold, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 4))
            self.edit_delay_entry = ctk.CTkEntry(ctrl_frame, width=90, placeholder_text="100")
            self.edit_delay_entry.insert(0, str(step.get("delay_ms", 0)))
            self.edit_delay_entry.pack(side="left", padx=(0, 10))
            self.edit_delay_entry.bind("<Return>", lambda e: self.apply_step_edit())
            focus_target = self.edit_delay_entry

        elif kind in ("mouse_left", "mouse_right"):
            tk.Label(ctrl_frame, text="Type:", font=self._font_12, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 4))
            self.edit_click_type = ctk.CTkSegmentedButton(
                ctrl_frame,
                values=["Left Click", "Right Click"],
                width=140
            )
            self.edit_click_type.set("Left Click" if kind == "mouse_left" else "Right Click")
            self.edit_click_type.pack(side="left", padx=(0, 10))

            tk.Label(ctrl_frame, text="X:", font=self._font_12, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 2))
            self.edit_x_entry = ctk.CTkEntry(ctrl_frame, width=55)
            if step.get("x") is not None:
                self.edit_x_entry.insert(0, str(step["x"]))
            self.edit_x_entry.pack(side="left", padx=(0, 6))
            self.edit_x_entry.bind("<Return>", lambda e: self.apply_step_edit())
            focus_target = self.edit_x_entry

            tk.Label(ctrl_frame, text="Y:", font=self._font_12, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 2))
            self.edit_y_entry = ctk.CTkEntry(ctrl_frame, width=55)
            if step.get("y") is not None:
                self.edit_y_entry.insert(0, str(step["y"]))
            self.edit_y_entry.pack(side="left", padx=(0, 8))
            self.edit_y_entry.bind("<Return>", lambda e: self.apply_step_edit())

            tk.Label(ctrl_frame, text="Delay (ms):", font=self._font_12, fg="#DCE4EE", bg="#1c2430").pack(side="left", padx=(0, 2))
            self.edit_delay_entry = ctk.CTkEntry(ctrl_frame, width=55)
            self.edit_delay_entry.insert(0, str(step.get("delay_ms", 0)))
            self.edit_delay_entry.pack(side="left", padx=(0, 10))
            self.edit_delay_entry.bind("<Return>", lambda e: self.apply_step_edit())

        self._apply_btn = tk.Button(
            ctrl_frame,
            text="Apply Change",
            font=self._font_bold,
            fg="white",
            bg="#238636",
            activeforeground="white",
            activebackground="#2ea043",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.apply_step_edit
        )
        self._apply_btn.pack(side="left", padx=(4, 0))

        if focus_edit and focus_target:
            self.after(50, lambda: self._focus_entry(focus_target))

    def apply_step_edit(self):
        if self.selected_step_index is None or not (0 <= self.selected_step_index < len(self.current_steps)):
            return

        idx = self.selected_step_index
        step = self.current_steps[idx]
        kind = step.get("kind", "key")

        if kind == "key":
            raw_key = self.edit_key_entry.get().strip()
            if not raw_key:
                self.edit_key_entry.configure(border_color="red")
                return

            if raw_key.startswith("{") and raw_key.endswith("}"):
                seq = _parse_sequence(raw_key)
                if len(seq) == 1 and seq[0]["kind"] != "key":
                    step["kind"] = seq[0]["kind"]
                    step["value"] = seq[0]["value"]
                    step["delay_ms"] = seq[0]["delay_ms"]
                    if seq[0].get("x") is not None:
                        step["x"] = seq[0]["x"]
                        step["y"] = seq[0]["y"]
                    self._update_step_row_widget(idx)
                    self.update_selection_panel(focus_edit=False)
                    self._flash_apply_btn()
                    return

            parsed_key = self.parse_single_key(raw_key)
            if not parsed_key:
                self.edit_key_entry.configure(border_color="red")
                return
            self.edit_key_entry.configure(border_color="gray")

            delay_str = self.edit_delay_entry.get().strip()
            delay_ms = 0
            if delay_str:
                try:
                    delay_ms = max(0, int(delay_str))
                    self.edit_delay_entry.configure(border_color="gray")
                except ValueError:
                    self.edit_delay_entry.configure(border_color="red")
                    return

            step["value"] = parsed_key
            step["delay_ms"] = delay_ms

        elif kind == "wait":
            delay_str = self.edit_delay_entry.get().strip()
            try:
                delay_ms = max(0, int(delay_str))
                self.edit_delay_entry.configure(border_color="gray")
            except (ValueError, TypeError):
                self.edit_delay_entry.configure(border_color="red")
                return
            step["delay_ms"] = delay_ms

        elif kind in ("mouse_left", "mouse_right"):
            click_choice = self.edit_click_type.get()
            step["kind"] = "mouse_left" if click_choice == "Left Click" else "mouse_right"

            x_str = self.edit_x_entry.get().strip()
            y_str = self.edit_y_entry.get().strip()
            if x_str:
                try:
                    step["x"] = int(x_str)
                    self.edit_x_entry.configure(border_color="gray")
                except ValueError:
                    self.edit_x_entry.configure(border_color="red")
                    return
            else:
                step["x"] = None

            if y_str:
                try:
                    step["y"] = int(y_str)
                    self.edit_y_entry.configure(border_color="gray")
                except ValueError:
                    self.edit_y_entry.configure(border_color="red")
                    return
            else:
                step["y"] = None

            delay_str = self.edit_delay_entry.get().strip()
            delay_ms = 0
            if delay_str:
                try:
                    delay_ms = max(0, int(delay_str))
                    self.edit_delay_entry.configure(border_color="gray")
                except ValueError:
                    self.edit_delay_entry.configure(border_color="red")
                    return
            step["delay_ms"] = delay_ms

        # Update only the modified row in-place instead of rebuilding the entire stack
        self._update_step_row_widget(idx)
        self._flash_apply_btn()

    def _flash_apply_btn(self):
        if hasattr(self, "_apply_btn") and self._apply_btn and self._apply_btn.winfo_exists():
            self._apply_btn.configure(text="✓ Applied", bg="#1f6feb")
            self.after(1000, lambda: self._apply_btn.configure(text="Apply Change", bg="#238636") if hasattr(self, "_apply_btn") and self._apply_btn and self._apply_btn.winfo_exists() else None)

    def add_raw_step(self, kind, position="after"):
        idx = self._get_insert_index(position)
        self.current_steps.insert(idx, {"kind": kind, "value": "", "delay_ms": 0})
        self.selected_step_index = idx
        self.refresh_steps_display()

    def add_segment(self, position="after"):
        seg = self.step_input.get().strip()
        if not seg: return
        new_steps = _parse_sequence(seg)
        if not new_steps: return
        idx = self._get_insert_index(position)
        for offset, step in enumerate(new_steps):
            self.current_steps.insert(idx + offset, step)
        self.selected_step_index = idx + len(new_steps) - 1
        self.step_input.delete(0, 'end')
        self.refresh_steps_display()

    def add_delay_step(self, position="after"):
        val = self.delay_input.get().strip()
        if not val.isdigit():
            self.delay_input.configure(border_color="red")
            return
        self.delay_input.configure(border_color="gray")
        ms = int(val)
        idx = self._get_insert_index(position)
        self.current_steps.insert(idx, {"kind": "wait", "value": "", "delay_ms": ms})
        self.selected_step_index = idx
        self.refresh_steps_display()

    def _create_pooled_step_row(self) -> dict:
        f = tk.Frame(self.steps_display, bg="#2b2b2b", highlightthickness=0, highlightbackground="#3b8ed0", highlightcolor="#3b8ed0", bd=0)
        item: dict = {"frame": f, "index": 0}

        handle = tk.Label(f, text="⠿", font=("Arial", 12, "bold"), fg="#999999", bg="#2b2b2b", cursor="fleur", width=2)
        handle.pack(side="left", padx=(6, 2), pady=3)

        step_lbl = tk.Label(f, text="", font=("Monospace", 10, "bold"), fg="white", bg="#2b2b2b", anchor="w")
        step_lbl.pack(side="left", padx=4, pady=3)

        badge_lbl = tk.Label(f, text="[SELECTED]", font=("Arial", 8, "bold"), fg="#58a6ff", bg="#1c324b")
        coord_lbl = tk.Label(f, text="", font=("Arial", 9, "bold"), fg="cyan", bg="#2b2b2b")
        delay_lbl = tk.Label(f, text="", font=("Arial", 9), fg="#aaaaaa", bg="#2b2b2b")

        remove_btn = tk.Button(
            f, text="×", relief="flat", bd=0, bg="#222b35", fg="#ff5555",
            activebackground="#441111", activeforeground="#ff8888", font=("Arial", 10, "bold"), width=2,
            command=lambda: self.remove_step(item["index"])
        )
        remove_btn.pack(side="right", padx=(2, 6), pady=2)

        down_btn = tk.Button(
            f, text="▼", relief="flat", bd=0, bg="#222b35", fg="#cccccc",
            activebackground="#2b4c7e", activeforeground="#ffffff", font=("Arial", 9), width=2,
            command=lambda: self.move_step(item["index"], 1)
        )
        down_btn.pack(side="right", padx=2, pady=2)

        up_btn = tk.Button(
            f, text="▲", relief="flat", bd=0, bg="#222b35", fg="#cccccc",
            activebackground="#2b4c7e", activeforeground="#ffffff", font=("Arial", 9), width=2,
            command=lambda: self.move_step(item["index"], -1)
        )
        up_btn.pack(side="right", padx=2, pady=2)

        edit_btn = tk.Button(
            f, text="✎", relief="flat", bd=0, bg="#222b35", fg="#58a6ff",
            activebackground="#2b4c7e", activeforeground="#ffffff", font=("Arial", 9), width=2,
            command=lambda: self.select_step(item["index"], focus_edit=True)
        )
        edit_btn.pack(side="right", padx=2, pady=2)

        for w in (f, handle, step_lbl, badge_lbl, coord_lbl, delay_lbl):
            w.bind("<Button-1>", lambda e: self.on_drag_start(e, item["index"]))
            w.bind("<B1-Motion>", self.on_drag_motion)
            w.bind("<ButtonRelease-1>", lambda e: self.on_drag_release(e, item["index"]))
            w.bind("<Double-Button-1>", lambda e: self.select_step(item["index"], focus_edit=True))

        item.update({
            "handle": handle,
            "step_lbl": step_lbl,
            "badge_lbl": badge_lbl,
            "coord_lbl": coord_lbl,
            "delay_lbl": delay_lbl,
            "remove_btn": remove_btn,
            "down_btn": down_btn,
            "up_btn": up_btn,
            "edit_btn": edit_btn,
        })
        return item

    def _update_step_row_widget(self, i: int):
        if not (0 <= i < len(self.current_steps)) or i >= len(self._step_row_pool):
            return
        item = self._step_row_pool[i]
        item["index"] = i
        step = self.current_steps[i]
        total = len(self.current_steps)
        is_selected = (self.selected_step_index == i)

        row_bg = "#1c324b" if is_selected else "#2b2b2b"
        btn_bg = "#1c324b" if is_selected else "#222b35"

        f = item["frame"]
        f.configure(
            bg=row_bg,
            highlightthickness=2 if is_selected else 0,
            highlightbackground="#3b8ed0",
            highlightcolor="#3b8ed0",
        )
        item["handle"].configure(bg=row_bg)

        if step["kind"] == "wait":
            label = f"WAIT {step['delay_ms']}ms"
            color = "orange"
        else:
            label = step["value"] if step["kind"] == "key" else f"[{step['kind']}]"
            color = "white"

        item["step_lbl"].configure(text=f"{i + 1}. {label}", fg=color, bg=row_bg)

        if is_selected:
            item["badge_lbl"].configure(bg=row_bg)
            item["badge_lbl"].pack(side="left", padx=4)
        else:
            item["badge_lbl"].pack_forget()

        if step.get("x") is not None:
            item["coord_lbl"].configure(text=f"@{step['x']},{step['y']}", bg=row_bg)
            item["coord_lbl"].pack(side="left", padx=5)
        else:
            item["coord_lbl"].pack_forget()

        if step["kind"] != "wait" and step.get("delay_ms", 0) > 0:
            item["delay_lbl"].configure(text=f"{step['delay_ms']}ms", bg=row_bg)
            item["delay_lbl"].pack(side="left", padx=5)
        else:
            item["delay_lbl"].pack_forget()

        item["remove_btn"].configure(bg=btn_bg)
        item["edit_btn"].configure(bg=btn_bg)
        item["up_btn"].configure(
            bg=btn_bg,
            fg="#cccccc" if i > 0 else "#555555",
            state="normal" if i > 0 else "disabled",
        )
        item["down_btn"].configure(
            bg=btn_bg,
            fg="#cccccc" if i < total - 1 else "#555555",
            state="normal" if i < total - 1 else "disabled",
        )

    def refresh_steps_display(self, focus_edit=False):
        self.drop_indicator.pack_forget()

        # Keep selected_step_index in valid bounds
        if self.selected_step_index is not None and not (0 <= self.selected_step_index < len(self.current_steps)):
            self.selected_step_index = None

        # Update Selection & Editing Bar
        self.update_selection_panel(focus_edit=focus_edit)

        total = len(self.current_steps)
        if total == 0:
            for item in self._step_row_pool:
                item["frame"].pack_forget()
            self.row_frames.clear()
            if self._empty_stack_lbl is None or not self._empty_stack_lbl.winfo_exists():
                self._empty_stack_lbl = tk.Label(self.steps_display, text="Stack is empty.", fg="#888888", bg="#242424", font=("Arial", 11))
            self._empty_stack_lbl.pack(pady=20)
            return

        if self._empty_stack_lbl is not None and self._empty_stack_lbl.winfo_exists():
            self._empty_stack_lbl.pack_forget()

        while len(self._step_row_pool) < total:
            self._step_row_pool.append(self._create_pooled_step_row())

        for j in range(total, len(self._step_row_pool)):
            self._step_row_pool[j]["frame"].pack_forget()

        self.row_frames = [self._step_row_pool[i]["frame"] for i in range(total)]
        for i in range(total):
            self._update_step_row_widget(i)
            fr = self._step_row_pool[i]["frame"]
            if not fr.winfo_ismapped():
                fr.pack(fill="x", pady=2)

    def move_step(self, index, direction):
        target = index + direction
        if 0 <= target < len(self.current_steps):
            self.current_steps[index], self.current_steps[target] = self.current_steps[target], self.current_steps[index]
            if self.selected_step_index == index:
                self.selected_step_index = target
            elif self.selected_step_index == target:
                self.selected_step_index = index
            if len(self.row_frames) == len(self.current_steps):
                self._update_step_row_widget(index)
                self._update_step_row_widget(target)
                self.update_selection_panel(focus_edit=False)
            else:
                self.refresh_steps_display()

    def remove_step(self, index):
        if 0 <= index < len(self.current_steps):
            del self.current_steps[index]
            if self.selected_step_index == index:
                self.selected_step_index = None
            elif self.selected_step_index is not None and index < self.selected_step_index:
                self.selected_step_index -= 1
            self.refresh_steps_display()

    def on_drag_start(self, event, index):
        self._drag_data = {
            "src": index,
            "active": False,
            "start_y": event.y_root,
            "target": index
        }

    def on_drag_motion(self, event):
        if self._drag_data.get("src") is None:
            return

        if not self._drag_data["active"]:
            if abs(event.y_root - self._drag_data["start_y"]) > 4:
                self._drag_data["active"] = True
                try:
                    self.configure(cursor="fleur")
                except Exception:
                    pass
                src = self._drag_data["src"]
                if 0 <= src < len(self.row_frames):
                    self.row_frames[src].configure(highlightthickness=2, highlightbackground="#3b8ed0")
            else:
                return

        # Auto-scroll if dragging near the top or bottom of the scrollable frame
        try:
            canvas = getattr(self.steps_display, "_parent_canvas", None)
            if canvas and canvas.winfo_exists():
                c_top = canvas.winfo_rooty()
                c_bot = c_top + canvas.winfo_height()
                if event.y_root < c_top + 25:
                    canvas.yview_scroll(-1, "units")
                elif event.y_root > c_bot - 25:
                    canvas.yview_scroll(1, "units")
        except Exception:
            pass

        # Calculate target drop position based on row midpoints
        target_idx = len(self.row_frames)
        for j, fr in enumerate(self.row_frames):
            try:
                mid_y = fr.winfo_rooty() + fr.winfo_height() / 2
                if event.y_root < mid_y:
                    target_idx = j
                    break
            except Exception:
                pass

        if target_idx != self._drag_data.get("target"):
            self._drag_data["target"] = target_idx
            if target_idx < len(self.row_frames):
                self.drop_indicator.pack_configure(before=self.row_frames[target_idx], fill="x", padx=10, pady=1)
            elif self.row_frames:
                self.drop_indicator.pack_configure(after=self.row_frames[-1], fill="x", padx=10, pady=1)

    def on_drag_release(self, event, index=None):
        try:
            self.configure(cursor="")
        except Exception:
            pass

        if self._drag_data.get("active") and self._drag_data.get("src") is not None:
            src = self._drag_data["src"]
            target = self._drag_data.get("target")
            if target is not None and 0 <= src < len(self.current_steps):
                item = self.current_steps.pop(src)
                new_idx = target if target <= src else target - 1
                self.current_steps.insert(new_idx, item)
                if self.selected_step_index == src:
                    self.selected_step_index = new_idx
                elif self.selected_step_index is not None:
                    if src < self.selected_step_index <= new_idx:
                        self.selected_step_index -= 1
                    elif new_idx <= self.selected_step_index < src:
                        self.selected_step_index += 1
            self._drag_data = {"src": None, "active": False, "start_y": 0, "target": None}
            self.drop_indicator.pack_forget()
            self.refresh_steps_display()
        else:
            self._drag_data = {"src": None, "active": False, "start_y": 0, "target": None}
            self.drop_indicator.pack_forget()
            if index is not None:
                if self.selected_step_index == index:
                    self.select_step(index, focus_edit=False)
                else:
                    self.select_step(index, focus_edit=True)
            else:
                self.refresh_steps_display()

    def save(self):
        name = self.name_entry.get().strip() or "Unnamed"
        if not self.bound_trigger:
            self.title_label.configure(text="Trigger Key Required!", fg="red")
            return
        
        if self.kind == "keybind":
            if not self.output_key:
                self.title_label.configure(text="Output Key Required!", fg="red")
                return
            steps = [{"kind": "key", "value": self.output_key, "delay_ms": 0}]
        else:
            if not self.current_steps:
                self.title_label.configure(text="Stack is empty!", fg="red")
                return
            steps = list(self.current_steps)

        macro = Macro(
            id=self.macro_to_edit["id"] if self.macro_to_edit else str(uuid.uuid4()),
            name=name,
            enabled=self.enabled_var.get(),
            kind=self.kind,
            trigger_mode=self.mode_selector.get().lower(),
            trigger=self.bound_trigger,
            interruptible=self.interrupt_var.get(),
            steps=steps
        )
        self.on_save(macro)
        self.close_editor()

class ShortcutEditor(ctk.CTkToplevel):
    def __init__(self, parent, on_save, shortcut_to_edit=None):
        super().__init__(parent)
        
        # Set icon
        try:
            self.icon_img = tk.PhotoImage(file='icon.png')
            self.wm_iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.shortcut_to_edit = shortcut_to_edit
        self.title("Edit Launch Shortcut" if shortcut_to_edit else "New Launch Shortcut")
        self.geometry("580x560")
        self.resizable(False, False)
        self.configure(fg_color="#242424")
        self.on_save = on_save
        
        self.custom_icon_path = shortcut_to_edit.get("custom_icon_path") if shortcut_to_edit else None
        self.target_path = shortcut_to_edit.get("target_path", "") if shortcut_to_edit else ""
        self.shortcut_id = shortcut_to_edit.get("id", str(uuid.uuid4())) if shortcut_to_edit else str(uuid.uuid4())
        self.preview_image = None

        self.main_container = tk.Frame(self, bg="#242424")
        self.main_container.pack(fill="both", expand=True, padx=25, pady=20)

        # Header Title
        title_text = "Edit Launch Shortcut" if shortcut_to_edit else "Add New Launch Shortcut"
        tk.Label(self.main_container, text=title_text, font=("sans-serif", 16, "bold"), fg="#DCE4EE", bg="#242424").pack(anchor="w", pady=(0, 4))
        tk.Label(
            self.main_container,
            text="Configure a shortcut to quickly open DarkAges clients or automation tools.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        ).pack(anchor="w", pady=(0, 20))

        # Shortcut Name
        tk.Label(self.main_container, text="Shortcut Name:", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#242424").pack(anchor="w")
        self.name_entry = ctk.CTkEntry(self.main_container, placeholder_text="e.g. DarkAges, Sapphire, Windower...", width=530)
        self.name_entry.pack(pady=(5, 15), anchor="w")
        if shortcut_to_edit:
            self.name_entry.insert(0, shortcut_to_edit["name"])

        # Target File to Run
        tk.Label(self.main_container, text="Target File to Run:", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#242424").pack(anchor="w")
        target_frame = tk.Frame(self.main_container, bg="#242424")
        target_frame.pack(fill="x", pady=(5, 15))
        
        self.target_entry = ctk.CTkEntry(target_frame, placeholder_text="Path to executable, script, or client...", width=430)
        self.target_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        if shortcut_to_edit:
            self.target_entry.insert(0, shortcut_to_edit["target_path"])
        self.target_entry.bind("<KeyRelease>", lambda e: self.update_icon_preview())

        browse_target_btn = tk.Button(
            target_frame,
            text="Browse...",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.browse_target
        )
        browse_target_btn.pack(side="right")

        # Custom Icon (Optional)
        tk.Label(
            self.main_container,
            text="Custom Icon (Optional - leave empty to use application icon):",
            font=("sans-serif", 10, "bold"),
            fg="#DCE4EE",
            bg="#242424"
        ).pack(anchor="w")
        icon_frame = tk.Frame(self.main_container, bg="#242424")
        icon_frame.pack(fill="x", pady=(5, 15))

        self.icon_entry = ctk.CTkEntry(icon_frame, placeholder_text="Leave blank to use selected application's icon...", width=340)
        self.icon_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        if shortcut_to_edit and shortcut_to_edit.get("custom_icon_path"):
            self.icon_entry.insert(0, shortcut_to_edit["custom_icon_path"])
        self.icon_entry.bind("<KeyRelease>", lambda e: self.update_icon_preview())

        browse_icon_btn = tk.Button(
            icon_frame,
            text="Browse...",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.browse_icon
        )
        browse_icon_btn.pack(side="left", padx=(0, 5))

        clear_icon_btn = tk.Button(
            icon_frame,
            text="Clear",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#555555",
            activeforeground="white",
            activebackground="#666666",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=self.clear_icon
        )
        clear_icon_btn.pack(side="left")

        # Live Icon Preview Card
        preview_box = tk.Frame(self.main_container, bg="#2b2b2b")
        preview_box.pack(fill="x", pady=(5, 15))

        self.preview_icon_label = tk.Label(preview_box, text="", fg="#DCE4EE", bg="#2b2b2b")
        self.preview_icon_label.pack(side="left", padx=15, pady=10)

        preview_text_frame = tk.Frame(preview_box, bg="#2b2b2b")
        preview_text_frame.pack(side="left", fill="both", expand=True, pady=10)

        self.preview_status_label = tk.Label(
            preview_text_frame,
            text="Icon Preview",
            font=("sans-serif", 11, "bold"),
            fg="#DCE4EE",
            bg="#2b2b2b"
        )
        self.preview_status_label.pack(anchor="w")

        self.preview_desc_label = tk.Label(
            preview_text_frame,
            text="Displays custom icon or extracts icon from application.",
            font=("sans-serif", 9),
            fg="#888888",
            bg="#2b2b2b"
        )
        self.preview_desc_label.pack(anchor="w")

        # Error / Validation Label
        self.error_label = tk.Label(self.main_container, text="", fg="red", bg="#242424", font=("sans-serif", 10))
        self.error_label.pack(anchor="w", pady=(0, 10))

        # Action Buttons (Cancel / Save)
        action_frame = tk.Frame(self.main_container, bg="#242424")
        action_frame.pack(fill="x", pady=(5, 0))

        cancel_btn = tk.Button(
            action_frame,
            text="Cancel",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#555555",
            activeforeground="white",
            activebackground="#666666",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = tk.Button(
            action_frame,
            text="Save Shortcut",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.save
        )
        save_btn.pack(side="right")

        # Initial preview update
        self.update_icon_preview()

    def browse_target(self):
        f = filedialog.askopenfilename(
            title="Select Client / Tool Executable or Script",
            filetypes=[
                ("Executables & Scripts", "*.exe *.sh *.desktop *"),
                ("All Files", "*.*")
            ]
        )
        if f:
            self.target_entry.delete(0, "end")
            self.target_entry.insert(0, f)
            if not self.name_entry.get().strip():
                base = os.path.splitext(os.path.basename(f))[0]
                clean_name = base.replace("-", " ").replace("_", " ").title()
                self.name_entry.insert(0, clean_name)
            self.update_icon_preview()

    def browse_icon(self):
        f = filedialog.askopenfilename(
            title="Select Custom Icon Image",
            filetypes=[
                ("Image Files", "*.png *.ico *.jpg *.jpeg *.bmp *.svg"),
                ("All Files", "*.*")
            ]
        )
        if f:
            self.icon_entry.delete(0, "end")
            self.icon_entry.insert(0, f)
            self.update_icon_preview()

    def clear_icon(self):
        self.icon_entry.delete(0, "end")
        self.update_icon_preview()

    def update_icon_preview(self):
        target = self.target_entry.get().strip()
        custom = self.icon_entry.get().strip() or None
        
        tmp_preview = os.path.join(ICONS_CACHE_DIR, f"preview_{self.shortcut_id}.png")
        ok, source_desc = resolve_icon(target, custom, tmp_preview)
        
        if ok and os.path.exists(tmp_preview):
            try:
                self.preview_image = tk.PhotoImage(file=tmp_preview)
                self.preview_icon_label.configure(image=self.preview_image, text="")
            except Exception:
                self.preview_icon_label.configure(image="", text="[IMG]")
        else:
            self.preview_icon_label.configure(image="", text="[None]")

        if source_desc == "custom":
            self.preview_status_label.configure(text="Custom Icon")
            self.preview_desc_label.configure(text="Using user-specified custom icon.")
        elif source_desc == "application_extracted":
            self.preview_status_label.configure(text="Application Icon (Extracted)")
            self.preview_desc_label.configure(text="Extracted automatically from target application.")
        elif source_desc == "fallback_default":
            self.preview_status_label.configure(text="Default Icon")
            self.preview_desc_label.configure(text="No icon found on target; using DALT default icon.")
        else:
            self.preview_status_label.configure(text="No Icon")
            self.preview_desc_label.configure(text="Select a valid file to resolve an icon.")

    def save(self):
        name = self.name_entry.get().strip()
        target = self.target_entry.get().strip()
        custom = self.icon_entry.get().strip() or None

        if not target:
            self.error_label.configure(text="Error: Target file is required.")
            self.target_entry.configure(border_color="red")
            return
        if not os.path.exists(os.path.expanduser(target)):
            self.error_label.configure(text="Error: Target file does not exist on disk.")
            self.target_entry.configure(border_color="red")
            return

        if not name:
            name = os.path.splitext(os.path.basename(target))[0]

        cache_icon_path = os.path.join(ICONS_CACHE_DIR, f"{self.shortcut_id}.png")
        resolve_icon(target, custom, cache_icon_path)

        shortcut_data: Shortcut = {
            "id": self.shortcut_id,
            "name": name,
            "target_path": target,
            "custom_icon_path": custom,
            "icon_cache_path": cache_icon_path,
        }
        self.on_save(shortcut_data)
        self.destroy()

_ALL_LAZY_FRAMES = ("butterwalk", "spacebar", "controller", "macros", "autofollowing", "credits")

class DarkAgesApp(ctk.CTk):
    def __getattr__(self, item: str):
        if not item.startswith("_"):
            for frame_name in _ALL_LAZY_FRAMES:
                if frame_name not in self._initialized_frames:
                    self._ensure_frame_setup(frame_name)
                    if item in self.__dict__:
                        return self.__dict__[item]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{item}'")

    def _ensure_frame_setup(self, name: str) -> None:
        if name in self._initialized_frames:
            return
        self._initialized_frames.add(name)
        if name == "butterwalk":
            self._setup_butterwalk_frame()
        elif name == "spacebar":
            self._setup_spacebar_frame()
        elif name == "controller":
            self._setup_controller_frame()
        elif name == "macros":
            self._setup_macro_frame()
        elif name == "autofollowing":
            self._setup_autofollowing_frame()
        elif name == "credits":
            self._setup_credits_frame()

    def __init__(self, macro_feature: MacroFeature, loop: asyncio.AbstractEventLoop):
        super().__init__()

        # Set icon
        try:
            self.icon_img = tk.PhotoImage(file='icon.png')
            self.wm_iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.macro_feature = macro_feature
        self.loop = loop
        self.title("DarkAges Linux Tool")
        self.geometry("900x800")
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#242424")

        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar / Navigation
        self.navigation_frame = tk.Frame(self, bg="#2b2b2b", bd=0, highlightthickness=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(8, weight=1)

        self.title_container = tk.Frame(self.navigation_frame, bg="#2b2b2b")
        self.title_container.grid(row=0, column=0, padx=20, pady=(20, 15))

        self.navigation_frame_label = tk.Label(
            self.title_container,
            text="DarkAges Linux Tool",
            font=("sans-serif", 12, "bold"),
            fg="#DCE4EE",
            bg="#2b2b2b"
        )
        self.navigation_frame_label.pack()

        self.version_label = tk.Label(
            self.title_container,
            text="Version 1.4",
            font=("sans-serif", 9),
            fg="#888888",
            bg="#2b2b2b"
        )
        self.version_label.pack(pady=(2, 0))

        nav_btn_cfg = {
            "font": ("sans-serif", 10, "bold"),
            "fg": "#DCE4EE",
            "bg": "#2b2b2b",
            "activeforeground": "white",
            "activebackground": "#4d4d4d",
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "anchor": "w",
            "padx": 16,
            "pady": 10,
            "cursor": "hand2",
        }

        self.home_button = tk.Button(self.navigation_frame, text="Home", command=self.home_button_event, **nav_btn_cfg)
        self.home_button.grid(row=1, column=0, sticky="ew")

        self.butterwalk_button = tk.Button(self.navigation_frame, text="Butterwalk", command=self.butterwalk_button_event, **nav_btn_cfg)
        self.butterwalk_button.grid(row=2, column=0, sticky="ew")

        self.spacebar_button = tk.Button(self.navigation_frame, text="Continuous Assail", command=self.spacebar_button_event, **nav_btn_cfg)
        self.spacebar_button.grid(row=3, column=0, sticky="ew")

        self.controller_button = tk.Button(self.navigation_frame, text="Controller Inputs", command=self.controller_button_event, **nav_btn_cfg)
        self.controller_button.grid(row=4, column=0, sticky="ew")

        self.macro_button = tk.Button(self.navigation_frame, text="Macros", command=self.macro_button_event, **nav_btn_cfg)
        self.macro_button.grid(row=5, column=0, sticky="ew")

        self.autofollow_button = tk.Button(self.navigation_frame, text="Autofollowing", command=self.autofollow_button_event, **nav_btn_cfg)
        self.autofollow_button.grid(row=6, column=0, sticky="ew")

        self.credits_button = tk.Button(self.navigation_frame, text="Credits", command=self.credits_button_event, **nav_btn_cfg)
        self.credits_button.grid(row=7, column=0, sticky="ew")

        # Create frames
        self.home_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        self.butterwalk_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        self.spacebar_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        self.controller_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        self.macro_frame = tk.Frame(self, bg="#242424", bd=0, highlightthickness=0)
        self.autofollowing_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        self.credits_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="#242424")
        
        enable_linux_scroll(self.home_frame)
        enable_linux_scroll(self.butterwalk_frame)
        enable_linux_scroll(self.spacebar_frame)
        enable_linux_scroll(self.controller_frame)
        enable_linux_scroll(self.autofollowing_frame)
        enable_linux_scroll(self.credits_frame)

        self._initialized_frames: set[str] = {"home"}
        self._gui_cache: dict = {}
        self._macro_editor: MacroEditor | None = None
        self._macro_card_widgets: dict[str, dict] = {}
        self._setup_home_frame()

        # Select default frame
        self.select_frame_by_name("home")
        
        # Footer for monitoring
        self.footer_frame = tk.Frame(self, height=40, bg="#2b2b2b", bd=0, highlightthickness=0)
        self.footer_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.footer_status = tk.Label(self.footer_frame, text="○ Inactive", font=("sans-serif", 9, "bold"), fg="#888888", bg="#2b2b2b")
        self.footer_status.pack(side="left", padx=20, pady=8)
        
        import input_hub
        kb, mice = input_hub.get_device_counts()
        pads = input_hub.get_controller_count()
        self.footer_devices = tk.Label(self.footer_frame, text=f"Devices: {kb} KB, {mice} Mice, {pads} Pad", font=("sans-serif", 9), fg="#DCE4EE", bg="#2b2b2b")
        self.footer_devices.pack(side="left", padx=10, pady=8)
        
        self.footer_last_event = tk.Label(self.footer_frame, text="Last Event: None", font=("sans-serif", 9, "bold"), fg="orange", bg="#2b2b2b")
        self.footer_last_event.pack(side="right", padx=20, pady=8)
        
        # Start update loop
        self.update_gui()

    def _setup_home_frame(self):
        self.home_frame.grid_columnconfigure(0, weight=1)
        self.home_label = tk.Label(self.home_frame, text="General Status", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.home_label.pack(padx=20, pady=(20, 15))
        
        # Quick Launch Section (DarkAges clients and tools)
        self.quick_launch_container = tk.Frame(self.home_frame, bg="#2b2b2b")
        self.quick_launch_container.pack(fill="x", padx=20, pady=(0, 10))

        ql_header = tk.Frame(self.quick_launch_container, bg="#2b2b2b")
        ql_header.pack(fill="x", padx=15, pady=(12, 6))

        ql_title_box = tk.Frame(ql_header, bg="#2b2b2b")
        ql_title_box.pack(side="left")
        tk.Label(ql_title_box, text="Quick Launch (Clients & Tools)", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#2b2b2b").pack(anchor="w")
        tk.Label(ql_title_box, text="Launch DarkAges clients and tools directly from DALT.", font=("sans-serif", 9), fg="#888888", bg="#2b2b2b").pack(anchor="w")

        self.add_shortcut_btn = tk.Button(
            ql_header,
            text="+ Add New",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.open_shortcut_editor
        )
        self.add_shortcut_btn.pack(side="right")

        self.shortcuts_list_frame = tk.Frame(self.quick_launch_container, bg="#2b2b2b")
        self.shortcuts_list_frame.pack(fill="x", padx=15, pady=(0, 12))

        self.refresh_shortcuts_display()

        # Window Hooks Management
        hooks_container = tk.Frame(self.home_frame, bg="#2b2b2b")
        hooks_container.pack(fill="x", padx=20, pady=10)
        
        tk.Label(hooks_container, text="Active Window Hooks:", font=("sans-serif", 11, "bold"), fg="#DCE4EE", bg="#2b2b2b").pack(pady=(12, 4))
        tk.Label(hooks_container, text="(The tool will only arm when these titles are focused)", font=("sans-serif", 8), fg="#888888", bg="#2b2b2b").pack(pady=(0, 8))

        # Input to add new hook
        hook_input_frame = tk.Frame(hooks_container, bg="#2b2b2b")
        hook_input_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.hook_entry = ctk.CTkEntry(hook_input_frame, placeholder_text="Enter Window Title...")
        self.hook_entry.pack(side="left", fill="x", expand=True)
        self.hook_entry.bind("<Return>", lambda e: self.add_hook())
        
        tk.Button(
            hook_input_frame,
            text="+ Add",
            font=("sans-serif", 10, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.add_hook
        ).pack(side="left", padx=(10, 0))

        # Box / Table for active window hooks (displays at most 5 before scrolling)
        self.hooks_table_frame = tk.Frame(hooks_container, bg="#202020")
        self.hooks_table_frame.pack(fill="x", padx=20, pady=(0, 12))

        # Table header
        hooks_header = tk.Frame(self.hooks_table_frame, bg="#2A2A2A")
        hooks_header.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hooks_header, text="Window Title / Hook", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#2A2A2A").pack(side="left", padx=10, pady=4)
        tk.Label(hooks_header, text="Action", font=("sans-serif", 10, "bold"), fg="#888888", bg="#2A2A2A").pack(side="right", padx=10, pady=4)

        self.hooks_list_frame = ctk.CTkScrollableFrame(self.hooks_table_frame, height=195, fg_color="#202020")
        self.hooks_list_frame.pack(fill="x", padx=4, pady=(0, 4))
        enable_linux_scroll(self.hooks_list_frame)
        
        self.refresh_hooks_display()

        # Input Suppression Toggle
        self.suppress_frame = tk.Frame(self.home_frame, bg="#242424")
        self.suppress_frame.pack(pady=15)
        
        self.suppress_switch = ctk.CTkSwitch(
            self.suppress_frame,
            text="Suppress Trigger Keys",
            bg_color="#242424",
            command=self.toggle_suppression,
            progress_color="orange"
        )
        self.suppress_switch.pack(side="top")
        
        tk.Label(
            self.suppress_frame,
            text="(Suppresses triggers: ` / ~, F-keys, Home, Del, End, Ins; PgUp / PgDn only if bound to macro/hotkey)",
            font=("sans-serif", 8),
            fg="#888888",
            bg="#242424"
        ).pack(pady=5)

    def add_hook(self):
        val = self.hook_entry.get().strip()
        if val and val not in state["window_hooks"]:
            from state import save_config
            state["window_hooks"].append(val)
            self.hook_entry.delete(0, 'end')
            self.refresh_hooks_display()
            save_config()
        
    def remove_hook(self, val):
        if val in state["window_hooks"]:
            from state import save_config
            state["window_hooks"].remove(val)
            self.refresh_hooks_display()
            save_config()

    def refresh_hooks_display(self):
        for widget in self.hooks_list_frame.winfo_children():
            widget.destroy()
        
        if not state["window_hooks"]:
            placeholder = tk.Label(
                self.hooks_list_frame,
                text="No window hooks configured. Add a title above.",
                font=("sans-serif", 10),
                fg="#888888",
                bg="#202020"
            )
            placeholder.pack(pady=20)
            return

        for hook in state["window_hooks"]:
            f = tk.Frame(self.hooks_list_frame, bg="#2B2B2B")
            f.pack(fill="x", pady=2)
            tk.Label(f, text=hook, font=("sans-serif", 10), fg="#DCE4EE", bg="#2B2B2B").pack(side="left", padx=10, pady=4)
            tk.Button(
                f,
                text="×",
                font=("sans-serif", 11, "bold"),
                fg="white",
                bg="#AA4444",
                activeforeground="white",
                activebackground="#882222",
                relief="flat",
                bd=0,
                padx=6,
                pady=1,
                cursor="hand2",
                command=lambda v=hook: self.remove_hook(v)
            ).pack(side="right", padx=6, pady=4)

    def refresh_shortcuts_display(self):
        for widget in self.shortcuts_list_frame.winfo_children():
            widget.destroy()

        self._shortcut_photos = {}

        if not state["shortcuts"]:
            placeholder = tk.Label(
                self.shortcuts_list_frame,
                text="No launch shortcuts added yet. Click '+ Add New' to configure quick launch shortcuts.",
                font=("sans-serif", 10),
                fg="#888888",
                bg="#2b2b2b"
            )
            placeholder.pack(pady=15)
            return

        for sc in state["shortcuts"]:
            card_bg = "#242424"
            card = tk.Frame(self.shortcuts_list_frame, bg=card_bg)
            card.pack(fill="x", pady=3)

            # Icon
            icon_lbl = tk.Label(card, text="", fg="#DCE4EE", bg=card_bg)
            icon_lbl.pack(side="left", padx=(10, 8), pady=6)

            cache_path = sc.get("icon_cache_path")
            if not cache_path or not os.path.exists(cache_path):
                cache_path = os.path.join(ICONS_CACHE_DIR, f"{sc['id']}.png")
                resolve_icon(sc.get("target_path"), sc.get("custom_icon_path"), cache_path)
                sc["icon_cache_path"] = cache_path

            if os.path.exists(cache_path):
                try:
                    photo = tk.PhotoImage(file=cache_path)
                    self._shortcut_photos[sc["id"]] = photo
                    icon_lbl.configure(image=photo)
                except Exception:
                    icon_lbl.configure(text="🚀")
            else:
                icon_lbl.configure(text="🚀")

            # Info (Name and Target path)
            info_frame = tk.Frame(card, bg=card_bg)
            info_frame.pack(side="left", fill="both", expand=True, padx=5, pady=6)
            tk.Label(info_frame, text=sc["name"], font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg=card_bg).pack(anchor="w")

            disp_path = sc["target_path"]
            if len(disp_path) > 55:
                disp_path = "..." + disp_path[-52:]
            tk.Label(info_frame, text=disp_path, font=("sans-serif", 8), fg="#888888", bg=card_bg).pack(anchor="w")

            # Actions (Launch, Edit, Delete)
            btn_frame = tk.Frame(card, bg=card_bg)
            btn_frame.pack(side="right", padx=10, pady=6)

            launch_btn = tk.Button(
                btn_frame,
                text="▶ Launch",
                font=("sans-serif", 9, "bold"),
                fg="white",
                bg="#2E7D32",
                activeforeground="white",
                activebackground="#1B5E20",
                relief="flat",
                bd=0,
                padx=10,
                pady=3,
                cursor="hand2",
                command=lambda s=sc: self.launch_target_shortcut(s)
            )
            launch_btn.pack(side="left", padx=4)

            edit_btn = tk.Button(
                btn_frame,
                text="Edit",
                font=("sans-serif", 9, "bold"),
                fg="white",
                bg="#4444AA",
                activeforeground="white",
                activebackground="#333388",
                relief="flat",
                bd=0,
                padx=10,
                pady=3,
                cursor="hand2",
                command=lambda s=sc: self.open_shortcut_editor(s)
            )
            edit_btn.pack(side="left", padx=4)

            del_btn = tk.Button(
                btn_frame,
                text="×",
                font=("sans-serif", 11, "bold"),
                fg="white",
                bg="#AA4444",
                activeforeground="white",
                activebackground="#882222",
                relief="flat",
                bd=0,
                padx=7,
                pady=2,
                cursor="hand2",
                command=lambda s=sc: self.delete_shortcut(s)
            )
            del_btn.pack(side="left", padx=2)

    def open_shortcut_editor(self, shortcut_to_edit=None):
        editor = ShortcutEditor(self, self.save_shortcut_callback, shortcut_to_edit=shortcut_to_edit)
        editor.grab_set()

    def save_shortcut_callback(self, shortcut_data: Shortcut):
        existing_idx = None
        for i, s in enumerate(state["shortcuts"]):
            if s["id"] == shortcut_data["id"]:
                existing_idx = i
                break
        if existing_idx is not None:
            state["shortcuts"][existing_idx] = shortcut_data
        else:
            state["shortcuts"].append(shortcut_data)
        save_shortcuts(state["shortcuts"])
        self.refresh_shortcuts_display()

    def delete_shortcut(self, shortcut: Shortcut):
        cache = shortcut.get("icon_cache_path")
        if cache and os.path.exists(cache):
            try:
                os.remove(cache)
            except OSError:
                pass
        state["shortcuts"] = [s for s in state["shortcuts"] if s["id"] != shortcut["id"]]
        save_shortcuts(state["shortcuts"])
        self.refresh_shortcuts_display()

    def launch_target_shortcut(self, shortcut: Shortcut):
        ok, msg = launch_shortcut(shortcut)
        state["last_event"] = msg

    def toggle_suppression(self):
        import input_hub
        from state import save_config
        enabled = self.suppress_switch.get() == 1
        state["suppress_triggers"] = enabled
        input_hub.toggle_suppression(enabled)
        save_config()

    def _setup_butterwalk_frame(self):
        self.bw_title = tk.Label(self.butterwalk_frame, text="Butterwalk Settings", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.bw_title.pack(padx=20, pady=(20, 10))

        self.bw_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable Butterwalk", bg_color="#242424", command=self.toggle_bw)
        self.bw_switch.pack(padx=20, pady=8)
        if state["butterwalk"]: self.bw_switch.select()

        self.zxcv_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable ZXCV Mapping", bg_color="#242424", command=self.toggle_zxcv)
        self.zxcv_switch.pack(padx=20, pady=8)
        if state["zxcv_enabled"]: self.zxcv_switch.select()

        # Toggle Hotkey
        bw_hotkey_frame = tk.Frame(self.butterwalk_frame, bg="#242424")
        bw_hotkey_frame.pack(padx=20, pady=10)
        tk.Label(bw_hotkey_frame, text="Toggle Hotkey:", font=("sans-serif", 11, "bold"), fg="#DCE4EE", bg="#242424").pack(side="left", padx=5)
        self.bw_hotkey_entry = ctk.CTkEntry(bw_hotkey_frame, width=140)
        self.bw_hotkey_entry.insert(0, state["butterwalk_hotkey"])
        self.bw_hotkey_entry.pack(side="left", padx=5)
        self.bw_hotkey_entry.bind("<Return>", lambda e: self.apply_bw_hotkey())
        self.bw_hotkey_apply_btn = tk.Button(
            bw_hotkey_frame,
            text="Apply",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.apply_bw_hotkey
        )
        self.bw_hotkey_apply_btn.pack(side="left", padx=5)
        self.bw_hotkey_bind_btn = tk.Button(
            bw_hotkey_frame,
            text="Record",
            font=("sans-serif", 9, "bold"),
            fg="black",
            bg="orange",
            activeforeground="black",
            activebackground="#CC8800",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self.start_hotkey_binding("butterwalk")
        )
        self.bw_hotkey_bind_btn.pack(side="left", padx=5)

        self.multiplier_label = tk.Label(self.butterwalk_frame, text=f"Multiplier: {state['multiplier']}x", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#242424")
        self.multiplier_label.pack(padx=20, pady=(15, 0))

        self.multiplier_desc = tk.Label(
            self.butterwalk_frame,
            text="How many times the keystroke is repeated at the ms rate selected.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.multiplier_desc.pack(padx=20, pady=(2, 6))
        
        self.multiplier_slider = ctk.CTkSlider(self.butterwalk_frame, from_=1, to=5, number_of_steps=4, command=self.set_multiplier)
        self.multiplier_slider.set(state["multiplier"])
        self.multiplier_slider.pack(padx=20, pady=(0, 15), fill="x")
        self._bw_slider_dragging = False
        self.multiplier_slider.bind("<Button-1>", lambda e: setattr(self, "_bw_slider_dragging", True), add="+")
        self.multiplier_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_bw_slider_dragging", False), add="+")

        # Repeat Speed (ms)
        self.bw_speed_label = tk.Label(self.butterwalk_frame, text=f"Repeat Speed: {state['butterwalk_delay_ms']} ms", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#242424")
        self.bw_speed_label.pack(padx=20, pady=(10, 0))

        self.bw_speed_desc = tk.Label(
            self.butterwalk_frame,
            text="How long, in milliseconds, the program waits between repeating the keystrokes.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.bw_speed_desc.pack(padx=20, pady=(2, 6))

        self.bw_speed_slider = ctk.CTkSlider(self.butterwalk_frame, from_=1, to=100, number_of_steps=99, command=self.set_butterwalk_delay)
        self.bw_speed_slider.set(state["butterwalk_delay_ms"])
        self.bw_speed_slider.pack(padx=20, pady=(0, 10), fill="x")
        self._bw_speed_slider_dragging = False
        self.bw_speed_slider.bind("<Button-1>", lambda e: setattr(self, "_bw_speed_slider_dragging", True), add="+")
        self.bw_speed_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_bw_speed_slider_dragging", False), add="+")

        self.input_display_label = tk.Label(self.butterwalk_frame, text="Keys Pressed: —", font=("monospace", 11), fg="#DCE4EE", bg="#242424")
        self.input_display_label.pack(padx=20, pady=(20, 10))

    def _setup_spacebar_frame(self):
        self.space_title = tk.Label(self.spacebar_frame, text="Continuous Assail", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.space_title.pack(padx=20, pady=(20, 10))

        self.space_desc = tk.Label(
            self.spacebar_frame,
            text="Continuously repeats Spacebar inputs (Assail) while held down, even during macro execution.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.space_desc.pack(padx=20, pady=(0, 15))

        self.space_switch = ctk.CTkSwitch(self.spacebar_frame, text="Enable Continuous Assail", bg_color="#242424", command=self.toggle_space)
        self.space_switch.pack(padx=20, pady=8)
        if state["space_enabled"]: self.space_switch.select()

        # Toggle Hotkey
        space_hotkey_frame = tk.Frame(self.spacebar_frame, bg="#242424")
        space_hotkey_frame.pack(padx=20, pady=10)
        tk.Label(space_hotkey_frame, text="Toggle Hotkey:", font=("sans-serif", 11, "bold"), fg="#DCE4EE", bg="#242424").pack(side="left", padx=5)
        self.space_hotkey_entry = ctk.CTkEntry(space_hotkey_frame, width=140)
        self.space_hotkey_entry.insert(0, state["space_hotkey"])
        self.space_hotkey_entry.pack(side="left", padx=5)
        self.space_hotkey_entry.bind("<Return>", lambda e: self.apply_space_hotkey())
        self.space_hotkey_apply_btn = tk.Button(
            space_hotkey_frame,
            text="Apply",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.apply_space_hotkey
        )
        self.space_hotkey_apply_btn.pack(side="left", padx=5)
        self.space_hotkey_bind_btn = tk.Button(
            space_hotkey_frame,
            text="Record",
            font=("sans-serif", 9, "bold"),
            fg="black",
            bg="orange",
            activeforeground="black",
            activebackground="#CC8800",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self.start_hotkey_binding("space")
        )
        self.space_hotkey_bind_btn.pack(side="left", padx=5)

        self.space_multiplier_label = tk.Label(self.spacebar_frame, text=f"Repeat Multiplier: {state['space_multiplier']}x", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#242424")
        self.space_multiplier_label.pack(padx=20, pady=(15, 0))

        self.space_multiplier_desc = tk.Label(
            self.spacebar_frame,
            text="How many times the keystroke is repeated at the ms rate selected.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.space_multiplier_desc.pack(padx=20, pady=(2, 6))
        
        self.space_multiplier_slider = ctk.CTkSlider(self.spacebar_frame, from_=1, to=5, number_of_steps=4, command=self.set_space_multiplier)
        self.space_multiplier_slider.set(state["space_multiplier"])
        self.space_multiplier_slider.pack(padx=20, pady=(0, 15), fill="x")
        self._space_slider_dragging = False
        self.space_multiplier_slider.bind("<Button-1>", lambda e: setattr(self, "_space_slider_dragging", True), add="+")
        self.space_multiplier_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_space_slider_dragging", False), add="+")

        # Repeat Speed (ms)
        self.space_speed_label = tk.Label(self.spacebar_frame, text=f"Repeat Speed: {state['space_delay_ms']} ms", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#242424")
        self.space_speed_label.pack(padx=20, pady=(10, 0))

        self.space_speed_desc = tk.Label(
            self.spacebar_frame,
            text="How long, in milliseconds, the program waits between repeating the keystrokes.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.space_speed_desc.pack(padx=20, pady=(2, 6))

        self.space_speed_slider = ctk.CTkSlider(self.spacebar_frame, from_=1, to=100, number_of_steps=99, command=self.set_space_delay)
        self.space_speed_slider.set(state["space_delay_ms"])
        self.space_speed_slider.pack(padx=20, pady=(0, 10), fill="x")
        self._space_speed_slider_dragging = False
        self.space_speed_slider.bind("<Button-1>", lambda e: setattr(self, "_space_speed_slider_dragging", True), add="+")
        self.space_speed_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_space_speed_slider_dragging", False), add="+")

        self.space_input_display_label = tk.Label(self.spacebar_frame, text="Keys Pressed: —", font=("monospace", 11), fg="#DCE4EE", bg="#242424")
        self.space_input_display_label.pack(padx=20, pady=(20, 10))

    def _setup_controller_frame(self):
        self._ctrl_editing_layer = "base"  # "base" or "layer"
        self._ctrl_selected_input: str | None = None
        self._ctrl_row_widgets: dict[str, dict] = {}
        self._ctrl_listening_output = False

        self.ctrl_title = tk.Label(self.controller_frame, text="Controller Inputs", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.ctrl_title.pack(padx=20, pady=(20, 6))

        self.ctrl_desc = tk.Label(
            self.controller_frame,
            text="Full native gamepad mapping: buttons, triggers, DPAD, analog sticks, modifier layers, and mouse cursor emulation.",
            font=("sans-serif", 10),
            fg="#888888",
            bg="#242424"
        )
        self.ctrl_desc.pack(padx=20, pady=(0, 8))

        # Connected Controller Status Banner
        self.ctrl_device_banner = tk.Label(
            self.controller_frame,
            text="Connected Controllers: Checking...",
            font=("sans-serif", 10, "bold"),
            fg="#58a6ff",
            bg="#242424"
        )
        self.ctrl_device_banner.pack(padx=20, pady=(0, 10))

        # Top Toggles Card
        toggles_card = tk.Frame(self.controller_frame, bg="#2b2b2b")
        toggles_card.pack(fill="x", padx=20, pady=(0, 10))

        self.controller_switch = ctk.CTkSwitch(toggles_card, text="Enable Controller Mapping", bg_color="#2b2b2b", command=self.toggle_controller)
        self.controller_switch.pack(padx=20, pady=(12, 6))
        if state["controller_enabled"]: self.controller_switch.select()

        # Toggle Hotkey
        ctrl_hotkey_frame = tk.Frame(toggles_card, bg="#2b2b2b")
        ctrl_hotkey_frame.pack(padx=20, pady=6)
        tk.Label(ctrl_hotkey_frame, text="Toggle Hotkey:", font=("sans-serif", 11, "bold"), fg="#DCE4EE", bg="#2b2b2b").pack(side="left", padx=5)
        self.ctrl_hotkey_entry = ctk.CTkEntry(ctrl_hotkey_frame, width=140)
        self.ctrl_hotkey_entry.insert(0, state["controller_hotkey"])
        self.ctrl_hotkey_entry.pack(side="left", padx=5)
        self.ctrl_hotkey_entry.bind("<Return>", lambda e: self.apply_ctrl_hotkey())
        self.ctrl_hotkey_apply_btn = tk.Button(
            ctrl_hotkey_frame,
            text="Apply",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.apply_ctrl_hotkey
        )
        self.ctrl_hotkey_apply_btn.pack(side="left", padx=5)
        self.ctrl_hotkey_bind_btn = tk.Button(
            ctrl_hotkey_frame,
            text="Record",
            font=("sans-serif", 9, "bold"),
            fg="black",
            bg="orange",
            activeforeground="black",
            activebackground="#CC8800",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self.start_hotkey_binding("controller")
        )
        self.ctrl_hotkey_bind_btn.pack(side="left", padx=5)

        sub_toggles = tk.Frame(toggles_card, bg="#2b2b2b")
        sub_toggles.pack(padx=20, pady=(4, 12))

        self.dpad_switch = ctk.CTkSwitch(sub_toggles, text="DPAD Mapping", bg_color="#2b2b2b", command=self.toggle_dpad)
        self.dpad_switch.pack(side="left", padx=10)
        if state["dpad_enabled"]: self.dpad_switch.select()

        self.joystick_switch = ctk.CTkSwitch(sub_toggles, text="Left Stick Mapping", bg_color="#2b2b2b", command=self.toggle_joystick)
        self.joystick_switch.pack(side="left", padx=10)
        if state["joystick_enabled"]: self.joystick_switch.select()

        self.mouse_control_switch = ctk.CTkSwitch(
            sub_toggles,
            text="Right Stick Mouse Control",
            bg_color="#2b2b2b",
            command=self.toggle_mouse_control
        )
        self.mouse_control_switch.pack(side="left", padx=10)
        if state["right_stick_mouse_enabled"]: self.mouse_control_switch.select()

        # Analog Calibration & Mouse Sensitivity Card
        calib_card = tk.Frame(self.controller_frame, bg="#2b2b2b")
        calib_card.pack(fill="x", padx=20, pady=(0, 10))

        self.mouse_sens_label = tk.Label(
            calib_card,
            text=f"Right Stick Sensitivity: {state['mouse_sensitivity']}% of {state['mouse_dpi']} DPI",
            font=("sans-serif", 11, "bold"),
            fg="#DCE4EE",
            bg="#2b2b2b"
        )
        self.mouse_sens_label.pack(padx=20, pady=(12, 0))

        self.mouse_sens_slider = ctk.CTkSlider(
            calib_card,
            from_=1,
            to=100,
            number_of_steps=99,
            command=self.set_mouse_sensitivity
        )
        self.mouse_sens_slider.set(state["mouse_sensitivity"])
        self.mouse_sens_slider.pack(padx=20, pady=6, fill="x")
        self._sens_slider_dragging = False
        self.mouse_sens_slider.bind("<Button-1>", lambda e: setattr(self, "_sens_slider_dragging", True), add="+")
        self.mouse_sens_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_sens_slider_dragging", False), add="+")

        dpi_frame = tk.Frame(calib_card, bg="#2b2b2b")
        dpi_frame.pack(padx=20, pady=4)
        tk.Label(dpi_frame, text="Hardware Mouse DPI:", font=("sans-serif", 10), fg="#DCE4EE", bg="#2b2b2b").pack(side="left", padx=5)
        self.mouse_dpi_entry = ctk.CTkEntry(dpi_frame, width=90)
        self.mouse_dpi_entry.insert(0, str(state["mouse_dpi"]))
        self.mouse_dpi_entry.pack(side="left", padx=5)
        self.mouse_dpi_entry.bind("<Return>", lambda e: self.set_mouse_dpi())
        self.mouse_dpi_entry.bind("<FocusOut>", lambda e: self.set_mouse_dpi())
        tk.Button(
            dpi_frame,
            text="Apply DPI",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.set_mouse_dpi
        ).pack(side="left", padx=5)

        # Deadzone Sliders (Left & Right Stick)
        dz_row = tk.Frame(calib_card, bg="#2b2b2b")
        dz_row.pack(fill="x", padx=20, pady=(6, 12))
        dz_row.grid_columnconfigure(0, weight=1)
        dz_row.grid_columnconfigure(1, weight=1)

        ls_dz_box = tk.Frame(dz_row, bg="#2b2b2b")
        ls_dz_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.ls_dz_label = tk.Label(ls_dz_box, text=f"Left Stick Deadzone: {state['left_stick_deadzone']}%", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#2b2b2b")
        self.ls_dz_label.pack(anchor="w")
        self.ls_dz_slider = ctk.CTkSlider(ls_dz_box, from_=5, to=40, number_of_steps=35, command=self.set_left_deadzone)
        self.ls_dz_slider.set(state["left_stick_deadzone"])
        self.ls_dz_slider.pack(fill="x", pady=4)
        self._ls_dz_dragging = False
        self.ls_dz_slider.bind("<Button-1>", lambda e: setattr(self, "_ls_dz_dragging", True), add="+")
        self.ls_dz_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_ls_dz_dragging", False), add="+")

        rs_dz_box = tk.Frame(dz_row, bg="#2b2b2b")
        rs_dz_box.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.rs_dz_label = tk.Label(rs_dz_box, text=f"Right Stick Deadzone: {state['right_stick_deadzone']}%", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#2b2b2b")
        self.rs_dz_label.pack(anchor="w")
        self.rs_dz_slider = ctk.CTkSlider(rs_dz_box, from_=5, to=40, number_of_steps=35, command=self.set_right_deadzone)
        self.rs_dz_slider.set(state["right_stick_deadzone"])
        self.rs_dz_slider.pack(fill="x", pady=4)
        self._rs_dz_dragging = False
        self.rs_dz_slider.bind("<Button-1>", lambda e: setattr(self, "_rs_dz_dragging", True), add="+")
        self.rs_dz_slider.bind("<ButtonRelease-1>", lambda e: setattr(self, "_rs_dz_dragging", False), add="+")

        # Live Input Monitor Line
        self.ctrl_input_display_label = tk.Label(self.controller_frame, text="Keys / Axes Pressed: —", font=("monospace", 11), fg="#DCE4EE", bg="#242424")
        self.ctrl_input_display_label.pack(padx=20, pady=(4, 8))

        # --- BUTTON MAPPING SECTION ---
        mapper_card = tk.Frame(self.controller_frame, bg="#2b2b2b")
        mapper_card.pack(fill="x", padx=20, pady=(0, 20))

        mapper_header = tk.Frame(mapper_card, bg="#2b2b2b")
        mapper_header.pack(fill="x", padx=15, pady=(12, 6))

        tk.Label(mapper_header, text="Controller Button & Axis Remapper", font=("sans-serif", 13, "bold"), fg="#DCE4EE", bg="#2b2b2b").pack(side="left")

        self.ctrl_detect_btn = tk.Button(
            mapper_header,
            text="Press Pad Input to Select",
            font=("sans-serif", 9, "bold"),
            fg="black",
            bg="orange",
            activeforeground="black",
            activebackground="#CC8800",
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.start_controller_input_detect
        )
        self.ctrl_detect_btn.pack(side="right", padx=4)

        # Layer & Preset Toolbar
        toolbar_row = tk.Frame(mapper_card, bg="#2b2b2b")
        toolbar_row.pack(fill="x", padx=15, pady=(0, 8))

        tk.Label(toolbar_row, text="Editing Layer:", font=("sans-serif", 10, "bold"), fg="#DCE4EE", bg="#2b2b2b").pack(side="left", padx=(0, 6))
        self.ctrl_layer_selector = ctk.CTkSegmentedButton(
            toolbar_row,
            values=["Base Layer", "Modifier Layer (Chord)"],
            command=self.switch_controller_edit_layer
        )
        self.ctrl_layer_selector.set("Base Layer")
        self.ctrl_layer_selector.pack(side="left", padx=(0, 12))

        tk.Button(
            toolbar_row,
            text="Preset: Movement Only",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#4d4d4d",
            activeforeground="white",
            activebackground="#666666",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.apply_minimal_controller_preset
        ).pack(side="right", padx=4)

        tk.Button(
            toolbar_row,
            text="Reset: Dark Ages Default",
            font=("sans-serif", 9, "bold"),
            fg="white",
            bg="#1f6feb",
            activeforeground="white",
            activebackground="#1856b8",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.reset_default_controller_preset
        ).pack(side="right", padx=4)

        # Selected Button Inline Editor Bar
        self.ctrl_edit_bar = tk.Frame(mapper_card, bg="#1c2430")
        self.ctrl_edit_bar.pack(fill="x", padx=15, pady=(0, 8))

        # Interactive Visual Controller Canvas (Single X11 window for zero-lag rendering)
        self._ctrl_canvas_items: dict[str, dict[str, int]] = {}
        self._ctrl_canvas_cx = 380
        self.ctrl_canvas = tk.Canvas(
            mapper_card,
            width=760,
            height=435,
            bg="#1d1e1e",
            highlightthickness=1,
            highlightbackground="#383838",
            bd=0,
        )
        self.ctrl_canvas.pack(fill="x", expand=False, padx=10, pady=(0, 12))
        self.ctrl_canvas.bind("<Configure>", self._on_ctrl_canvas_configure)

        self._build_controller_canvas()
        self._update_controller_edit_bar()

    def _on_ctrl_canvas_configure(self, event):
        if event.width <= 10:
            return
        target_cx = max(380, event.width // 2)
        dx = target_cx - self._ctrl_canvas_cx
        if dx != 0:
            self.ctrl_canvas.move("all", dx, 0)
            self._ctrl_canvas_cx = target_cx

    def _get_active_binding_dict(self) -> dict:
        if self._ctrl_editing_layer == "layer":
            return state["controller_layer_bindings"]
        return state["controller_bindings"]

    def _format_compact_binding(self, binding: dict | None) -> tuple[str, str]:
        from features.controller import MOUSE_ACTION_LABELS
        if not binding:
            return "—", "#707885"
        kind = binding.get("kind", "none")
        val = str(binding.get("value", ""))
        if kind == "none" or (kind != "layer_hold" and not val):
            return "—", "#707885"
        if kind == "layer_hold":
            return "Mod Layer", "#ffaa33"
        if kind == "mouse":
            lbl = MOUSE_ACTION_LABELS.get(val, val)
            return lbl, "#44cc88"
        if kind == "macro":
            name = val
            for m in state.get("macros", []):
                if m.get("id") == val or m.get("name") == val:
                    name = m.get("name", val)
                    break
            if len(name) > 11:
                name = name[:10] + "…"
            return f"M:{name}", "#d2a8ff"
        return (val[:12] + "…" if len(val) > 13 else val), "#58a6ff"

    def _build_controller_canvas(self):
        c = self.ctrl_canvas
        c.delete("all")
        self._ctrl_canvas_items.clear()
        self._ctrl_row_widgets.clear()
        self._ctrl_canvas_cx = 380

        # Subtle helper subtitle
        c.create_text(
            380, 12,
            text="Left-Click any controller button or badge to configure   •   Right-Click to unbind",
            fill="#8b949e",
            font=("sans-serif", 9),
        )

        # --- Controller Body Silhouette (Centered around x=380, y=215) ---
        # Shoulder housings
        c.create_oval(230, 82, 330, 140, fill="#252932", outline="#3d4452", width=2)
        c.create_oval(430, 82, 530, 140, fill="#252932", outline="#3d4452", width=2)

        # Left & Right Grips
        c.create_polygon(
            222, 145, 200, 255, 206, 338, 238, 355, 275, 325, 305, 265, 290, 145,
            fill="#252932", outline="#3d4452", width=2, smooth=True
        )
        c.create_polygon(
            538, 145, 560, 255, 554, 338, 522, 355, 485, 325, 455, 265, 470, 145,
            fill="#252932", outline="#3d4452", width=2, smooth=True
        )

        # Main center deck
        c.create_polygon(
            235, 102, 525, 102, 548, 165, 528, 275, 455, 285, 380, 278, 305, 285, 232, 275, 212, 165,
            fill="#282c36", outline="#454d5e", width=2, smooth=True
        )

        # Analog Stick Outer Wells
        c.create_oval(245, 138, 325, 218, fill="#1e222a", outline="#383f4d", width=2)
        c.create_oval(395, 222, 475, 302, fill="#1e222a", outline="#383f4d", width=2)

        # D-Pad Backing Circle
        c.create_oval(288, 224, 362, 298, fill="#1e222a", outline="#383f4d", width=1)

        #Right Stick live position dot (updated in update_gui)
        self._ctrl_rs_dot_origin = (435, 262)
        self._ctrl_rs_dot_id = c.create_oval(
            431, 258, 439, 266, fill="#58a6ff", outline=""
        )

        # --- On-Controller Interactive Shapes ---
        # (code, shape_type, coords, short_label)
        pad_shapes = [
            # Triggers & Bumpers
            ("BTN_L2", "rect", (245, 34, 315, 58), "L2"),
            ("BTN_TL", "rect", (240, 64, 320, 88), "L1"),
            ("BTN_R2", "rect", (445, 34, 515, 58), "R2"),
            ("BTN_TR", "rect", (440, 64, 520, 88), "R1"),
            # Center Buttons
            ("BTN_SELECT", "rect", (326, 128, 356, 146), "SEL"),
            ("BTN_MODE", "oval", (367, 118, 393, 144), "HOME"),
            ("BTN_START", "rect", (404, 128, 434, 146), "STR"),
            # Left Stick (center=285, 178)
            ("BTN_JOY_LY_NEG", "rect", (273, 140, 297, 156), "↑"),
            ("BTN_JOY_LY_POS", "rect", (273, 200, 297, 216), "↓"),
            ("BTN_JOY_LX_NEG", "rect", (247, 166, 263, 190), "←"),
            ("BTN_JOY_LX_POS", "rect", (307, 166, 323, 190), "→"),
            ("BTN_THUMBL", "oval", (267, 160, 303, 196), "L3"),
            # D-Pad (center=325, 261)
            ("BTN_DPAD_UP", "rect", (315, 229, 335, 250), "↑"),
            ("BTN_DPAD_DOWN", "rect", (315, 272, 335, 293), "↓"),
            ("BTN_DPAD_LEFT", "rect", (293, 251, 314, 271), "←"),
            ("BTN_DPAD_RIGHT", "rect", (336, 251, 357, 271), "→"),
            # Face Buttons (center=475, 178)
            ("BTN_NORTH", "oval", (461, 134, 489, 162), "Y"),
            ("BTN_SOUTH", "oval", (461, 194, 489, 222), "A"),
            ("BTN_WEST", "oval", (431, 164, 459, 192), "X"),
            ("BTN_EAST", "oval", (491, 164, 519, 192), "B"),
            # Right Stick (center=435, 262)
            ("BTN_JOY_RY_NEG", "rect", (423, 224, 447, 240), "↑"),
            ("BTN_JOY_RY_POS", "rect", (423, 284, 447, 300), "↓"),
            ("BTN_JOY_RX_NEG", "rect", (397, 250, 413, 274), "←"),
            ("BTN_JOY_RX_POS", "rect", (457, 250, 473, 274), "→"),
            ("BTN_THUMBR", "oval", (417, 244, 453, 280), "R3"),
        ]

        # Callout Badges Layout: (code, badge_x1, badge_y1, badge_x2, badge_y2, short_title)
        badges = [
            # Left Column (x=14..186)
            ("BTN_L2", 14, 28, 186, 54, "L2 / LT"),
            ("BTN_TL", 14, 58, 186, 84, "L1 / LB"),
            ("BTN_JOY_LY_NEG", 14, 98, 186, 124, "LS Up"),
            ("BTN_JOY_LY_POS", 14, 128, 186, 154, "LS Down"),
            ("BTN_JOY_LX_NEG", 14, 158, 186, 184, "LS Left"),
            ("BTN_JOY_LX_POS", 14, 188, 186, 214, "LS Right"),
            ("BTN_THUMBL", 14, 218, 186, 244, "L3 Click"),
            ("BTN_DPAD_UP", 14, 258, 186, 284, "DPAD Up"),
            ("BTN_DPAD_DOWN", 14, 288, 186, 314, "DPAD Down"),
            ("BTN_DPAD_LEFT", 14, 318, 186, 344, "DPAD Left"),
            ("BTN_DPAD_RIGHT", 14, 348, 186, 374, "DPAD Right"),
            # Center Bottom Row (y=392..420)
            ("BTN_SELECT", 196, 392, 314, 420, "Select"),
            ("BTN_MODE", 321, 392, 439, 420, "Guide"),
            ("BTN_START", 446, 392, 564, 420, "Start"),
            # Right Column (x=574..746)
            ("BTN_R2", 574, 28, 746, 54, "R2 / RT"),
            ("BTN_TR", 574, 58, 746, 84, "R1 / RB"),
            ("BTN_NORTH", 574, 98, 746, 124, "Y / North"),
            ("BTN_WEST", 574, 128, 746, 154, "X / West"),
            ("BTN_EAST", 574, 158, 746, 184, "B / East"),
            ("BTN_SOUTH", 574, 188, 746, 214, "A / South"),
            ("BTN_THUMBR", 574, 228, 746, 254, "R3 Click"),
            ("BTN_JOY_RY_NEG", 574, 258, 746, 284, "RS Up"),
            ("BTN_JOY_RY_POS", 574, 288, 746, 314, "RS Down"),
            ("BTN_JOY_RX_NEG", 574, 318, 746, 344, "RS Left"),
            ("BTN_JOY_RX_POS", 574, 348, 746, 374, "RS Right"),
        ]

        # Subtle group connector lines from columns to gamepad
        c.create_line(186, 42, 244, 46, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(186, 71, 239, 76, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(186, 170, 245, 178, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(186, 316, 288, 265, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(574, 42, 516, 46, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(574, 71, 521, 76, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(574, 156, 520, 178, fill="#353b48", width=1, dash=(2, 2))
        c.create_line(574, 300, 475, 265, fill="#353b48", width=1, dash=(2, 2))

        shape_map = {code: (stype, coords, lbl) for code, stype, coords, lbl in pad_shapes}
        bind_map = self._get_active_binding_dict()

        for code, x1, y1, x2, y2, title in badges:
            tag = f"input_{code}"
            stype, scoords, slbl = shape_map[code]
            sx1, sy1, sx2, sy2 = scoords
            scx, scy = (sx1 + sx2) / 2, (sy1 + sy2) / 2

            if stype == "oval":
                pad_id = c.create_oval(
                    sx1, sy1, sx2, sy2,
                    fill="#323846", outline="#566075", width=1, tags=(tag,)
                )
            else:
                pad_id = c.create_rectangle(
                    sx1, sy1, sx2, sy2,
                    fill="#323846", outline="#566075", width=1, tags=(tag,)
                )
            pad_txt_id = c.create_text(
                scx, scy,
                text=slbl,
                fill="#DCE4EE",
                font=("sans-serif", 7, "bold"),
                tags=(tag,)
            )

            badge_id = c.create_rectangle(
                x1, y1, x2, y2,
                fill="#262626", outline="#3a3f4b", width=1, tags=(tag,)
            )
            cy = (y1 + y2) / 2
            dot_id = c.create_oval(
                x1 + 6, cy - 4, x1 + 14, cy + 4,
                fill="#3a3f4b", outline="", tags=(tag,)
            )
            name_id = c.create_text(
                x1 + 20, cy,
                text=title,
                fill="#DCE4EE",
                font=("sans-serif", 8, "bold"),
                anchor="w",
                tags=(tag,)
            )

            binding = bind_map.get(code, {"kind": "none", "value": ""})
            b_text, b_color = self._format_compact_binding(binding)
            val_id = c.create_text(
                x2 - 6, cy,
                text=b_text,
                fill=b_color,
                font=("monospace", 8, "bold"),
                anchor="e",
                tags=(tag,)
            )

            c.tag_bind(tag, "<Button-1>", lambda e, k=code: self.select_controller_input(k))
            c.tag_bind(tag, "<Button-3>", lambda e, k=code: self.clear_controller_binding(k))

            self._ctrl_canvas_items[code] = {
                "pad": pad_id,
                "pad_txt": pad_txt_id,
                "badge": badge_id,
                "dot": dot_id,
                "name": name_id,
                "val": val_id,
            }
            # Maintain compatibility with self._ctrl_row_widgets membership checks
            self._ctrl_row_widgets[code] = self._ctrl_canvas_items[code]

        # Raise the live right-stick dot to the top layer
        c.tag_raise(self._ctrl_rs_dot_id)
        self._refresh_controller_rows_style()

    def _refresh_controller_rows_style(self):
        if not hasattr(self, "ctrl_canvas") or not self._ctrl_canvas_items:
            return
        c = self.ctrl_canvas
        bind_map = self._get_active_binding_dict()
        keys_down = state.get("physical_keys_down", set())

        for code, items in self._ctrl_canvas_items.items():
            is_selected = (self._ctrl_selected_input == code)
            is_down = code in keys_down
            binding = bind_map.get(code, {"kind": "none", "value": ""})
            b_text, b_color = self._format_compact_binding(binding)
            is_bound = binding.get("kind", "none") != "none"

            badge_bg = "#1c324b" if is_selected else ("#1e3a2b" if is_down else "#262626")
            badge_outline = "#58a6ff" if is_selected else ("#44cc88" if is_down else "#3a3f4b")
            badge_width = 2 if (is_selected or is_down) else 1

            pad_fill = (
                "#2ea043" if is_down
                else "#1f6feb" if is_selected
                else "#35435a" if is_bound
                else "#2f3440"
            )
            pad_outline = "#58a6ff" if is_selected else ("#44cc88" if is_down else "#566075")
            dot_fill = "#44cc88" if is_down else (b_color if is_bound else "#484f58")

            c.itemconfigure(items["badge"], fill=badge_bg, outline=badge_outline, width=badge_width)
            c.itemconfigure(items["pad"], fill=pad_fill, outline=pad_outline, width=badge_width)
            c.itemconfigure(items["dot"], fill=dot_fill)
            c.itemconfigure(items["val"], text=b_text, fill=b_color)

    def select_controller_input(self, code: str | None):
        self._ctrl_listening_output = False
        state["listening_for_hotkey"] = None
        self._ctrl_selected_input = code
        self._refresh_controller_rows_style()
        self._update_controller_edit_bar()

    def switch_controller_edit_layer(self, value: str):
        self._ctrl_editing_layer = "layer" if "Modifier" in value else "base"
        self._refresh_controller_rows_style()
        self._update_controller_edit_bar()

    def start_controller_input_detect(self):
        state["captured_controller_input"] = None
        state["listening_for_controller_input"] = True
        self.ctrl_detect_btn.configure(text="Press Any Pad Input...", state="disabled")

    def clear_controller_binding(self, code: str):
        from state import save_config
        bind_map = self._get_active_binding_dict()
        bind_map[code] = {"kind": "none", "value": ""}
        save_config()
        self._refresh_controller_rows_style()
        if self._ctrl_selected_input == code:
            self._update_controller_edit_bar()

    def reset_default_controller_preset(self):
        from state import get_default_controller_bindings, get_default_layer_bindings, save_config
        state["controller_bindings"] = get_default_controller_bindings()
        state["controller_layer_bindings"] = get_default_layer_bindings()
        save_config()
        self._refresh_controller_rows_style()
        self._update_controller_edit_bar()

    def apply_minimal_controller_preset(self):
        from state import get_minimal_controller_bindings, get_default_layer_bindings, save_config
        state["controller_bindings"] = get_minimal_controller_bindings()
        state["controller_layer_bindings"] = {
            k: {"kind": "none", "value": ""} for k in get_default_layer_bindings()
        }
        save_config()
        self._refresh_controller_rows_style()
        self._update_controller_edit_bar()

    def _update_controller_edit_bar(self, override_kind: str | None = None):
        from features.controller import CONTROLLER_INPUT_LABELS, MOUSE_ACTION_LABELS
        for w in self.ctrl_edit_bar.winfo_children():
            w.destroy()

        code = self._ctrl_selected_input
        if not code:
            tk.Label(
                self.ctrl_edit_bar,
                text="Selected Input: None (Click any button on the visual controller below or 'Press Pad Input to Select')",
                fg="#888888",
                bg="#1c2430",
                font=("sans-serif", 11)
            ).pack(pady=10, padx=10)
            return

        bind_map = self._get_active_binding_dict()
        current = bind_map.get(code, {"kind": "none", "value": ""})
        kind = override_kind if override_kind is not None else current.get("kind", "none")
        val = str(current.get("value", ""))
        label = CONTROLLER_INPUT_LABELS.get(code, code)
        layer_tag = "Modifier Layer (Chord)" if self._ctrl_editing_layer == "layer" else "Base Layer"

        top_row = tk.Frame(self.ctrl_edit_bar, bg="#1c2430")
        top_row.pack(fill="x", padx=10, pady=(6, 2))

        tk.Label(
            top_row,
            text=f"Configure: {label} ({code})  —  [{layer_tag}]",
            font=("sans-serif", 11, "bold"),
            fg="#58a6ff",
            bg="#1c2430"
        ).pack(side="left")

        tk.Button(
            top_row,
            text="Done",
            bg="#4d4d4d",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=10,
            pady=2,
            cursor="hand2",
            font=("sans-serif", 10),
            command=lambda: self.select_controller_input(None)
        ).pack(side="right")

        kind_to_tab = {
            "key": "Key / Combo",
            "mouse": "Mouse",
            "layer_hold": "Modifier Layer",
            "macro": "Macro",
            "none": "Unbound",
        }
        tab_to_kind = {v: k for k, v in kind_to_tab.items()}

        allowed_tabs = ["Key / Combo", "Mouse", "Macro", "Unbound"]
        if self._ctrl_editing_layer == "base":
            allowed_tabs.insert(2, "Modifier Layer")
        elif kind == "layer_hold":
            kind = "none"

        ctrl_row = tk.Frame(self.ctrl_edit_bar, bg="#1c2430")
        ctrl_row.pack(fill="x", padx=10, pady=(4, 8))

        type_seg = ctk.CTkSegmentedButton(
            ctrl_row,
            values=allowed_tabs,
            bg_color="#1c2430",
            command=lambda choice: self._update_controller_edit_bar(override_kind=tab_to_kind.get(choice, "none"))
        )
        type_seg.set(kind_to_tab.get(kind, "Unbound"))
        type_seg.pack(side="left", padx=(0, 10))

        if kind == "key":
            self._ctrl_key_entry = ctk.CTkEntry(ctrl_row, width=130, bg_color="#1c2430", placeholder_text="e.g. space, F1, shift+1")
            if current.get("kind") == "key" and val:
                self._ctrl_key_entry.insert(0, val)
            self._ctrl_key_entry.pack(side="left", padx=4)
            self._ctrl_key_entry.bind("<Return>", lambda e: self._save_controller_binding_from_ui("key"))

            self._ctrl_record_key_btn = tk.Button(
                ctrl_row,
                text="Record Key",
                bg="orange",
                fg="black",
                activebackground="#CC8800",
                activeforeground="black",
                relief="flat",
                bd=0,
                padx=10,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=self._start_controller_output_key_record
            )
            self._ctrl_record_key_btn.pack(side="left", padx=4)

            tk.Button(
                ctrl_row,
                text="Apply",
                bg="#238636",
                fg="white",
                activebackground="#2ea043",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=lambda: self._save_controller_binding_from_ui("key")
            ).pack(side="left", padx=4)

        elif kind == "mouse":
            inv_mouse = {v: k for k, v in MOUSE_ACTION_LABELS.items()}
            options = list(MOUSE_ACTION_LABELS.values())
            current_label = MOUSE_ACTION_LABELS.get(val, "Left Click")
            self._ctrl_mouse_menu = ctk.CTkOptionMenu(ctrl_row, values=options, width=140, bg_color="#1c2430")
            self._ctrl_mouse_menu.set(current_label)
            self._ctrl_mouse_menu.pack(side="left", padx=4)

            tk.Button(
                ctrl_row,
                text="Apply",
                bg="#238636",
                fg="white",
                activebackground="#2ea043",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=lambda: self._save_controller_binding_from_ui("mouse", inv_mouse.get(self._ctrl_mouse_menu.get(), "left_click"))
            ).pack(side="left", padx=4)

        elif kind == "layer_hold":
            tk.Label(
                ctrl_row,
                text="Holding this input activates Modifier Layer (Chord) bindings.",
                font=("sans-serif", 10),
                fg="#ffaa33",
                bg="#1c2430"
            ).pack(side="left", padx=6)
            tk.Button(
                ctrl_row,
                text="Apply",
                bg="#238636",
                fg="white",
                activebackground="#2ea043",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=lambda: self._save_controller_binding_from_ui("layer_hold", "modifier_layer")
            ).pack(side="left", padx=4)

        elif kind == "macro":
            macros = state.get("macros", [])
            macro_names = [m["name"] for m in macros] if macros else ["(No Macros Created)"]
            self._ctrl_macro_menu = ctk.CTkOptionMenu(ctrl_row, values=macro_names, width=160, bg_color="#1c2430")
            if val in macro_names:
                self._ctrl_macro_menu.set(val)
            else:
                self._ctrl_macro_menu.set(macro_names[0])
            self._ctrl_macro_menu.pack(side="left", padx=4)

            tk.Button(
                ctrl_row,
                text="Apply",
                bg="#238636",
                fg="white",
                activebackground="#2ea043",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=lambda: self._save_controller_binding_from_ui("macro", self._ctrl_macro_menu.get())
            ).pack(side="left", padx=4)

        else:
            tk.Button(
                ctrl_row,
                text="Confirm Unbind",
                bg="#AA4444",
                fg="white",
                activebackground="#882222",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=14,
                pady=4,
                cursor="hand2",
                font=("sans-serif", 10, "bold"),
                command=lambda: self._save_controller_binding_from_ui("none", "")
            ).pack(side="left", padx=4)

    def _start_controller_output_key_record(self):
        self._ctrl_listening_output = True
        state["captured_hotkey"] = None
        state["listening_for_hotkey"] = "controller_output"
        if hasattr(self, "_ctrl_record_key_btn") and self._ctrl_record_key_btn.winfo_exists():
            self._ctrl_record_key_btn.configure(text="Press Key...", state="disabled")

    def _normalize_controller_key_str(self, raw: str) -> str:
        raw = raw.strip()
        if not raw:
            return ""
        if "+" in raw and len(raw) > 1:
            parts = [p.strip() for p in raw.split("+") if p.strip()]
            norm_parts = []
            for p in parts:
                pl = p.lower()
                if pl in ("ctrl", "shift", "alt"):
                    norm_parts.append(pl)
                elif pl in _SPECIAL_XDOTOOL:
                    norm_parts.append(_SPECIAL_XDOTOOL[pl])
                else:
                    norm_parts.append(pl)
            return " + ".join(norm_parts)
        low = raw.lower()
        if low in _SPECIAL_XDOTOOL:
            return _SPECIAL_XDOTOOL[low]
        return raw

    def _save_controller_binding_from_ui(self, kind: str, explicit_val: str | None = None):
        from state import save_config
        code = self._ctrl_selected_input
        if not code:
            return
        bind_map = self._get_active_binding_dict()
        if kind == "key":
            raw = self._ctrl_key_entry.get().strip() if hasattr(self, "_ctrl_key_entry") else ""
            norm = self._normalize_controller_key_str(raw)
            if not norm:
                if hasattr(self, "_ctrl_key_entry"):
                    self._ctrl_key_entry.configure(border_color="red")
                return
            bind_map[code] = {"kind": "key", "value": norm}
        elif kind == "macro":
            if not explicit_val or explicit_val == "(No Macros Created)":
                return
            bind_map[code] = {"kind": "macro", "value": explicit_val}
        elif kind == "none":
            bind_map[code] = {"kind": "none", "value": ""}
        else:
            bind_map[code] = {"kind": kind, "value": explicit_val or ""}

        save_config()
        self._refresh_controller_rows_style()
        self._update_controller_edit_bar()

    def _setup_macro_frame(self):
        self.macro_frame.grid_columnconfigure(0, weight=1)
        self.macro_frame.grid_rowconfigure(1, weight=1)

        self.macro_top_frame = tk.Frame(self.macro_frame, bg="#242424")
        self.macro_top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        self.macro_title = tk.Label(self.macro_top_frame, text="Macro Management", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.macro_title.pack(side="left")
        
        self.new_macro_button = tk.Button(
            self.macro_top_frame,
            text="+ New Macro",
            bg="#1f6feb",
            fg="white",
            activebackground="#1856b8",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            font=("sans-serif", 10, "bold"),
            command=self.open_editor
        )
        self.new_macro_button.pack(side="right")

        self.macro_list_frame = ctk.CTkScrollableFrame(self.macro_frame, label_text="Your Macros")
        self.macro_list_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        enable_linux_scroll(self.macro_list_frame)
        
        self.refresh_macro_list()

    def refresh_macro_list(self):
        for widget in self.macro_list_frame.winfo_children():
            widget.destroy()
        self._macro_card_widgets.clear()

        macros_only = [m for m in state["macros"] if m.get("kind", "macro") == "macro"]
        binds_only = [m for m in state["macros"] if m.get("kind") == "keybind"]

        def render_section(title, items, color):
            if not items:
                return

            header = tk.Frame(self.macro_list_frame, bg="#1d1e1e")
            header.pack(fill="x", pady=(15, 5))
            tk.Label(
                header,
                text=title,
                font=("sans-serif", 11, "bold"),
                fg=color,
                bg="#1d1e1e"
            ).pack(side="left", padx=10)
            tk.Frame(header, height=2, bg=color).pack(side="left", fill="x", expand=True, padx=10)

            for macro in items:
                card_bg = "#2B2B2B"
                item_frame = tk.Frame(self.macro_list_frame, bg=card_bg, bd=0, highlightthickness=0)
                item_frame.pack(fill="x", pady=3, padx=5)

                name_label = tk.Label(
                    item_frame,
                    text=macro["name"],
                    font=("sans-serif", 10, "bold"),
                    fg="#DCE4EE",
                    bg=card_bg
                )
                name_label.pack(side="left", padx=10, pady=8)

                trigger_label = tk.Label(
                    item_frame,
                    text=macro["trigger"].replace("KEY_", ""),
                    fg="orange",
                    bg=card_bg,
                    font=("sans-serif", 10, "bold")
                )
                trigger_label.pack(side="left", padx=10, pady=8)

                steps_label = tk.Label(
                    item_frame,
                    text=f"{len(macro['steps'])} steps",
                    fg="#888888",
                    bg=card_bg,
                    font=("sans-serif", 9)
                )
                steps_label.pack(side="left", padx=10, pady=8)

                btn_frame = tk.Frame(item_frame, bg=card_bg)
                btn_frame.pack(side="right", padx=10, pady=6)

                edit_btn = tk.Button(
                    btn_frame,
                    text="Edit",
                    font=("sans-serif", 9, "bold"),
                    fg="white",
                    bg="#4444AA",
                    activeforeground="white",
                    activebackground="#333388",
                    relief="flat",
                    bd=0,
                    padx=10,
                    pady=3,
                    cursor="hand2",
                    command=lambda m=macro: self.edit_macro(m)
                )
                edit_btn.pack(side="left", padx=4)

                delete_btn = tk.Button(
                    btn_frame,
                    text="×",
                    font=("sans-serif", 11, "bold"),
                    fg="white",
                    bg="#AA4444",
                    activeforeground="white",
                    activebackground="#882222",
                    relief="flat",
                    bd=0,
                    padx=7,
                    pady=2,
                    cursor="hand2",
                    command=lambda m=macro: self.delete_macro(m)
                )
                delete_btn.pack(side="left", padx=2)

                enabled_switch = ctk.CTkSwitch(
                    item_frame,
                    text="",
                    width=40,
                    bg_color=card_bg,
                    command=lambda m=macro: self.toggle_macro(m)
                )
                if macro.get("enabled", True):
                    enabled_switch.select()
                enabled_switch.pack(side="right", padx=10)

                self._macro_card_widgets[macro["id"]] = {
                    "frame": item_frame,
                    "name": name_label,
                    "trigger": trigger_label,
                    "steps": steps_label,
                    "switch": enabled_switch,
                    "kind": macro.get("kind", "macro"),
                }

        render_section("MACROS", macros_only, "#b3b3b3")
        render_section("KEYBINDS", binds_only, "#00ffff")

    def toggle_macro(self, macro):
        macro["enabled"] = not macro.get("enabled", True)
        save_macros()

    def open_editor(self):
        if self._macro_editor is None or not self._macro_editor.winfo_exists():
            self._macro_editor = MacroEditor(self, self.save_new_macro, macro_to_edit=None)
        else:
            self._macro_editor.load_macro_data(self.save_new_macro, macro_to_edit=None)
            self._macro_editor.deiconify()
            self._macro_editor.lift()
        self._macro_editor.grab_set()

    def edit_macro(self, macro):
        if self._macro_editor is None or not self._macro_editor.winfo_exists():
            self._macro_editor = MacroEditor(self, self.save_edited_macro, macro_to_edit=macro)
        else:
            self._macro_editor.load_macro_data(self.save_edited_macro, macro_to_edit=macro)
            self._macro_editor.deiconify()
            self._macro_editor.lift()
        self._macro_editor.grab_set()

    def save_new_macro(self, macro):
        state["macros"].append(macro)
        save_macros()
        self.schedule_refresh()

    def delete_macro(self, macro):
        if macro in state["macros"]:
            macro_id = macro.get("id")
            macro_kind = macro.get("kind", "macro")
            state["macros"].remove(macro)
            save_macros()
            remaining_in_kind = any(m.get("kind", "macro") == macro_kind for m in state["macros"])
            card = self._macro_card_widgets.pop(macro_id, None)
            if card and remaining_in_kind and card["frame"].winfo_exists():
                card["frame"].destroy()
            else:
                self.schedule_refresh()

    def save_edited_macro(self, macro):
        old_kind = None
        for m in state["macros"]:
            if m["id"] == macro["id"]:
                old_kind = m.get("kind", "macro")
                m.clear()
                m.update(macro)
                break
        save_macros()
        new_kind = macro.get("kind", "macro")
        card = self._macro_card_widgets.get(macro["id"])
        if card and old_kind == new_kind and card["frame"].winfo_exists():
            card["name"].configure(text=macro["name"])
            card["trigger"].configure(text=macro["trigger"].replace("KEY_", ""))
            card["steps"].configure(text=f"{len(macro['steps'])} steps")
            sw_val = bool(card["switch"].get())
            if macro.get("enabled", True) != sw_val:
                if macro.get("enabled", True):
                    card["switch"].select()
                else:
                    card["switch"].deselect()
        else:
            self.schedule_refresh()

    def schedule_refresh(self):
        # Debounce refresh calls to prevent layout thrashing
        if hasattr(self, "_refresh_timer") and self._refresh_timer:
            self.after_cancel(self._refresh_timer)
        self._refresh_timer = self.after(100, self.refresh_macro_list)

    def _setup_autofollowing_frame(self):
        self.af_title = tk.Label(self.autofollowing_frame, text="Autofollowing", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.af_title.pack(padx=20, pady=(20, 15))

        notice_box = tk.Frame(self.autofollowing_frame, bg="#2b2b2b")
        notice_box.pack(padx=20, pady=10, fill="x")

        message = (
            "Autofollowing Features will not be added to DALT. "
            "Please use an alternative program to control autofollowing. "
            "The only reason this tab exists is solely so I don't get messages asking for this feature. "
            "DALT is not meant to be used on inactive windows, which is why you must hold your hotkey to loop a macro and why DALT only works on active windows, and why Autofollowing will not be implemented."
        )
        self.af_text = tk.Label(
            notice_box,
            text=message,
            font=("sans-serif", 11),
            fg="#DCE4EE",
            bg="#2b2b2b",
            wraplength=600,
            justify="center"
        )
        self.af_text.pack(padx=20, pady=25)

    def _setup_credits_frame(self):
        self.credits_title = tk.Label(self.credits_frame, text="DALT is brought to you by the following Aislings", font=("sans-serif", 18, "bold"), fg="#DCE4EE", bg="#242424")
        self.credits_title.pack(padx=20, pady=(20, 15))

        notice_box = tk.Frame(self.credits_frame, bg="#2b2b2b")
        notice_box.pack(padx=20, pady=10, fill="x")

        self.credits_text = tk.Label(
            notice_box,
            text="""Initial Coding and Setup, Initial Macro and Butterwalk implementation: Phever - https://github.com/phever

GUI Implementation and Troubleshooting: Aon - https://github.com/FreyaNile

Feature implementation, Optimization, and Polishing: Iglis - https://github.com/IglisViriou""",
            font=("sans-serif", 11),
            fg="#DCE4EE",
            bg="#2b2b2b",
            wraplength=600,
            justify="center"
        )
        self.credits_text.pack(padx=20, pady=25)

    def select_frame_by_name(self, name):
        self._ensure_frame_setup(name)
        self.home_button.configure(bg="#3d3d3d" if name == "home" else "#2b2b2b")
        self.butterwalk_button.configure(bg="#3d3d3d" if name == "butterwalk" else "#2b2b2b")
        self.spacebar_button.configure(bg="#3d3d3d" if name == "spacebar" else "#2b2b2b")
        self.controller_button.configure(bg="#3d3d3d" if name == "controller" else "#2b2b2b")
        self.macro_button.configure(bg="#3d3d3d" if name == "macros" else "#2b2b2b")
        self.autofollow_button.configure(bg="#3d3d3d" if name == "autofollowing" else "#2b2b2b")
        self.credits_button.configure(bg="#3d3d3d" if name == "credits" else "#2b2b2b")

        if name == "home": self.home_frame.grid(row=0, column=1, sticky="nsew")
        else: self.home_frame.grid_forget()
        
        if name == "butterwalk": self.butterwalk_frame.grid(row=0, column=1, sticky="nsew")
        else: self.butterwalk_frame.grid_forget()

        if name == "spacebar": self.spacebar_frame.grid(row=0, column=1, sticky="nsew")
        else: self.spacebar_frame.grid_forget()

        if name == "controller": self.controller_frame.grid(row=0, column=1, sticky="nsew")
        else: self.controller_frame.grid_forget()
        
        if name == "macros": self.macro_frame.grid(row=0, column=1, sticky="nsew")
        else: self.macro_frame.grid_forget()

        if name == "autofollowing": self.autofollowing_frame.grid(row=0, column=1, sticky="nsew")
        else: self.autofollowing_frame.grid_forget()

        if name == "credits": self.credits_frame.grid(row=0, column=1, sticky="nsew")
        else: self.credits_frame.grid_forget()

    def home_button_event(self): self.select_frame_by_name("home")
    def butterwalk_button_event(self): self.select_frame_by_name("butterwalk")
    def spacebar_button_event(self): self.select_frame_by_name("spacebar")
    def controller_button_event(self): self.select_frame_by_name("controller")
    def macro_button_event(self): self.select_frame_by_name("macros")
    def autofollow_button_event(self): self.select_frame_by_name("autofollowing")
    def credits_button_event(self): self.select_frame_by_name("credits")

    def toggle_bw(self): state["butterwalk"] = self.bw_switch.get() == 1
    def toggle_zxcv(self): 
        from state import save_config
        state["zxcv_enabled"] = self.zxcv_switch.get() == 1
        save_config()

    def toggle_controller(self): 
        from state import save_config
        state["controller_enabled"] = self.controller_switch.get() == 1
        save_config()

    def toggle_dpad(self): 
        from state import save_config
        state["dpad_enabled"] = self.dpad_switch.get() == 1
        save_config()

    def toggle_joystick(self): 
        from state import save_config
        state["joystick_enabled"] = self.joystick_switch.get() == 1
        save_config()

    def toggle_mouse_control(self): 
        from state import save_config
        state["right_stick_mouse_enabled"] = self.mouse_control_switch.get() == 1
        save_config()

    def set_mouse_sensitivity(self, value):
        from state import save_config
        state["mouse_sensitivity"] = int(value)
        self.mouse_sens_label.configure(
            text=f"Right Stick Sensitivity: {state['mouse_sensitivity']}% of {state['mouse_dpi']} DPI"
        )
        save_config()

    def set_left_deadzone(self, value):
        from state import save_config
        val = int(round(value))
        if state["left_stick_deadzone"] != val:
            state["left_stick_deadzone"] = val
            self.ls_dz_label.configure(text=f"Left Stick Deadzone: {val}%")
            save_config()

    def set_right_deadzone(self, value):
        from state import save_config
        val = int(round(value))
        if state["right_stick_deadzone"] != val:
            state["right_stick_deadzone"] = val
            self.rs_dz_label.configure(text=f"Right Stick Deadzone: {val}%")
            save_config()

    def set_mouse_dpi(self):
        from state import save_config
        try:
            val = int(self.mouse_dpi_entry.get().strip())
            if val > 0:
                state["mouse_dpi"] = val
                self.mouse_sens_label.configure(
                    text=f"Right Stick Sensitivity: {state['mouse_sensitivity']}% of {state['mouse_dpi']} DPI"
                )
                save_config()
        except ValueError:
            self.mouse_dpi_entry.delete(0, 'end')
            self.mouse_dpi_entry.insert(0, str(state["mouse_dpi"]))

    def toggle_space(self): 
        from state import save_config
        state["space_enabled"] = self.space_switch.get() == 1
        save_config()

    def set_multiplier(self, value): 
        from state import save_config
        val = int(round(value))
        if state["multiplier"] != val:
            state["multiplier"] = val
            self.multiplier_label.configure(text=f"Multiplier: {state['multiplier']}x")
            save_config()

    def set_space_multiplier(self, value):
        from state import save_config
        val = int(round(value))
        if state["space_multiplier"] != val:
            state["space_multiplier"] = val
            self.space_multiplier_label.configure(text=f"Repeat Multiplier: {state['space_multiplier']}x")
            save_config()

    def set_butterwalk_delay(self, value):
        from state import save_config
        val = int(round(value))
        if state["butterwalk_delay_ms"] != val:
            state["butterwalk_delay_ms"] = val
            self.bw_speed_label.configure(text=f"Repeat Speed: {state['butterwalk_delay_ms']} ms")
            save_config()

    def set_space_delay(self, value):
        from state import save_config
        val = int(round(value))
        if state["space_delay_ms"] != val:
            state["space_delay_ms"] = val
            self.space_speed_label.configure(text=f"Repeat Speed: {state['space_delay_ms']} ms")
            save_config()

    def start_hotkey_binding(self, target: str):
        state["listening_for_hotkey"] = target
        state["captured_hotkey"] = None
        if target == "butterwalk":
            self.bw_hotkey_bind_btn.configure(text="Press Keys...", state="disabled")
        elif target == "controller":
            self.ctrl_hotkey_bind_btn.configure(text="Press Keys...", state="disabled")
        elif target == "space":
            self.space_hotkey_bind_btn.configure(text="Press Keys...", state="disabled")

    def apply_bw_hotkey(self):
        from features.hotkeys import normalize_hotkey_str
        from state import save_config
        val = normalize_hotkey_str(self.bw_hotkey_entry.get().strip())
        if val:
            state["butterwalk_hotkey"] = val
            self.bw_hotkey_entry.delete(0, 'end')
            self.bw_hotkey_entry.insert(0, val)
            save_config()

    def apply_ctrl_hotkey(self):
        from features.hotkeys import normalize_hotkey_str
        from state import save_config
        val = normalize_hotkey_str(self.ctrl_hotkey_entry.get().strip())
        if val:
            state["controller_hotkey"] = val
            self.ctrl_hotkey_entry.delete(0, 'end')
            self.ctrl_hotkey_entry.insert(0, val)
            save_config()

    def apply_space_hotkey(self):
        from features.hotkeys import normalize_hotkey_str
        from state import save_config
        val = normalize_hotkey_str(self.space_hotkey_entry.get().strip())
        if val:
            state["space_hotkey"] = val
            self.space_hotkey_entry.delete(0, 'end')
            self.space_hotkey_entry.insert(0, val)
            save_config()

    def _cache_changed(self, key: str, value) -> bool:
        if self._gui_cache.get(key) != value:
            self._gui_cache[key] = value
            return True
        return False

    def update_gui(self):
        # Update Footer Status & Device Counts
        active_val = bool(state["active"])
        if self._cache_changed("footer_active", active_val):
            status_text = "● ACTIVE" if active_val else "○ Inactive"
            status_color = "#44AA44" if active_val else "#888888"
            self.footer_status.configure(text=status_text, fg=status_color)

        import input_hub
        kb, mice = input_hub.get_device_counts()
        pads = input_hub.get_controller_count()
        if self._cache_changed("footer_devices", (kb, mice, pads)):
            self.footer_devices.configure(text=f"Devices: {kb} KB, {mice} Mice, {pads} Pad")

        # Check for captured hotkeys
        if state.get("captured_hotkey"):
            target, combo = state["captured_hotkey"]
            state["captured_hotkey"] = None
            if target == "butterwalk":
                state["butterwalk_hotkey"] = combo
                if "butterwalk" in self._initialized_frames:
                    self.bw_hotkey_entry.delete(0, 'end')
                    self.bw_hotkey_entry.insert(0, combo)
                    self.bw_hotkey_bind_btn.configure(text="Record", state="normal")
            elif target == "controller":
                state["controller_hotkey"] = combo
                if "controller" in self._initialized_frames:
                    self.ctrl_hotkey_entry.delete(0, 'end')
                    self.ctrl_hotkey_entry.insert(0, combo)
                    self.ctrl_hotkey_bind_btn.configure(text="Record", state="normal")
            elif target == "space":
                state["space_hotkey"] = combo
                if "spacebar" in self._initialized_frames:
                    self.space_hotkey_entry.delete(0, 'end')
                    self.space_hotkey_entry.insert(0, combo)
                    self.space_hotkey_bind_btn.configure(text="Record", state="normal")
            elif target == "controller_output":
                self._ctrl_listening_output = False
                if "controller" in self._initialized_frames and hasattr(self, "_ctrl_key_entry") and self._ctrl_key_entry.winfo_exists():
                    norm_out = self._normalize_controller_key_str(combo)
                    self._ctrl_key_entry.delete(0, "end")
                    self._ctrl_key_entry.insert(0, norm_out)
                    if hasattr(self, "_ctrl_record_key_btn") and self._ctrl_record_key_btn.winfo_exists():
                        self._ctrl_record_key_btn.configure(text="Record Key", state="normal")
                    self._save_controller_binding_from_ui("key")
            from state import save_config
            save_config()

        # Check for captured gamepad input selection
        if state.get("captured_controller_input"):
            cap_input = state["captured_controller_input"]
            state["captured_controller_input"] = None
            if "controller" in self._initialized_frames:
                self.ctrl_detect_btn.configure(text="Press Pad Input to Select", state="normal")
                if cap_input in self._ctrl_row_widgets:
                    self.select_controller_input(cap_input)

        keys_down = state["physical_keys_down"]
        keys_str = ", ".join(k.replace("KEY_", "") for k in keys_down) or "—"

        # Sync switches and controls for initialized tabs
        if "butterwalk" in self._initialized_frames:
            if state["butterwalk"] and self.bw_switch.get() == 0: self.bw_switch.select()
            elif not state["butterwalk"] and self.bw_switch.get() == 1: self.bw_switch.deselect()
            
            if state["zxcv_enabled"] and self.zxcv_switch.get() == 0: self.zxcv_switch.select()
            elif not state["zxcv_enabled"] and self.zxcv_switch.get() == 1: self.zxcv_switch.deselect()

            if self._cache_changed("bw_mult", state["multiplier"]):
                self.multiplier_label.configure(text=f"Multiplier: {state['multiplier']}x")
            if not getattr(self, "_bw_slider_dragging", False) and int(round(self.multiplier_slider.get())) != state["multiplier"]:
                self.multiplier_slider.set(state["multiplier"])

            if self._cache_changed("bw_delay", state["butterwalk_delay_ms"]):
                self.bw_speed_label.configure(text=f"Repeat Speed: {state['butterwalk_delay_ms']} ms")
            if not getattr(self, "_bw_speed_slider_dragging", False) and int(round(self.bw_speed_slider.get())) != state["butterwalk_delay_ms"]:
                self.bw_speed_slider.set(state["butterwalk_delay_ms"])

            if self._cache_changed("bw_keys", keys_str):
                self.input_display_label.configure(text=f"Keys Pressed: {keys_str}")

        if "spacebar" in self._initialized_frames:
            if state["space_enabled"] and self.space_switch.get() == 0: self.space_switch.select()
            elif not state["space_enabled"] and self.space_switch.get() == 1: self.space_switch.deselect()

            if self._cache_changed("space_mult", state["space_multiplier"]):
                self.space_multiplier_label.configure(text=f"Repeat Multiplier: {state['space_multiplier']}x")
            if not getattr(self, "_space_slider_dragging", False) and int(round(self.space_multiplier_slider.get())) != state["space_multiplier"]:
                self.space_multiplier_slider.set(state["space_multiplier"])

            if self._cache_changed("space_delay", state["space_delay_ms"]):
                self.space_speed_label.configure(text=f"Repeat Speed: {state['space_delay_ms']} ms")
            if not getattr(self, "_space_speed_slider_dragging", False) and int(round(self.space_speed_slider.get())) != state["space_delay_ms"]:
                self.space_speed_slider.set(state["space_delay_ms"])

            if self._cache_changed("space_keys", keys_str):
                self.space_input_display_label.configure(text=f"Keys Pressed: {keys_str}")

        if "controller" in self._initialized_frames:
            pad_names = tuple(input_hub.get_controller_names())
            if self._cache_changed("ctrl_pads", pad_names):
                if pad_names:
                    self.ctrl_device_banner.configure(
                        text=f"Connected Controller(s) ({len(pad_names)}): {', '.join(pad_names)}",
                        fg="#44cc88"
                    )
                else:
                    self.ctrl_device_banner.configure(
                        text="Connected Controllers: None Detected (Auto-Hotplug Active)",
                        fg="#888888"
                    )

            if state["controller_enabled"] and self.controller_switch.get() == 0: self.controller_switch.select()
            elif not state["controller_enabled"] and self.controller_switch.get() == 1: self.controller_switch.deselect()

            if state["dpad_enabled"] and self.dpad_switch.get() == 0: self.dpad_switch.select()
            elif not state["dpad_enabled"] and self.dpad_switch.get() == 1: self.dpad_switch.deselect()

            if state["joystick_enabled"] and self.joystick_switch.get() == 0: self.joystick_switch.select()
            elif not state["joystick_enabled"] and self.joystick_switch.get() == 1: self.joystick_switch.deselect()

            if state["right_stick_mouse_enabled"] and self.mouse_control_switch.get() == 0: self.mouse_control_switch.select()
            elif not state["right_stick_mouse_enabled"] and self.mouse_control_switch.get() == 1: self.mouse_control_switch.deselect()

            if self._cache_changed("ctrl_sens", (state["mouse_sensitivity"], state["mouse_dpi"])):
                self.mouse_sens_label.configure(text=f"Right Stick Sensitivity: {state['mouse_sensitivity']}% of {state['mouse_dpi']} DPI")
            if not getattr(self, "_sens_slider_dragging", False) and int(round(self.mouse_sens_slider.get())) != state["mouse_sensitivity"]:
                self.mouse_sens_slider.set(state["mouse_sensitivity"])

            if self._cache_changed("ctrl_ls_dz", state["left_stick_deadzone"]):
                self.ls_dz_label.configure(text=f"Left Stick Deadzone: {state['left_stick_deadzone']}%")
            if not getattr(self, "_ls_dz_dragging", False) and int(round(self.ls_dz_slider.get())) != state["left_stick_deadzone"]:
                self.ls_dz_slider.set(state["left_stick_deadzone"])

            if self._cache_changed("ctrl_rs_dz", state["right_stick_deadzone"]):
                self.rs_dz_label.configure(text=f"Right Stick Deadzone: {state['right_stick_deadzone']}%")
            if not getattr(self, "_rs_dz_dragging", False) and int(round(self.rs_dz_slider.get())) != state["right_stick_deadzone"]:
                self.rs_dz_slider.set(state["right_stick_deadzone"])

            rx, ry = state.get("right_stick_x", 0.0), state.get("right_stick_y", 0.0)
            stick_info = f" | RS: ({rx:+.2f}, {ry:+.2f})" if (rx != 0.0 or ry != 0.0) else ""
            from features.controller import is_layer_active
            layer_status = " | [MODIFIER LAYER ACTIVE]" if is_layer_active() else ""
            ctrl_disp_text = f"Keys / Axes Pressed: {keys_str}{stick_info}{layer_status}"
            if self._cache_changed("ctrl_disp", ctrl_disp_text):
                self.ctrl_input_display_label.configure(text=ctrl_disp_text)

            # Update live active indicators on the visual controller canvas only when state changes
            any_btn_changed = False
            for code in self._ctrl_canvas_items:
                is_down = code in keys_down
                if self._cache_changed(f"ctrl_dot_{code}", is_down):
                    any_btn_changed = True
            if any_btn_changed:
                self._refresh_controller_rows_style()

            if hasattr(self, "_ctrl_rs_dot_id") and self._cache_changed("ctrl_rs_pos", (round(rx, 2), round(ry, 2), self._ctrl_canvas_cx)):
                rs_cx = self._ctrl_canvas_cx + 55 + (rx * 28.0)
                rs_cy = 262 + (ry * 28.0)
                self.ctrl_canvas.coords(self._ctrl_rs_dot_id, rs_cx - 4, rs_cy - 4, rs_cx + 4, rs_cy + 4)
        
        # Update Footer Monitoring
        if self._cache_changed("footer_last_event", state["last_event"]):
            self.footer_last_event.configure(text=f"Last Event: {state['last_event']}")

        if state["running"]:
            self.after(200, self.update_gui)

def run_gui(macro_feature, loop):
    app = DarkAgesApp(macro_feature, loop)
    def on_closing():
        try:
            app.withdraw()
            app.update_idletasks()
        except Exception:
            pass
        state["running"] = False
        app.destroy()
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
