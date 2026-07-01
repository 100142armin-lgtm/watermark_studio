from __future__ import annotations

import ctypes
import json
import os
import queue
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from tkinter import (
    BooleanVar,
    Button,
    Canvas,
    Checkbutton,
    DoubleVar,
    END,
    Entry,
    Frame,
    IntVar,
    Label,
    Listbox,
    StringVar,
    Tk,
    colorchooser,
    filedialog,
    messagebox,
)
from tkinter import ttk

from PIL import Image, ImageTk
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = ""
    TKDND_AVAILABLE = False
    TkBase = Tk
else:
    TKDND_AVAILABLE = True
    TkBase = TkinterDnD.Tk

from watermark_engine import (
    IMAGE_EXTENSIONS,
    POSITION_LABELS,
    STYLE_LABELS,
    VIDEO_ENCODER_LABELS,
    VIDEO_EXTENSIONS,
    WatermarkOptions,
    available_video_encoders,
    default_font_path,
    find_ffmpeg,
    is_image_file,
    is_video_file,
    iter_media_files,
    make_preview_image,
    make_video_preview_image,
    process_file,
)


APP_TITLE = "智影水印 - 图片/视频批量水印"
ROOT_BG = "#08090d"
PANEL_BG = "#11141a"
SOFT_BG = "#171b23"
FIELD_BG = "#0b0d12"
BORDER = "#2b313d"
TEXT = "#f8fafc"
MUTED = "#9ca3af"
SOFT_TEXT = "#cbd5e1"
ACCENT = "#f97316"
ACCENT_HOVER = "#fb923c"
ACCENT_DARK = "#7c2d12"
PREVIEW_BG = "#05070d"
THEMES = {
    "dark": {
        "mode_label": "☀ 白天",
        "root": ROOT_BG,
        "panel": PANEL_BG,
        "soft": SOFT_BG,
        "field": FIELD_BG,
        "border": BORDER,
        "text": TEXT,
        "muted": MUTED,
        "soft_text": SOFT_TEXT,
        "section": "#fed7aa",
        "accent": ACCENT,
        "accent_hover": ACCENT_HOVER,
        "accent_pressed": "#ea580c",
        "accent_disabled": ACCENT_DARK,
        "accent_disabled_text": "#fed7aa",
        "button_bg": "#242a35",
        "button_active": "#343b49",
        "button_pressed": "#1f2430",
        "field_disabled": "#111827",
        "disabled_text": "#64748b",
        "tree_bg": "#0c0f15",
        "tree_heading": "#1f2530",
        "tree_selected": "#7c2d12",
        "tree_selected_text": "#fff7ed",
        "progress_trough": "#1f2937",
        "preview_bg": PREVIEW_BG,
        "log_bg": "#0c0f15",
        "badge_ok_bg": "#172a1f",
        "badge_ok_fg": "#86efac",
        "badge_warn_bg": "#2b170b",
        "badge_warn_fg": "#fdba74",
        "check_select": FIELD_BG,
    },
    "light": {
        "mode_label": "☾ 夜晚",
        "root": "#dff3ff",
        "panel": "#ffffff",
        "soft": "#eff8ff",
        "field": "#f8fbff",
        "border": "#b8d7ea",
        "text": "#0f172a",
        "muted": "#475569",
        "soft_text": "#334155",
        "section": "#075985",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_pressed": "#1e40af",
        "accent_disabled": "#bfdbfe",
        "accent_disabled_text": "#1e3a8a",
        "button_bg": "#e0f2fe",
        "button_active": "#bae6fd",
        "button_pressed": "#7dd3fc",
        "field_disabled": "#e2e8f0",
        "disabled_text": "#94a3b8",
        "tree_bg": "#f8fbff",
        "tree_heading": "#dbeafe",
        "tree_selected": "#bfdbfe",
        "tree_selected_text": "#0f172a",
        "progress_trough": "#bae6fd",
        "preview_bg": "#eaf8ff",
        "log_bg": "#f8fbff",
        "badge_ok_bg": "#dcfce7",
        "badge_ok_fg": "#166534",
        "badge_warn_bg": "#ffedd5",
        "badge_warn_fg": "#9a3412",
        "check_select": "#e0f2fe",
    },
}
SUPPORTED_PATTERNS = [
    ("媒体文件", " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))),
    ("图片", " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS))),
    ("视频", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))),
    ("所有文件", "*.*"),
]
WATERMARK_PRESETS = {
    "清晰角标": {
        "position": POSITION_LABELS["smart_corner"],
        "style": STYLE_LABELS["smart"],
        "opacity": 92,
        "margin": 28,
        "auto_size": True,
        "font_size": 32,
        "use_panel": True,
        "logo_scale": 12,
        "logo_gap": 10,
    },
    "轻量标记": {
        "position": POSITION_LABELS["bottom_right"],
        "style": STYLE_LABELS["light"],
        "opacity": 66,
        "margin": 36,
        "auto_size": True,
        "font_size": 28,
        "use_panel": False,
        "logo_scale": 10,
        "logo_gap": 8,
    },
    "强可见": {
        "position": POSITION_LABELS["bottom_right"],
        "style": STYLE_LABELS["smart"],
        "opacity": 100,
        "margin": 24,
        "auto_size": True,
        "font_size": 38,
        "use_panel": True,
        "logo_scale": 15,
        "logo_gap": 12,
    },
    "平铺防盗": {
        "position": POSITION_LABELS["tile"],
        "style": STYLE_LABELS["smart"],
        "opacity": 52,
        "margin": 28,
        "auto_size": True,
        "font_size": 30,
        "use_panel": False,
        "logo_scale": 10,
        "logo_gap": 10,
    },
    "Logo 品牌": {
        "position": POSITION_LABELS["bottom_right"],
        "style": STYLE_LABELS["smart"],
        "opacity": 94,
        "margin": 30,
        "auto_size": True,
        "font_size": 30,
        "use_panel": True,
        "logo_scale": 16,
        "logo_gap": 12,
    },
}
TEXT_COLOR_MODES = {
    "smart": "智能选色",
    "custom": "自定义颜色",
}
STROKE_COLOR_MODES = {
    "smart": "智能反差",
    "custom": "自定义颜色",
}


