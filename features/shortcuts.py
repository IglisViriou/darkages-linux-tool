from __future__ import annotations
import os
import json
import uuid
import subprocess
import tempfile
from typing import TypedDict

SHORTCUTS_DIR = os.path.expanduser("~/.config/darkages-linux-tool")
SHORTCUTS_CONFIG_PATH = os.path.join(SHORTCUTS_DIR, "shortcuts.json")
ICONS_CACHE_DIR = os.path.join(SHORTCUTS_DIR, "icons")


class Shortcut(TypedDict):
    id: str
    name: str
    target_path: str
    custom_icon_path: str | None
    icon_cache_path: str


def load_shortcuts() -> list[Shortcut]:
    """Load shortcuts from shortcuts.json config file."""
    try:
        with open(SHORTCUTS_CONFIG_PATH) as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def save_shortcuts(shortcuts: list[Shortcut]) -> None:
    """Save shortcuts to shortcuts.json config file."""
    try:
        os.makedirs(SHORTCUTS_DIR, exist_ok=True)
        with open(SHORTCUTS_CONFIG_PATH, "w") as f:
            json.dump(shortcuts, f, indent=2)
    except Exception as e:
        pass


def _convert_image_to_png(src: str, dest_png: str, size: str = "48x48") -> bool:
    """Convert and resize an image file to a PNG using ImageMagick convert or icotool."""
    if not os.path.exists(src):
        return False
    # Try ImageMagick convert with frame [0] first
    try:
        res = subprocess.run(
            ["convert", f"{src}[0]", "-resize", size, dest_png],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if res.returncode == 0 and os.path.exists(dest_png) and os.path.getsize(dest_png) > 0:
            return True
    except Exception:
        pass

    # Try ImageMagick convert without frame specifier
    try:
        res = subprocess.run(
            ["convert", src, "-resize", size, dest_png],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if res.returncode == 0 and os.path.exists(dest_png) and os.path.getsize(dest_png) > 0:
            return True
    except Exception:
        pass

    # If ICO file, try icotool fallback
    if src.lower().endswith(".ico"):
        try:
            res = subprocess.run(
                ["icotool", "-x", src, "-o", dest_png],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if res.returncode == 0 and os.path.exists(dest_png) and os.path.getsize(dest_png) > 0:
                return True
        except Exception:
            pass

    return False


def resolve_icon(
    target_path: str | None,
    custom_icon_path: str | None,
    dest_png: str,
    project_root: str = "."
) -> tuple[bool, str]:
    """
    Resolve and generate a cached 48x48 PNG icon.
    Priority:
    1. Custom icon path if provided and exists.
    2. Selected application's icon (extracted from .exe via wrestool, parsed from .desktop,
       neighboring icon files, or direct image file).
    3. Project default icon (icon.png).

    Returns (success, source_description).
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest_png)), exist_ok=True)

    # 1. Custom icon provided by user
    if custom_icon_path:
        expanded_custom = os.path.expanduser(custom_icon_path.strip())
        if os.path.exists(expanded_custom):
            if _convert_image_to_png(expanded_custom, dest_png):
                return True, "custom"

    # 2. Selected application icon fallback
    if target_path:
        expanded_target = os.path.expanduser(target_path.strip())
        if os.path.exists(expanded_target):
            # 2a. Windows PE Executable / DLL (extract icon using wrestool)
            if expanded_target.lower().endswith((".exe", ".dll")):
                with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as tf:
                    ico_tmp = tf.name
                try:
                    res = subprocess.run(
                        ["wrestool", "-x", "-t", "14", expanded_target, "-o", ico_tmp],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    if res.returncode == 0 and os.path.exists(ico_tmp) and os.path.getsize(ico_tmp) > 0:
                        if _convert_image_to_png(ico_tmp, dest_png):
                            return True, "application_extracted"
                except Exception:
                    pass
                finally:
                    if os.path.exists(ico_tmp):
                        try:
                            os.remove(ico_tmp)
                        except OSError:
                            pass

            # 2b. Linux .desktop file
            if expanded_target.endswith(".desktop"):
                try:
                    with open(expanded_target, "r", errors="ignore") as f:
                        for line in f:
                            if line.startswith("Icon="):
                                icon_val = line.strip().split("=", 1)[1].strip()
                                if os.path.isabs(icon_val) and os.path.exists(icon_val):
                                    if _convert_image_to_png(icon_val, dest_png):
                                        return True, "application_extracted"
                                # Search system icon directories
                                search_dirs = [
                                    "/usr/share/pixmaps",
                                    "/usr/share/icons/hicolor/48x48/apps",
                                    "/usr/share/icons/hicolor/scalable/apps",
                                    os.path.expanduser("~/.local/share/icons"),
                                ]
                                for d in search_dirs:
                                    for ext in ["", ".png", ".svg", ".ico", ".xpm"]:
                                        cand = os.path.join(d, f"{icon_val}{ext}")
                                        if os.path.exists(cand):
                                            if _convert_image_to_png(cand, dest_png):
                                                return True, "application_extracted"
                except Exception:
                    pass

            # 2c. Neighboring icon files in application directory
            app_dir = os.path.dirname(expanded_target)
            base_name = os.path.splitext(os.path.basename(expanded_target))[0]
            candidates = [
                f"{base_name}.ico",
                f"{base_name}.png",
                f"{base_name}.jpg",
                "icon.png",
                "icon.ico",
                "app.ico",
                "app.png",
                "Chaos Launcher.ico",
                "Chaos Launcher.png",
            ]
            for cand_name in candidates:
                cand = os.path.join(app_dir, cand_name)
                if os.path.exists(cand):
                    if _convert_image_to_png(cand, dest_png):
                        return True, "application_extracted"

            # 2d. Direct image file if user pointed to an image
            if expanded_target.lower().endswith((".png", ".ico", ".jpg", ".jpeg", ".bmp", ".svg")):
                if _convert_image_to_png(expanded_target, dest_png):
                    return True, "application_extracted"

    # 3. Final fallback: default DALT icon
    for fallback_cand in [
        os.path.join(project_root, "icon.png"),
        os.path.join(project_root, "assets", "icon.png"),
        os.path.expanduser("~/.config/darkages-linux-tool/icon.png"),
    ]:
        if os.path.exists(fallback_cand):
            if _convert_image_to_png(fallback_cand, dest_png):
                return True, "fallback_default"

    return False, "none"


def launch_shortcut(shortcut: Shortcut) -> tuple[bool, str]:
    """
    Launch the shortcut target asynchronously and non-blockingly.
    Returns (success, message).
    """
    target_path = os.path.expanduser(shortcut["target_path"].strip())
    if not os.path.exists(target_path):
        return False, f"File does not exist: {target_path}"

    cwd = os.path.dirname(target_path) or None
    try:
        # .desktop file
        if target_path.endswith(".desktop"):
            subprocess.Popen(["gio", "launch", target_path], cwd=cwd, start_new_session=True)
            return True, f"Launched {shortcut['name']}"

        # Shell script
        if target_path.endswith(".sh"):
            if not os.access(target_path, os.X_OK):
                subprocess.Popen(["/bin/sh", target_path], cwd=cwd, start_new_session=True)
            else:
                subprocess.Popen([target_path], cwd=cwd, start_new_session=True)
            return True, f"Launched {shortcut['name']}"

        # Linux executable binary
        if os.access(target_path, os.X_OK) and not target_path.lower().endswith((".exe", ".lnk", ".bat", ".cmd")):
            subprocess.Popen([target_path], cwd=cwd, start_new_session=True)
            return True, f"Launched {shortcut['name']}"

        # Windows .exe or other target: try direct execution, then xdg-open fallback
        try:
            subprocess.Popen([target_path], cwd=cwd, start_new_session=True)
            return True, f"Launched {shortcut['name']}"
        except (PermissionError, OSError):
            subprocess.Popen(["xdg-open", target_path], cwd=cwd, start_new_session=True)
            return True, f"Launched {shortcut['name']}"

    except Exception as e:
        return False, f"Launch error: {str(e)}"