def resource_path(*parts: str) -> Path:
    candidates: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(getattr(sys, "_MEIPASS")).joinpath(*parts))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent.joinpath(*parts))
    candidates.append(Path(__file__).resolve().parent.joinpath(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


class WatermarkApp(TkBase):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x920")
        self.minsize(1180, 760)
        self.configure(bg=ROOT_BG)
        self._set_window_icon()

        self.files: list[Path] = []
        self.item_for_path: dict[str, str] = {}
        self.worker: threading.Thread | None = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.preview_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_after_id: str | None = None
        self.preview_token = 0
        self.preview_zoom = 1.0
        self.preview_pan_x = 0.0
        self.preview_pan_y = 0.0
        self._preview_drag_start_x = 0
        self._preview_drag_start_y = 0
        self._preview_drag_pan_x = 0.0
        self._preview_drag_pan_y = 0.0
        self.cancel_event = threading.Event()
        self.settings_path = self._settings_path()
        self._drop_wndproc = None
        self._drop_old_wndproc = None
        self._drop_old_wndprocs: dict[int, object] = {}
        self.checkbuttons: list[Checkbutton] = []
        self.color_buttons: dict[str, Button] = {}
        self.preview_buttons: list[Button] = []
        self.preview_toolbar_window: int | None = None

        self.theme_var = StringVar(value="dark")
        self.text_var = StringVar(value="AI-Generated (Audio & Visuals)")
        self.font_path_var = StringVar(value=default_font_path())
        self.auto_size_var = BooleanVar(value=True)
        self.font_size_var = IntVar(value=32)
        self.opacity_var = IntVar(value=92)
        self.margin_var = IntVar(value=28)
        self.quality_var = IntVar(value=95)
        self.panel_var = BooleanVar(value=True)
        self.position_var = StringVar(value=POSITION_LABELS["smart_corner"])
        self.style_var = StringVar(value=STYLE_LABELS["smart"])
        self.text_color_mode_var = StringVar(value=TEXT_COLOR_MODES["smart"])
        self.text_color_var = StringVar(value="#FFFFFF")
        self.stroke_enabled_var = BooleanVar(value=True)
        self.stroke_color_mode_var = StringVar(value=STROKE_COLOR_MODES["smart"])
        self.stroke_color_var = StringVar(value="#000000")
        self.logo_path_var = StringVar(value="")
        self.logo_scale_var = IntVar(value=12)
        self.logo_gap_var = IntVar(value=10)
        self.output_dir_var = StringVar(value=str(Path.cwd() / "output"))
        self.ffmpeg_path_var = StringVar(value=find_ffmpeg())
        self.video_encoder_var = StringVar(value=VIDEO_ENCODER_LABELS["auto"])
        self.open_after_var = BooleanVar(value=False)
        self.status_var = StringVar(value="准备就绪")
        self.progress_var = DoubleVar(value=0)
        self.preset_var = StringVar(value="清晰角标")

        self._load_settings()
        self._configure_style()
        self._build_layout()
        self._apply_theme()
        self._refresh_ffmpeg_badge()
        self.after(120, self._drain_queue)
        self.after(200, self._enable_drag_drop)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self) -> None:
        icon_path = resource_path("assets", "icon.ico")
        if not icon_path.exists():
            return
        try:
            self.iconbitmap(str(icon_path))
        except Exception:
            pass

    def _colors(self) -> dict[str, str]:
        return THEMES.get(self.theme_var.get(), THEMES["dark"])

    def _register_checkbutton(self, checkbutton: Checkbutton) -> Checkbutton:
        self.checkbuttons.append(checkbutton)
        return checkbutton

    def _normalize_hex_color(self, value: str) -> str:
        text = (value or "").strip().lstrip("#")
        if len(text) == 3:
            text = "".join(char * 2 for char in text)
        if len(text) != 6:
            return ""
        try:
            int(text, 16)
        except ValueError:
            return ""
        return f"#{text.upper()}"

    def _settings_path(self) -> Path:
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "WatermarkStudio" / "settings.json"

    def _settings_snapshot(self) -> dict[str, object]:
        return {
            "text": self.text_var.get(),
            "font_path": self.font_path_var.get(),
            "auto_size": self.auto_size_var.get(),
            "font_size": self.font_size_var.get(),
            "opacity": self.opacity_var.get(),
            "margin": self.margin_var.get(),
            "quality": self.quality_var.get(),
            "use_panel": self.panel_var.get(),
            "position": self.position_var.get(),
            "style": self.style_var.get(),
            "text_color_mode": self.text_color_mode_var.get(),
            "text_color": self.text_color_var.get(),
            "stroke_enabled": self.stroke_enabled_var.get(),
            "stroke_color_mode": self.stroke_color_mode_var.get(),
            "stroke_color": self.stroke_color_var.get(),
            "logo_path": self.logo_path_var.get(),
            "logo_scale": self.logo_scale_var.get(),
            "logo_gap": self.logo_gap_var.get(),
            "output_dir": self.output_dir_var.get(),
            "ffmpeg_path": self.ffmpeg_path_var.get(),
            "video_encoder": self.video_encoder_var.get(),
            "open_after": self.open_after_var.get(),
            "preset": self.preset_var.get(),
            "theme": self.theme_var.get(),
        }

    def _load_settings(self) -> None:
        if not self.settings_path.exists():
            return

        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        def set_int(variable: IntVar, key: str, minimum: int, maximum: int) -> None:
            try:
                value = int(data.get(key, variable.get()))
            except (TypeError, ValueError):
                return
            variable.set(max(minimum, min(maximum, value)))

        def set_hex(variable: StringVar, key: str, default: str) -> None:
            value = str(data.get(key, variable.get() or default)).strip()
            if self._normalize_hex_color(value):
                variable.set(self._normalize_hex_color(value))

        self.text_var.set(str(data.get("text", self.text_var.get())))
        self.font_path_var.set(str(data.get("font_path", self.font_path_var.get())))
        self.auto_size_var.set(bool(data.get("auto_size", self.auto_size_var.get())))
        set_int(self.font_size_var, "font_size", 12, 96)
        set_int(self.opacity_var, "opacity", 30, 100)
        set_int(self.margin_var, "margin", 0, 120)
        set_int(self.quality_var, "quality", 60, 100)
        self.panel_var.set(bool(data.get("use_panel", self.panel_var.get())))

        position = str(data.get("position", self.position_var.get()))
        if position in POSITION_LABELS.values():
            self.position_var.set(position)
        style = str(data.get("style", self.style_var.get()))
        if style in STYLE_LABELS.values():
            self.style_var.set(style)

        text_mode = str(data.get("text_color_mode", self.text_color_mode_var.get()))
        if text_mode in TEXT_COLOR_MODES.values():
            self.text_color_mode_var.set(text_mode)
        set_hex(self.text_color_var, "text_color", "#FFFFFF")
        self.stroke_enabled_var.set(bool(data.get("stroke_enabled", self.stroke_enabled_var.get())))
        stroke_mode = str(data.get("stroke_color_mode", self.stroke_color_mode_var.get()))
        if stroke_mode in STROKE_COLOR_MODES.values():
            self.stroke_color_mode_var.set(stroke_mode)
        set_hex(self.stroke_color_var, "stroke_color", "#000000")

        self.logo_path_var.set(str(data.get("logo_path", self.logo_path_var.get())))
        set_int(self.logo_scale_var, "logo_scale", 4, 35)
        set_int(self.logo_gap_var, "logo_gap", 0, 80)
        self.output_dir_var.set(str(data.get("output_dir", self.output_dir_var.get())))
        self.ffmpeg_path_var.set(str(data.get("ffmpeg_path", self.ffmpeg_path_var.get())))
        encoder = str(data.get("video_encoder", self.video_encoder_var.get()))
        if encoder in VIDEO_ENCODER_LABELS.values():
            self.video_encoder_var.set(encoder)
        self.open_after_var.set(bool(data.get("open_after", self.open_after_var.get())))
        preset = str(data.get("preset", self.preset_var.get()))
        if preset in WATERMARK_PRESETS:
            self.preset_var.set(preset)
        theme = str(data.get("theme", self.theme_var.get()))
        if theme in THEMES:
            self.theme_var.set(theme)

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(
                json.dumps(self._settings_snapshot(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._append_log(f"设置已保存：{self.settings_path}")
        except OSError as exc:
            self._append_log(f"设置保存失败：{exc}")

    def _reset_settings(self) -> None:
        self.text_var.set("AI-Generated (Audio & Visuals)")
        self.font_path_var.set(default_font_path())
        self.auto_size_var.set(True)
        self.font_size_var.set(32)
        self.opacity_var.set(92)
        self.margin_var.set(28)
        self.quality_var.set(95)
        self.panel_var.set(True)
        self.position_var.set(POSITION_LABELS["smart_corner"])
        self.style_var.set(STYLE_LABELS["smart"])
        self.text_color_mode_var.set(TEXT_COLOR_MODES["smart"])
        self.text_color_var.set("#FFFFFF")
        self.stroke_enabled_var.set(True)
        self.stroke_color_mode_var.set(STROKE_COLOR_MODES["smart"])
        self.stroke_color_var.set("#000000")
        self.logo_path_var.set("")
        self.logo_scale_var.set(12)
        self.logo_gap_var.set(10)
        self.output_dir_var.set(str(Path.cwd() / "output"))
        self.ffmpeg_path_var.set(find_ffmpeg())
        self.video_encoder_var.set(VIDEO_ENCODER_LABELS["auto"])
        self.open_after_var.set(False)
        self.preset_var.set("清晰角标")
        self.theme_var.set("dark")
        self._refresh_color_swatches()
        self._apply_theme()
        self._refresh_ffmpeg_badge()
        self.update_preview()
        self._append_log("已恢复默认设置")

    def apply_preset(self) -> None:
        preset = WATERMARK_PRESETS.get(self.preset_var.get())
        if not preset:
            return

        self.position_var.set(str(preset["position"]))
        self.style_var.set(str(preset["style"]))
        self.opacity_var.set(int(preset["opacity"]))
        self.margin_var.set(int(preset["margin"]))
        self.auto_size_var.set(bool(preset["auto_size"]))
        self.font_size_var.set(int(preset["font_size"]))
        self.panel_var.set(bool(preset["use_panel"]))
        self.logo_scale_var.set(int(preset["logo_scale"]))
        self.logo_gap_var.set(int(preset["logo_gap"]))

        if self.preset_var.get() == "Logo 品牌" and not self.logo_path_var.get().strip():
            self._append_log("Logo 品牌预设已应用；可选择 Logo 图片获得完整效果")
        elif self.preset_var.get() == "平铺防盗":
            self._append_log("平铺防盗预设已应用；建议水印文字保持简短")
        else:
            self._append_log(f"已应用预设：{self.preset_var.get()}")
        self.update_preview()

    def _enable_drag_drop(self) -> None:
        if self._enable_tkdnd_drop():
            return
        self._enable_native_drop()

    def _enable_tkdnd_drop(self) -> bool:
        if not TKDND_AVAILABLE:
            return False

        widgets = [
            self,
            getattr(self, "left_panel", None),
            getattr(self, "tree", None),
            getattr(self, "preview_shell", None),
            getattr(self, "preview_canvas", None),
            getattr(self, "log_shell", None),
            getattr(self, "log_list", None),
            getattr(self, "right_shell", None),
            getattr(self, "settings_canvas", None),
        ]
        registered = 0
        for widget in widgets:
            if widget is None:
                continue
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_tkdnd_drop)
                registered += 1
            except Exception:
                continue

        if registered:
            self._append_log(f"已启用稳定拖拽添加文件（{registered} 个区域）")
            return True
        return False

    def _on_tkdnd_drop(self, event) -> None:
        try:
            paths = [Path(item) for item in self.tk.splitlist(event.data) if item]
        except Exception as exc:
            self._append_log(f"拖拽读取失败：{exc}")
            return
        self._handle_dropped_paths(paths)

    def _enable_native_drop(self) -> None:
        if os.name != "nt":
            self._append_log("当前系统不支持内置拖拽，仍可使用添加文件按钮")
            return

        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            wm_dropfiles = 0x0233
            wm_copyglobaldata = 0x0049
            gwl_wndproc = -4
            lresult = ctypes.c_longlong if sys.maxsize > 2**32 else ctypes.c_long
            wndproc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

            set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            set_window_long_ptr.restype = ctypes.c_void_p
            call_window_proc = user32.CallWindowProcW
            call_window_proc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            call_window_proc.restype = lresult

            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
            shell32.DragQueryFileW.restype = wintypes.UINT
            shell32.DragFinish.argtypes = [wintypes.HANDLE]
            change_filter = getattr(user32, "ChangeWindowMessageFilterEx", None)
            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = lresult

            def wndproc(window_handle, message, wparam, lparam):
                if message == wm_dropfiles:
                    paths: list[Path] = []
                    try:
                        paths = self._paths_from_drop(wparam)
                    except Exception as exc:
                        self.after(0, lambda error=exc: self._append_log(f"拖拽读取失败：{error}"))
                    finally:
                        shell32.DragFinish(wparam)
                    if paths:
                        self.after(0, lambda dropped_paths=paths: self._handle_dropped_paths(dropped_paths))
                    return 0
                old_proc = self._drop_old_wndprocs.get(int(window_handle))
                if old_proc:
                    return call_window_proc(old_proc, window_handle, message, wparam, lparam)
                return user32.DefWindowProcW(window_handle, message, wparam, lparam)

            self._drop_wndproc = wndproc_type(wndproc)
            hwnd = self.winfo_id()
            if int(hwnd) not in self._drop_old_wndprocs:
                old_proc = set_window_long_ptr(
                    hwnd,
                    gwl_wndproc,
                    ctypes.cast(self._drop_wndproc, ctypes.c_void_p).value,
                )
                self._drop_old_wndprocs[int(hwnd)] = old_proc
                shell32.DragAcceptFiles(hwnd, True)
                if change_filter:
                    change_filter(hwnd, wm_dropfiles, 1, None)
                    change_filter(hwnd, wm_copyglobaldata, 1, None)
            self._append_log("已启用稳定拖拽添加文件")
        except Exception as exc:
            self._append_log(f"拖拽初始化失败：{exc}")

    def _paths_from_drop(self, drop_handle) -> list[Path]:
        shell32 = ctypes.windll.shell32
        count = shell32.DragQueryFileW(drop_handle, 0xFFFFFFFF, None, 0)
        paths: list[Path] = []
        for index in range(count):
            length = shell32.DragQueryFileW(drop_handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(drop_handle, index, buffer, length + 1)
            paths.append(Path(buffer.value))
        return paths

    def _handle_dropped_paths(self, paths: list[Path]) -> None:
        expanded: list[Path] = []
        for path in paths:
            if path.is_dir():
                expanded.extend(iter_media_files(path))
            else:
                expanded.append(path)
        before = len(self.files)
        self._add_paths(expanded)
        added = len(self.files) - before
        self._append_log(f"拖拽添加 {added} 个文件")

    def _configure_style(self) -> None:
        colors = self._colors()
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Root.TFrame", background=colors["root"])
        style.configure("Panel.TFrame", background=colors["panel"], borderwidth=1, relief="solid")
        style.configure("Soft.TFrame", background=colors["soft"])
        style.configure("Header.TFrame", background=colors["root"])
        style.configure("Toolbar.TFrame", background=colors["panel"])
        style.configure("TLabel", background=colors["panel"], foreground=colors["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("SoftMuted.TLabel", background=colors["soft"], foreground=colors["soft_text"], font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=colors["root"], foreground=colors["text"], font=("Microsoft YaHei UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background=colors["root"], foreground=colors["muted"], font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabel", background=colors["panel"], foreground=colors["section"], font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 9), background=colors["accent"], foreground="#ffffff", bordercolor=colors["accent"])
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 7), background=colors["button_bg"], foreground=colors["text"], bordercolor=colors["border"])
        style.map(
            "Accent.TButton",
            background=[("active", colors["accent_hover"]), ("pressed", colors["accent_pressed"]), ("disabled", colors["accent_disabled"])],
            foreground=[("disabled", colors["accent_disabled_text"])],
        )
        style.map("TButton", background=[("active", colors["button_active"]), ("pressed", colors["button_pressed"])], foreground=[("disabled", colors["disabled_text"])])
        style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            insertcolor=colors["text"],
            padding=(8, 6),
        )
        style.map("TEntry", fieldbackground=[("disabled", colors["field_disabled"])], foreground=[("disabled", colors["disabled_text"])])
        style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["button_bg"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            arrowcolor=colors["accent"],
            padding=(8, 6),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"]), ("disabled", colors["field_disabled"])],
            foreground=[("readonly", colors["text"]), ("disabled", colors["disabled_text"])],
            selectbackground=[("readonly", colors["field"])],
            selectforeground=[("readonly", colors["text"])],
        )
        style.configure("Treeview", background=colors["tree_bg"], fieldbackground=colors["tree_bg"], foreground=colors["text"], rowheight=34, bordercolor=colors["border"], font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", background=colors["tree_heading"], foreground=colors["section"], bordercolor=colors["border"], font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", colors["tree_selected"])], foreground=[("selected", colors["tree_selected_text"])])
        style.configure("Horizontal.TProgressbar", troughcolor=colors["progress_trough"], background=colors["accent"], bordercolor=colors["progress_trough"])

    def _toggle_theme(self) -> None:
        self.theme_var.set("light" if self.theme_var.get() == "dark" else "dark")
        self._apply_theme()
        self._save_settings()

    def _apply_theme(self) -> None:
        colors = self._colors()
        self.configure(bg=colors["root"])
        self._configure_style()

        if hasattr(self, "settings_canvas"):
            self.settings_canvas.configure(bg=colors["panel"])
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.configure(
                bg=colors["preview_bg"],
                highlightbackground=colors["border"],
            )
            self._render_preview_canvas()
        if hasattr(self, "preview_tools"):
            self.preview_tools.configure(bg=colors["preview_bg"])
        if hasattr(self, "log_list"):
            self.log_list.configure(
                bg=colors["log_bg"],
                fg=colors["soft_text"],
                selectbackground=colors["tree_selected"],
                selectforeground=colors["tree_selected_text"],
            )
        if hasattr(self, "theme_button"):
            self.theme_button.configure(
                text=colors["mode_label"],
                bg=colors["button_bg"],
                fg=colors["text"],
                activebackground=colors["button_active"],
                activeforeground=colors["text"],
                highlightbackground=colors["border"],
            )
        for checkbutton in self.checkbuttons:
            checkbutton.configure(
                bg=colors["panel"],
                fg=colors["soft_text"],
                activebackground=colors["panel"],
                activeforeground=colors["text"],
                selectcolor=colors["check_select"],
            )
        for button in self.preview_buttons:
            button.configure(
                bg=colors["button_bg"],
                fg=colors["text"],
                activebackground=colors["button_active"],
                activeforeground=colors["text"],
                highlightbackground=colors["border"],
            )
        self._refresh_color_swatches()
        self._refresh_ffmpeg_badge()

    def _swatch_text_color(self, color_value: str) -> str:
        normalized = self._normalize_hex_color(color_value) or "#000000"
        red = int(normalized[1:3], 16)
        green = int(normalized[3:5], 16)
        blue = int(normalized[5:7], 16)
        luminance = red * 0.299 + green * 0.587 + blue * 0.114
        return "#111827" if luminance > 150 else "#ffffff"

    def _refresh_color_swatches(self) -> None:
        swatches = {
            "text": self.text_color_var.get(),
            "stroke": self.stroke_color_var.get(),
        }
        for key, value in swatches.items():
            button = self.color_buttons.get(key)
            if not button:
                continue
            color = self._normalize_hex_color(value) or ("#FFFFFF" if key == "text" else "#000000")
            button.configure(
                bg=color,
                fg=self._swatch_text_color(color),
                activebackground=color,
                activeforeground=self._swatch_text_color(color),
                text=color,
            )

    def _pick_color(self, variable: StringVar, mode_variable: StringVar, custom_label: str, title: str) -> None:
        current = self._normalize_hex_color(variable.get()) or "#FFFFFF"
        _rgb, color = colorchooser.askcolor(color=current, title=title, parent=self)
        normalized = self._normalize_hex_color(str(color or ""))
        if not normalized:
            return
        variable.set(normalized)
        mode_variable.set(custom_label)
        self._refresh_color_swatches()
        self.update_preview()

    def _zoom_preview(self, factor: float) -> None:
        if self.preview_image is None:
            return
        self.preview_zoom = max(1.0, min(6.0, self.preview_zoom * factor))
        self._render_preview_canvas()

    def _reset_preview_view(self) -> None:
        self.preview_zoom = 1.0
        self.preview_pan_x = 0.0
        self.preview_pan_y = 0.0
        self._render_preview_canvas()

    def _begin_preview_pan(self, event) -> None:
        if self.preview_image is None or self.preview_zoom <= 1.0:
            return
        self._preview_drag_start_x = event.x
        self._preview_drag_start_y = event.y
        self._preview_drag_pan_x = self.preview_pan_x
        self._preview_drag_pan_y = self.preview_pan_y
        self.preview_canvas.configure(cursor="fleur")

    def _pan_preview(self, event) -> None:
        if self.preview_image is None or self.preview_zoom <= 1.0:
            return
        self.preview_pan_x = self._preview_drag_pan_x + event.x - self._preview_drag_start_x
        self.preview_pan_y = self._preview_drag_pan_y + event.y - self._preview_drag_start_y
        self._render_preview_canvas()

    def _end_preview_pan(self, _event) -> None:
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.configure(cursor="fleur" if self.preview_image is not None and self.preview_zoom > 1.0 else "arrow")

    def _preview_scales(self) -> tuple[float, int, int]:
        if self.preview_image is None or not hasattr(self, "preview_canvas"):
            return 1.0, 0, 0
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        image_width, image_height = self.preview_image.size
        fit_scale = min(canvas_width / image_width, canvas_height / image_height, 1.0)
        scale = max(0.05, fit_scale * self.preview_zoom)
        return scale, max(1, int(image_width * scale)), max(1, int(image_height * scale))

    def _clamp_preview_pan(self, scaled_width: int, scaled_height: int) -> None:
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        max_x = max(0.0, (scaled_width - canvas_width) / 2)
        max_y = max(0.0, (scaled_height - canvas_height) / 2)
        self.preview_pan_x = max(-max_x, min(max_x, self.preview_pan_x)) if max_x else 0.0
        self.preview_pan_y = max(-max_y, min(max_y, self.preview_pan_y)) if max_y else 0.0

    def _render_preview_canvas(self, _event=None) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        colors = self._colors()
        canvas = self.preview_canvas
        canvas.delete("preview_content")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())

        if self.preview_image is None:
            canvas.create_text(
                width / 2,
                height / 2,
                text=getattr(self, "preview_message", "选择一个图片或视频后可预览智能水印效果"),
                fill=colors["soft_text"],
                font=("Microsoft YaHei UI", 10),
                tags=("preview_content",),
                width=max(280, width - 80),
                justify="center",
            )
            self.preview_photo = None
        else:
            _scale, scaled_width, scaled_height = self._preview_scales()
            self._clamp_preview_pan(scaled_width, scaled_height)
            resized = self.preview_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(resized)
            left = (width - scaled_width) / 2 + self.preview_pan_x
            top = (height - scaled_height) / 2 + self.preview_pan_y
            canvas.create_image(left, top, image=self.preview_photo, anchor="nw", tags=("preview_content",))
            if self.preview_zoom > 1.0:
                canvas.configure(cursor="fleur")
            else:
                canvas.configure(cursor="arrow")

        if self.preview_toolbar_window is not None:
            canvas.tag_raise(self.preview_toolbar_window)

    def _build_layout(self) -> None:
        colors = self._colors()
        root = ttk.Frame(self, style="Root.TFrame", padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, style="Header.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        header.columnconfigure(1, weight=1)
        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.grid(row=0, column=0, sticky="w")
        ttk.Label(title_block, text="智影水印", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_block, text="图片与视频批量智能水印工具", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        header_actions = ttk.Frame(header, style="Header.TFrame")
        header_actions.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.theme_button = Button(
            header_actions,
            text=colors["mode_label"],
            command=self._toggle_theme,
            bg=colors["button_bg"],
            fg=colors["text"],
            activebackground=colors["button_active"],
            activeforeground=colors["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=colors["border"],
            padx=14,
            pady=7,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.theme_button.grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.ffmpeg_badge = Label(header_actions, text="", bg=colors["badge_ok_bg"], fg=colors["badge_ok_fg"], padx=14, pady=7, font=("Microsoft YaHei UI", 9, "bold"))
        self.ffmpeg_badge.grid(row=0, column=1, sticky="e")

        left = ttk.Frame(root, style="Panel.TFrame", padding=14)
        self.left_panel = left
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1, minsize=170)
        left.rowconfigure(3, weight=3, minsize=360)
        left.rowconfigure(4, weight=0)

        toolbar = ttk.Frame(left, style="Toolbar.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(4, weight=1)
        ttk.Button(toolbar, text="添加文件", style="Accent.TButton", command=self.add_files).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(toolbar, text="添加文件夹", command=self.add_folder).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(toolbar, text="移除选中", command=self.remove_selected).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="清空", command=self.clear_files).grid(row=0, column=3, padx=(0, 8))
        self.file_count_label = ttk.Label(toolbar, text="已选择 0 个文件", style="Muted.TLabel")
        self.file_count_label.grid(row=0, column=4, sticky="e")

        hint = ttk.Label(left, text="把图片/视频/文件夹拖到列表或预览区即可添加；也可批量选择。图片：jpg/png/webp/bmp/tiff；视频：mp4/mkv/mov/avi/wmv。", style="Muted.TLabel")
        hint.grid(row=1, column=0, sticky="w", pady=(0, 8))

        columns = ("type", "status", "path")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("type", text="类型")
        self.tree.heading("status", text="状态")
        self.tree.heading("path", text="文件")
        self.tree.column("type", width=70, anchor="center", stretch=False)
        self.tree.column("status", width=110, anchor="center", stretch=False)
        self.tree.column("path", minwidth=360, width=620, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_preview())

        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        preview_shell = ttk.Frame(left, style="Soft.TFrame", padding=12)
        self.preview_shell = preview_shell
        preview_shell.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        preview_shell.columnconfigure(0, weight=1)
        preview_shell.rowconfigure(1, weight=1)
        ttk.Label(preview_shell, text="大预览", style="SoftMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.preview_message = "选择或拖入一个图片/视频后，可在这里查看更大的水印预览"
        self.preview_canvas = Canvas(
            preview_shell,
            bg=colors["preview_bg"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
        )
        self.preview_canvas.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.preview_canvas.bind("<Configure>", self._render_preview_canvas)
        self.preview_canvas.bind("<ButtonPress-1>", self._begin_preview_pan)
        self.preview_canvas.bind("<B1-Motion>", self._pan_preview)
        self.preview_canvas.bind("<ButtonRelease-1>", self._end_preview_pan)

        preview_tools = Frame(self.preview_canvas, bg=colors["preview_bg"])
        self.preview_tools = preview_tools
        tool_specs = [
            ("＋", lambda: self._zoom_preview(1.25), "放大预览"),
            ("－", lambda: self._zoom_preview(0.8), "缩小预览"),
            ("全景", self._reset_preview_view, "还原全景"),
        ]
        for index, (text, command, _hint) in enumerate(tool_specs):
            button = Button(
                preview_tools,
                text=text,
                command=command,
                bg=colors["button_bg"],
                fg=colors["text"],
                activebackground=colors["button_active"],
                activeforeground=colors["text"],
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=colors["border"],
                padx=9,
                pady=4,
                font=("Microsoft YaHei UI", 9, "bold"),
            )
            button.grid(row=0, column=index, padx=(0, 6))
            self.preview_buttons.append(button)
        self.preview_toolbar_window = self.preview_canvas.create_window(14, 14, window=preview_tools, anchor="nw")
        self._render_preview_canvas()

        log_shell = ttk.Frame(left, style="Soft.TFrame", padding=10)
        self.log_shell = log_shell
        log_shell.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        log_shell.columnconfigure(0, weight=1)
        log_header = ttk.Frame(log_shell, style="Soft.TFrame")
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="处理日志", style="SoftMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="导出日志", style="Accent.TButton", command=self.export_log).grid(row=0, column=1, sticky="e")
        self.log_list = Listbox(
            log_shell,
            height=5,
            bg=colors["log_bg"],
            fg=colors["soft_text"],
            selectbackground=colors["tree_selected"],
            selectforeground=colors["tree_selected_text"],
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 9),
        )
        self.log_list.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        right_shell = ttk.Frame(root, style="Panel.TFrame")
        self.right_shell = right_shell
        right_shell.grid(row=1, column=1, sticky="ns")
        right_shell.columnconfigure(0, weight=1)
        right_shell.rowconfigure(0, weight=1)

        settings_canvas = Canvas(right_shell, bg=colors["panel"], highlightthickness=0, width=360)
        self.settings_canvas = settings_canvas
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar = ttk.Scrollbar(right_shell, orient="vertical", command=settings_canvas.yview)
        settings_scrollbar.grid(row=0, column=1, sticky="ns")
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)

        right = ttk.Frame(settings_canvas, style="Panel.TFrame", padding=18)
        settings_window = settings_canvas.create_window((0, 0), window=right, anchor="nw")
        right.columnconfigure(0, weight=1)

        def sync_settings_region(_event=None) -> None:
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
            settings_canvas.itemconfigure(settings_window, width=settings_canvas.winfo_width())

        right.bind("<Configure>", sync_settings_region)
        settings_canvas.bind("<Configure>", sync_settings_region)
        settings_canvas.bind_all("<MouseWheel>", lambda event: settings_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        self._build_settings(right)

        footer = ttk.Frame(root, style="Root.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(footer, textvariable=self.status_var, style="Title.TLabel", font=("Microsoft YaHei UI", 9)).grid(row=0, column=1, sticky="e")

    def _build_settings(self, parent: ttk.Frame) -> None:
        colors = self._colors()
        row = 0
        ttk.Label(parent, text="水印预设", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        preset_line = ttk.Frame(parent, style="Panel.TFrame")
        preset_line.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        preset_line.columnconfigure(0, weight=1)
        preset_box = ttk.Combobox(preset_line, textvariable=self.preset_var, state="readonly", values=list(WATERMARK_PRESETS))
        preset_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(preset_line, text="应用", style="Accent.TButton", command=self.apply_preset).grid(row=0, column=1)

        row += 1
        ttk.Label(parent, text="水印文字", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Entry(parent, textvariable=self.text_var, width=34).grid(row=row, column=0, sticky="ew", pady=(6, 14))
        self.text_var.trace_add("write", lambda *_args: self.update_preview())

        row += 1
        ttk.Label(parent, text="字体文件", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        font_line = ttk.Frame(parent, style="Panel.TFrame")
        font_line.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        font_line.columnconfigure(0, weight=1)
        ttk.Entry(font_line, textvariable=self.font_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(font_line, text="选择", style="Accent.TButton", command=self.pick_font).grid(row=0, column=1)

        row += 1
        auto_size_check = self._register_checkbutton(Checkbutton(
            parent,
            text="字体大小自适应",
            variable=self.auto_size_var,
            command=self.update_preview,
            bg=colors["panel"],
            fg=colors["soft_text"],
            activebackground=colors["panel"],
            activeforeground=colors["text"],
            selectcolor=colors["check_select"],
            font=("Microsoft YaHei UI", 10),
        ))
        auto_size_check.grid(row=row, column=0, sticky="w", pady=(0, 6))

        row += 1
        self._slider(parent, row, "字体大小", self.font_size_var, 12, 96, "px")
        row += 1
        self._slider(parent, row, "透明度", self.opacity_var, 30, 100, "%")
        row += 1
        self._slider(parent, row, "边距", self.margin_var, 0, 120, "px")
        row += 1
        self._slider(parent, row, "图片质量", self.quality_var, 60, 100, "%")

        row += 1
        ttk.Label(parent, text="水印位置", style="Section.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1
        position_box = ttk.Combobox(parent, textvariable=self.position_var, state="readonly", values=list(POSITION_LABELS.values()))
        position_box.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        position_box.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())

        row += 1
        ttk.Label(parent, text="文字风格", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        style_box = ttk.Combobox(parent, textvariable=self.style_var, state="readonly", values=list(STYLE_LABELS.values()))
        style_box.grid(row=row, column=0, sticky="ew", pady=(6, 10))
        style_box.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())

        row += 1
        ttk.Label(parent, text="文字颜色", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        color_line = ttk.Frame(parent, style="Panel.TFrame")
        color_line.grid(row=row, column=0, sticky="ew", pady=(6, 10))
        color_line.columnconfigure(0, weight=1)
        text_color_mode_box = ttk.Combobox(
            color_line,
            textvariable=self.text_color_mode_var,
            state="readonly",
            values=list(TEXT_COLOR_MODES.values()),
            width=12,
        )
        text_color_mode_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        text_color_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())
        text_swatch = Button(
            color_line,
            command=lambda: self._pick_color(self.text_color_var, self.text_color_mode_var, TEXT_COLOR_MODES["custom"], "选择文字颜色"),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=("Consolas", 9, "bold"),
        )
        text_swatch.grid(row=0, column=1, sticky="e")
        self.color_buttons["text"] = text_swatch

        row += 1
        stroke_check = self._register_checkbutton(Checkbutton(
            parent,
            text="启用文字描边",
            variable=self.stroke_enabled_var,
            command=self.update_preview,
            bg=colors["panel"],
            fg=colors["soft_text"],
            activebackground=colors["panel"],
            activeforeground=colors["text"],
            selectcolor=colors["check_select"],
            font=("Microsoft YaHei UI", 10),
        ))
        stroke_check.grid(row=row, column=0, sticky="w", pady=(0, 8))

        row += 1
        stroke_color_line = ttk.Frame(parent, style="Panel.TFrame")
        stroke_color_line.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        stroke_color_line.columnconfigure(0, weight=1)
        stroke_color_mode_box = ttk.Combobox(
            stroke_color_line,
            textvariable=self.stroke_color_mode_var,
            state="readonly",
            values=list(STROKE_COLOR_MODES.values()),
            width=12,
        )
        stroke_color_mode_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        stroke_color_mode_box.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())
        stroke_swatch = Button(
            stroke_color_line,
            command=lambda: self._pick_color(self.stroke_color_var, self.stroke_color_mode_var, STROKE_COLOR_MODES["custom"], "选择描边颜色"),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=("Consolas", 9, "bold"),
        )
        stroke_swatch.grid(row=0, column=1, sticky="e")
        self.color_buttons["stroke"] = stroke_swatch

        row += 1
        panel_check = self._register_checkbutton(Checkbutton(
            parent,
            text="使用半透明底衬增强清晰度",
            variable=self.panel_var,
            command=self.update_preview,
            bg=colors["panel"],
            fg=colors["soft_text"],
            activebackground=colors["panel"],
            activeforeground=colors["text"],
            selectcolor=colors["check_select"],
            font=("Microsoft YaHei UI", 10),
        ))
        panel_check.grid(row=row, column=0, sticky="w", pady=(0, 14))

        row += 1
        ttk.Label(parent, text="Logo 图片（可选）", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        logo_line = ttk.Frame(parent, style="Panel.TFrame")
        logo_line.grid(row=row, column=0, sticky="ew", pady=(6, 8))
        logo_line.columnconfigure(0, weight=1)
        ttk.Entry(logo_line, textvariable=self.logo_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(logo_line, text="选择", style="Accent.TButton", command=self.pick_logo).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(logo_line, text="清除", style="Accent.TButton", command=self.clear_logo).grid(row=0, column=2)
        self.logo_path_var.trace_add("write", lambda *_args: self.update_preview())

        row += 1
        self._slider(parent, row, "Logo 大小", self.logo_scale_var, 4, 35, "%")
        row += 1
        self._slider(parent, row, "Logo 间距", self.logo_gap_var, 0, 80, "px")

        row += 1
        ttk.Label(parent, text="输出目录", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        output_line = ttk.Frame(parent, style="Panel.TFrame")
        output_line.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        output_line.columnconfigure(0, weight=1)
        ttk.Entry(output_line, textvariable=self.output_dir_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(output_line, text="选择", style="Accent.TButton", command=self.pick_output_dir).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(output_line, text="打开", style="Accent.TButton", command=self.open_output_dir).grid(row=0, column=2)

        row += 1
        open_after_check = self._register_checkbutton(Checkbutton(
            parent,
            text="处理完成后打开输出目录",
            variable=self.open_after_var,
            bg=colors["panel"],
            fg=colors["soft_text"],
            activebackground=colors["panel"],
            activeforeground=colors["text"],
            selectcolor=colors["check_select"],
            font=("Microsoft YaHei UI", 10),
        ))
        open_after_check.grid(row=row, column=0, sticky="w", pady=(0, 14))

        row += 1
        ttk.Label(parent, text="FFmpeg", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        ffmpeg_line = ttk.Frame(parent, style="Panel.TFrame")
        ffmpeg_line.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        ffmpeg_line.columnconfigure(0, weight=1)
        ttk.Entry(ffmpeg_line, textvariable=self.ffmpeg_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(ffmpeg_line, text="选择", style="Accent.TButton", command=self.pick_ffmpeg).grid(row=0, column=1)

        row += 1
        ttk.Label(parent, text="视频编码器", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        encoder_box = ttk.Combobox(parent, textvariable=self.video_encoder_var, state="readonly", values=list(VIDEO_ENCODER_LABELS.values()))
        encoder_box.grid(row=row, column=0, sticky="ew", pady=(6, 14))
        row += 1
        ttk.Label(parent, text="硬件编码器不可用时会自动回退到 CPU H.264", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(0, 8))

        row += 1
        ttk.Button(parent, text="刷新预览", style="Accent.TButton", command=self.update_preview).grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1
        self.start_button = ttk.Button(parent, text="开始处理", style="Accent.TButton", command=self.start_processing)
        self.start_button.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        self.cancel_button = ttk.Button(parent, text="取消处理", command=self.cancel_processing)
        self.cancel_button.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        self.cancel_button.configure(state="disabled")
        row += 1
        settings_line = ttk.Frame(parent, style="Panel.TFrame")
        settings_line.grid(row=row, column=0, sticky="ew", pady=(0, 0))
        settings_line.columnconfigure(0, weight=1)
        settings_line.columnconfigure(1, weight=1)
        ttk.Button(settings_line, text="保存设置", style="Accent.TButton", command=self._save_settings).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(settings_line, text="恢复默认", style="Accent.TButton", command=self._reset_settings).grid(row=0, column=1, sticky="ew")

    def _slider(self, parent: ttk.Frame, row: int, label: str, variable: IntVar, min_value: int, max_value: int, suffix: str) -> None:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        value_label = ttk.Label(frame, text="", style="Muted.TLabel")

        def update_value(*_args: object) -> None:
            value_label.configure(text=f"{variable.get()} {suffix}")
            self.update_preview()

        ttk.Label(frame, text=label).grid(row=0, column=0, sticky="w")
        value_label.grid(row=0, column=2, sticky="e")
        scale = ttk.Scale(frame, from_=min_value, to=max_value, orient="horizontal", command=lambda value: variable.set(round(float(value))))
        scale.set(variable.get())
        scale.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        variable.trace_add("write", update_value)
        update_value()

    def _watermark_options(self) -> WatermarkOptions:
        position_by_label = {label: key for key, label in POSITION_LABELS.items()}
        style_by_label = {label: key for key, label in STYLE_LABELS.items()}
        encoder_by_label = {label: key for key, label in VIDEO_ENCODER_LABELS.items()}
        text_color_mode_by_label = {label: key for key, label in TEXT_COLOR_MODES.items()}
        stroke_color_mode_by_label = {label: key for key, label in STROKE_COLOR_MODES.items()}
        return WatermarkOptions(
            text=self.text_var.get().strip(),
            font_path=self.font_path_var.get().strip(),
            font_size=self.font_size_var.get(),
            auto_font_size=self.auto_size_var.get(),
            opacity=self.opacity_var.get(),
            margin=self.margin_var.get(),
            position=position_by_label.get(self.position_var.get(), "smart_corner"),
            style=style_by_label.get(self.style_var.get(), "smart"),
            use_panel=self.panel_var.get(),
            text_color_mode=text_color_mode_by_label.get(self.text_color_mode_var.get(), "smart"),
            text_color=self.text_color_var.get(),
            stroke_enabled=self.stroke_enabled_var.get(),
            stroke_color_mode=stroke_color_mode_by_label.get(self.stroke_color_mode_var.get(), "smart"),
            stroke_color=self.stroke_color_var.get(),
            image_quality=self.quality_var.get(),
            output_dir=self.output_dir_var.get().strip(),
            video_encoder=encoder_by_label.get(self.video_encoder_var.get(), "auto"),
            logo_path=self.logo_path_var.get().strip(),
            logo_scale=self.logo_scale_var.get(),
            logo_gap=self.logo_gap_var.get(),
        )

    def add_files(self) -> None:
        names = filedialog.askopenfilenames(title="选择图片或视频", filetypes=SUPPORTED_PATTERNS)
        self._add_paths(Path(name) for name in names)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择包含图片或视频的文件夹")
        if not folder:
            return
        self._add_paths(iter_media_files(folder))

    def _add_paths(self, paths) -> None:
        added = 0
        for path in paths:
            media_path = Path(path)
            key = str(media_path.resolve())
            if key in self.item_for_path:
                continue
            if not (is_image_file(media_path) or is_video_file(media_path)):
                continue
            media_type = "图片" if is_image_file(media_path) else "视频"
            item_id = self.tree.insert("", END, values=(media_type, "待处理", str(media_path)))
            self.files.append(media_path)
            self.item_for_path[key] = item_id
            added += 1
        self._refresh_file_count()
        if added and not self.tree.selection():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)
            self.update_preview()

    def remove_selected(self) -> None:
        selected = list(self.tree.selection())
        if not selected:
            return
        selected_paths = {self.tree.item(item, "values")[2] for item in selected}
        self.files = [path for path in self.files if str(path) not in selected_paths]
        for item in selected:
            path = self.tree.item(item, "values")[2]
            self.item_for_path.pop(str(Path(path).resolve()), None)
            self.tree.delete(item)
        self._refresh_file_count()
        self.update_preview()

    def clear_files(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.files.clear()
        self.item_for_path.clear()
        self._refresh_file_count()
        self.update_preview()

    def pick_font(self) -> None:
        name = filedialog.askopenfilename(title="选择字体文件", filetypes=[("字体", "*.ttf *.ttc *.otf"), ("所有文件", "*.*")])
        if name:
            self.font_path_var.set(name)
            self.update_preview()

    def pick_logo(self) -> None:
        name = filedialog.askopenfilename(
            title="选择 Logo 图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("所有文件", "*.*")],
        )
        if name:
            self.logo_path_var.set(name)
            self.update_preview()

    def clear_logo(self) -> None:
        self.logo_path_var.set("")
        self.update_preview()

    def pick_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_dir_var.set(folder)

    def open_output_dir(self) -> None:
        folder = Path(self.output_dir_var.get().strip() or Path.cwd() / "output")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"无法打开输出目录：{exc}")

    def pick_ffmpeg(self) -> None:
        name = filedialog.askopenfilename(title="选择 ffmpeg.exe", filetypes=[("FFmpeg", "ffmpeg.exe"), ("EXE", "*.exe"), ("所有文件", "*.*")])
        if name:
            self.ffmpeg_path_var.set(name)
            self._refresh_ffmpeg_badge()
            self.update_preview()

    def update_preview(self) -> None:
        if self.preview_after_id:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None

        selected = self.tree.selection()
        if not selected:
            self.preview_token += 1
            self.preview_image = None
            self.preview_photo = None
            self.preview_message = "选择或拖入一个图片/视频后，可在这里查看更大的水印预览"
            self._reset_preview_view()
            return

        path = Path(self.tree.item(selected[0], "values")[2])
        options = self._watermark_options()
        ffmpeg_path = self.ffmpeg_path_var.get().strip()
        max_size = self._preview_max_size()
        self.preview_token += 1
        token = self.preview_token
        self.preview_image = None
        self.preview_photo = None
        self.preview_message = "正在生成预览..."
        self._reset_preview_view()
        self.preview_after_id = self.after(220, lambda: self._start_preview_worker(token, path, options, ffmpeg_path, max_size))

    def _preview_max_size(self) -> tuple[int, int]:
        width = self.preview_canvas.winfo_width()
        height = self.preview_canvas.winfo_height()
        if width < 300 or height < 220:
            return 1600, 1200
        return min(2600, max(900, width * 3)), min(2200, max(900, height * 3))

    def _start_preview_worker(self, token: int, path: Path, options: WatermarkOptions, ffmpeg_path: str, max_size: tuple[int, int]) -> None:
        self.preview_after_id = None
        thread = threading.Thread(target=self._preview_worker, args=(token, path, options, ffmpeg_path, max_size), daemon=True)
        thread.start()

    def _preview_worker(self, token: int, path: Path, options: WatermarkOptions, ffmpeg_path: str, max_size: tuple[int, int]) -> None:
        try:
            if is_image_file(path):
                preview = make_preview_image(path, options, max_size)
            elif is_video_file(path):
                preview = make_video_preview_image(path, ffmpeg_path, options, max_size)
                if preview is None:
                    self.ui_queue.put(("preview", (token, None, "视频预览需要可用的 FFmpeg")))
                    return
            else:
                return
        except Exception as exc:
            self.ui_queue.put(("preview", (token, None, f"预览失败：{exc}")))
            return

        self.ui_queue.put(("preview", (token, preview, "")))

    def start_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "正在处理中，请等待当前任务完成。")
            return
        if not self.files:
            messagebox.showwarning(APP_TITLE, "请先添加图片或视频文件。")
            return
        if not self.text_var.get().strip() and not self.logo_path_var.get().strip():
            messagebox.showwarning(APP_TITLE, "请填写水印文字，或选择一个 Logo 图片。")
            return

        options = self._watermark_options()
        ffmpeg_path = self.ffmpeg_path_var.get().strip()
        self.cancel_event.clear()
        self.progress_var.set(0)
        self.status_var.set("开始处理")
        self.log_list.delete(0, END)
        self._save_settings()
        self._append_log("开始批量处理")
        if hasattr(self, "start_button"):
            self.start_button.configure(state="disabled")
        if hasattr(self, "cancel_button"):
            self.cancel_button.configure(state="normal")
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            values[1] = "待处理"
            self.tree.item(item, values=values)

        self.worker = threading.Thread(target=self._process_worker, args=(list(self.files), options, ffmpeg_path), daemon=True)
        self.worker.start()

    def cancel_processing(self) -> None:
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.status_var.set("正在取消，请稍候...")
            self._append_log("已请求取消处理")
            if hasattr(self, "cancel_button"):
                self.cancel_button.configure(state="disabled")
        else:
            self._append_log("当前没有正在运行的处理任务")

    def _process_worker(self, files: list[Path], options: WatermarkOptions, ffmpeg_path: str) -> None:
        total = len(files)
        completed = 0
        failures = 0
        cancelled = False
        for index, path in enumerate(files, start=1):
            if self.cancel_event.is_set():
                cancelled = True
                break
            self.ui_queue.put(("status", (path, "处理中")))
            self.ui_queue.put(("message", f"正在处理 {index}/{total}: {path.name}"))
            try:
                result = process_file(
                    path,
                    options,
                    ffmpeg_path,
                    lambda message: self.ui_queue.put(("message", message)),
                    self.cancel_event.is_set,
                )
                self.ui_queue.put(("status", (path, "完成")))
                self.ui_queue.put(("message", f"已输出：{result.output_path} | {result.message}"))
            except Exception as exc:
                if self.cancel_event.is_set() or str(exc) == "已取消":
                    cancelled = True
                    self.ui_queue.put(("status", (path, "已取消")))
                    self.ui_queue.put(("message", f"{path.name} 已取消"))
                    completed += 1
                    self.ui_queue.put(("progress", completed / total * 100))
                    break
                else:
                    failures += 1
                    self.ui_queue.put(("status", (path, "失败")))
                    self.ui_queue.put(("message", f"{path.name} 失败：{exc}"))
            completed += 1
            self.ui_queue.put(("progress", completed / total * 100))
        self.ui_queue.put(("done", (completed, failures, cancelled)))

    def _drain_queue(self) -> None:
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()
                if event == "status":
                    path, status = payload
                    item_id = self.item_for_path.get(str(Path(path).resolve()))
                    if item_id:
                        values = list(self.tree.item(item_id, "values"))
                        values[1] = status
                        self.tree.item(item_id, values=values)
                elif event == "message":
                    self.status_var.set(str(payload))
                    self._append_log(str(payload))
                elif event == "progress":
                    self.progress_var.set(float(payload))
                elif event == "preview":
                    token, image, message = payload
                    if token != self.preview_token:
                        continue
                    if image is None:
                        self.preview_image = None
                        self.preview_photo = None
                        self.preview_message = str(message)
                        self._reset_preview_view()
                    else:
                        self.preview_image = image.convert("RGB")
                        self.preview_message = ""
                        self._reset_preview_view()
                elif event == "done":
                    completed, failures, cancelled = payload
                    if cancelled:
                        message = f"处理已取消：已处理 {completed} 个，失败 {failures} 个"
                    else:
                        message = f"处理完成：{completed} 个，失败 {failures} 个"
                    self.status_var.set(message)
                    self._append_log(message)
                    if hasattr(self, "start_button"):
                        self.start_button.configure(state="normal")
                    if hasattr(self, "cancel_button"):
                        self.cancel_button.configure(state="disabled")
                    self._refresh_ffmpeg_badge()
                    if self.open_after_var.get() and completed:
                        self.open_output_dir()
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _append_log(self, message: str) -> None:
        if not hasattr(self, "log_list"):
            return
        self.log_list.insert(END, message)
        self.log_list.see(END)
        if self.log_list.size() > 300:
            self.log_list.delete(0, self.log_list.size() - 300)

    def export_log(self) -> None:
        if not hasattr(self, "log_list") or self.log_list.size() == 0:
            messagebox.showinfo(APP_TITLE, "当前没有可导出的日志。")
            return

        default_path = Path(self.output_dir_var.get().strip() or Path.cwd() / "output") / "watermark_log.txt"
        name = filedialog.asksaveasfilename(
            title="导出处理日志",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not name:
            return

        lines = [self.log_list.get(index) for index in range(self.log_list.size())]
        try:
            Path(name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._append_log(f"日志已导出：{name}")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"日志导出失败：{exc}")

    def _refresh_file_count(self) -> None:
        image_count = sum(1 for path in self.files if is_image_file(path))
        video_count = sum(1 for path in self.files if is_video_file(path))
        self.file_count_label.configure(text=f"已选择 {len(self.files)} 个文件，图片 {image_count}，视频 {video_count}")

    def _refresh_ffmpeg_badge(self) -> None:
        colors = self._colors()
        path = find_ffmpeg(self.ffmpeg_path_var.get().strip())
        if path:
            self.ffmpeg_path_var.set(path)
            encoders = available_video_encoders(path)
            gpu_names = []
            if "h264_nvenc" in encoders:
                gpu_names.append("NVENC")
            if "h264_qsv" in encoders:
                gpu_names.append("QSV")
            if "h264_amf" in encoders:
                gpu_names.append("AMF")
            suffix = f" | GPU: {', '.join(gpu_names)}" if gpu_names else " | GPU: 未检测到"
            self.ffmpeg_badge.configure(text=f"FFmpeg 已就绪: {Path(path).name}{suffix}", bg=colors["badge_ok_bg"], fg=colors["badge_ok_fg"])
        else:
            self.ffmpeg_badge.configure(text="FFmpeg 未找到：图片可用，视频需选择 ffmpeg.exe", bg=colors["badge_warn_bg"], fg=colors["badge_warn_fg"])

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_TITLE, "任务仍在处理中，要取消并退出吗？"):
                return
            self.cancel_event.set()

        self._save_settings()
        if os.name == "nt" and self._drop_old_wndprocs:
            try:
                user32 = ctypes.windll.user32
                set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
                set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                set_window_long_ptr.restype = ctypes.c_void_p
                for hwnd, old_proc in list(self._drop_old_wndprocs.items()):
                    set_window_long_ptr(hwnd, -4, old_proc)
            except Exception:
                pass
        self.destroy()


def main() -> None:
    app = WatermarkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
