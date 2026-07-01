from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat
try:
    from PIL import features
except Exception:
    features = None

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:
    arabic_reshaper = None
    get_display = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".m4v", ".webm"}
HAVE_RAQM = bool(features and features.check("raqm"))
DEFAULT_CJK_FONT_NAMES = {"msyh.ttc", "msyhbd.ttc", "simsun.ttc", "simhei.ttf", "msyh.ttf"}
ARABIC_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\tahoma.ttf"),
    Path(r"C:\Windows\Fonts\times.ttf"),
]
ARABIC_RESHAPER = (
    arabic_reshaper.ArabicReshaper(
        configuration={
            "delete_harakat": False,
            "shift_harakat_position": True,
        }
    )
    if arabic_reshaper
    else None
)

POSITION_LABELS = {
    "smart_corner": "智能角落",
    "top_left": "左上角",
    "top_right": "右上角",
    "bottom_left": "左下角",
    "bottom_right": "右下角",
    "center": "居中",
    "tile": "平铺",
}

STYLE_LABELS = {
    "smart": "智能清晰",
    "light": "白字黑描边",
    "dark": "黑字白描边",
}

VIDEO_ENCODER_LABELS = {
    "auto": "自动选择（优先 GPU）",
    "cpu": "CPU H.264（兼容）",
    "nvidia": "NVIDIA NVENC",
    "intel": "Intel Quick Sync",
    "amd": "AMD AMF",
}

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def _hidden_subprocess_kwargs() -> dict[str, int]:
    if CREATE_NO_WINDOW:
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


@dataclass
class WatermarkOptions:
    text: str = "AI-Generated (Audio & Visuals)"
    font_path: str = ""
    font_size: int = 32
    auto_font_size: bool = True
    opacity: int = 92
    margin: int = 28
    position: str = "smart_corner"
    style: str = "smart"
    use_panel: bool = True
    text_color_mode: str = "smart"
    text_color: str = "#FFFFFF"
    stroke_enabled: bool = True
    stroke_color_mode: str = "smart"
    stroke_color: str = "#000000"
    image_quality: int = 95
    output_dir: str = ""
    video_encoder: str = "cpu"
    logo_path: str = ""
    logo_scale: int = 12
    logo_gap: int = 10


@dataclass
class ProcessResult:
    input_path: Path
    output_path: Path
    media_type: str
    message: str = "完成"


@dataclass
class RenderStyle:
    fill: tuple[int, int, int, int]
    stroke: tuple[int, int, int, int]
    shadow: tuple[int, int, int, int]
    panel: tuple[int, int, int, int]
    position: str
    stroke_width: int
    shadow_offset: int
    panel_padding: int


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def iter_media_files(folder: str | Path) -> Iterable[Path]:
    folder_path = Path(folder)
    for path in folder_path.rglob("*"):
        if path.is_file() and (is_image_file(path) or is_video_file(path)):
            yield path


def default_font_path() -> str:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _contains_arabic(text: str) -> bool:
    return any(
        0x0600 <= ord(char) <= 0x06FF
        or 0x0750 <= ord(char) <= 0x077F
        or 0x08A0 <= ord(char) <= 0x08FF
        or 0xFB50 <= ord(char) <= 0xFDFF
        or 0xFE70 <= ord(char) <= 0xFEFF
        for char in text
    )


def _is_default_cjk_font(font_path: str) -> bool:
    if not font_path:
        return False
    return Path(font_path).name.lower() in DEFAULT_CJK_FONT_NAMES


def _font_candidates_for_text(text: str, preferred_path: str) -> list[Path]:
    preferred = Path(preferred_path) if preferred_path else None
    candidates: list[Path] = []
    if _contains_arabic(text):
        if preferred and not _is_default_cjk_font(str(preferred)):
            candidates.append(preferred)
        candidates.extend(ARABIC_FONT_CANDIDATES)
        if preferred and _is_default_cjk_font(str(preferred)):
            candidates.append(preferred)
    else:
        if preferred:
            candidates.append(preferred)
        default_path = default_font_path()
        if default_path:
            candidates.append(Path(default_path))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _layout_engine():
    if HAVE_RAQM and hasattr(ImageFont, "Layout"):
        return ImageFont.Layout.RAQM
    return None


def _prepare_text_for_rendering(text: str) -> tuple[str, dict[str, str]]:
    if not text or not _contains_arabic(text):
        return text, {}
    if HAVE_RAQM:
        return text, {"direction": "rtl", "language": "ar"}
    if ARABIC_RESHAPER and get_display:
        try:
            reshaped = ARABIC_RESHAPER.reshape(text)
            return get_display(reshaped), {}
        except Exception:
            return text, {}
    return text, {}


def find_ffmpeg(preferred_path: str = "") -> str:
    if preferred_path and Path(preferred_path).is_file():
        return preferred_path

    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    local_candidates = [
        app_dir / "ffmpeg.exe",
        Path.cwd() / "ffmpeg.exe",
        Path(__file__).resolve().parent / "ffmpeg.exe",
        Path(r"C:\Program Files\ShareX\ffmpeg.exe"),
        Path(r"C:\Program Files\BlueStacks_msi5\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)

    detected = shutil.which("ffmpeg")
    return detected or ""


def available_video_encoders(ffmpeg_path: str) -> set[str]:
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        return set()

    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
            timeout=12,
            **_hidden_subprocess_kwargs(),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return set()

    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return names


def resolve_video_encoder(ffmpeg_path: str, choice: str) -> tuple[str, list[str], str]:
    available = available_video_encoders(ffmpeg_path)
    requested = choice if choice in VIDEO_ENCODER_LABELS else "cpu"

    candidates: list[tuple[str, str, list[str]]] = []
    if requested == "auto":
        candidates = [
            ("h264_nvenc", "NVIDIA NVENC", ["-cq", "19", "-preset", "medium"]),
            ("h264_qsv", "Intel Quick Sync", ["-global_quality", "20"]),
            ("h264_amf", "AMD AMF", ["-quality", "quality", "-qp_i", "19", "-qp_p", "21"]),
            ("libx264", "CPU H.264", ["-crf", "18", "-preset", "medium"]),
        ]
    elif requested == "nvidia":
        candidates = [("h264_nvenc", "NVIDIA NVENC", ["-cq", "19", "-preset", "medium"])]
    elif requested == "intel":
        candidates = [("h264_qsv", "Intel Quick Sync", ["-global_quality", "20"])]
    elif requested == "amd":
        candidates = [("h264_amf", "AMD AMF", ["-quality", "quality", "-qp_i", "19", "-qp_p", "21"])]
    else:
        candidates = [("libx264", "CPU H.264", ["-crf", "18", "-preset", "medium"])]

    for encoder_name, label, args in candidates:
        if encoder_name in available:
            return encoder_name, args, label

    if "libx264" in available or requested == "cpu":
        return "libx264", ["-crf", "18", "-preset", "medium"], "CPU H.264"

    return "mpeg4", ["-q:v", "3"], "MPEG-4"


def build_output_path(input_path: str | Path, options: WatermarkOptions) -> Path:
    source = Path(input_path)
    output_dir = Path(options.output_dir) if options.output_dir else source.parent / "watermarked"
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    if is_video_file(source) and suffix in {".wmv", ".webm"}:
        suffix = ".mp4"

    base = output_dir / f"{source.stem}_watermarked{suffix}"
    if not base.exists():
        return base

    for index in range(2, 10000):
        candidate = output_dir / f"{source.stem}_watermarked_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("无法生成唯一的输出文件名。")


def _effective_font_size(image_size: tuple[int, int], options: WatermarkOptions) -> int:
    if not options.auto_font_size:
        return max(8, int(options.font_size))

    width, height = image_size
    short_edge = max(1, min(width, height))
    calculated = int(short_edge * 0.048)
    return max(18, min(96, calculated))


def _load_font(image_size: tuple[int, int], options: WatermarkOptions, text: str = "") -> ImageFont.FreeTypeFont:
    font_size = _effective_font_size(image_size, options)
    layout_engine = _layout_engine()
    for font_path in _font_candidates_for_text(text, options.font_path):
        if not font_path.exists():
            continue
        if layout_engine is not None:
            return ImageFont.truetype(font_path, font_size, layout_engine=layout_engine)
        return ImageFont.truetype(font_path, font_size)
    return ImageFont.load_default(size=font_size)


def _measure_text(
    text: str,
    font: ImageFont.ImageFont,
    stroke_width: int = 0,
    text_kwargs: Optional[dict[str, str]] = None,
) -> tuple[int, int]:
    if not text:
        return 0, 0
    scratch = Image.new("RGBA", (8, 8))
    draw = ImageDraw.Draw(scratch)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width, **(text_kwargs or {}))
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def _load_logo(image_size: tuple[int, int], options: WatermarkOptions) -> Optional[Image.Image]:
    logo_path = (options.logo_path or "").strip()
    if not logo_path:
        return None

    path = Path(logo_path)
    if not path.is_file():
        return None

    with Image.open(path) as logo:
        logo_image = ImageOps.exif_transpose(logo).convert("RGBA")

    short_edge = max(1, min(image_size))
    max_height = max(18, int(short_edge * max(2, min(60, options.logo_scale)) / 100))
    max_width = max(18, int(image_size[0] * 0.32))
    logo_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    opacity = max(1, min(100, int(options.opacity))) / 100
    if opacity < 1:
        alpha = logo_image.getchannel("A")
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        logo_image.putalpha(alpha)

    return logo_image


def _combined_mark_size(
    text_size: tuple[int, int],
    logo: Optional[Image.Image],
    options: WatermarkOptions,
) -> tuple[int, int, int]:
    gap = max(0, int(options.logo_gap)) if logo and text_size[0] else 0
    logo_width = logo.width if logo else 0
    logo_height = logo.height if logo else 0
    width = logo_width + gap + text_size[0]
    height = max(logo_height, text_size[1])
    return max(1, width), max(1, height), gap


def _box_for_position(
    image_size: tuple[int, int],
    content_size: tuple[int, int],
    margin: int,
    position: str,
) -> tuple[int, int, int, int]:
    width, height = image_size
    content_width, content_height = content_size
    margin = max(0, margin)

    if position == "top_left":
        x, y = margin, margin
    elif position == "top_right":
        x, y = width - content_width - margin, margin
    elif position == "bottom_left":
        x, y = margin, height - content_height - margin
    elif position == "center":
        x, y = (width - content_width) // 2, (height - content_height) // 2
    else:
        x, y = width - content_width - margin, height - content_height - margin

    x = max(0, min(width - content_width, x))
    y = max(0, min(height - content_height, y))
    return x, y, x + content_width, y + content_height


def _region_stats(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[float, float, float]:
    crop = image.crop(box).convert("RGB")
    crop.thumbnail((96, 96))

    gray = crop.convert("L")
    lum = ImageStat.Stat(gray).mean[0]
    contrast = ImageStat.Stat(gray).stddev[0]

    saturation_img = crop.convert("HSV").getchannel("S")
    saturation = ImageStat.Stat(saturation_img).mean[0]
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_level = ImageStat.Stat(edges).mean[0]
    visual_noise = contrast * 0.65 + saturation * 0.18 + edge_level * 0.6
    return lum, contrast, visual_noise


def _parse_hex_color(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        return fallback
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return fallback


def _pick_smart_position(
    image: Image.Image,
    content_size: tuple[int, int],
    margin: int,
) -> str:
    candidates = ["bottom_right", "bottom_left", "top_right", "top_left"]
    best_position = "bottom_right"
    best_score = math.inf

    for position in candidates:
        box = _box_for_position(image.size, content_size, margin, position)
        lum, _contrast, noise = _region_stats(image, box)
        edge_bias = 0 if position.startswith("bottom") else 8
        midtone_penalty = max(0, 55 - abs(lum - 128)) * 0.35
        score = noise + edge_bias + midtone_penalty
        if score < best_score:
            best_score = score
            best_position = position

    return best_position


def _choose_style(image: Image.Image, box: tuple[int, int, int, int], options: WatermarkOptions) -> tuple[str, float]:
    if options.style in {"light", "dark"}:
        lum, _contrast, _noise = _region_stats(image, box)
        return options.style, lum

    lum, _contrast, _noise = _region_stats(image, box)
    style = "light" if lum < 145 else "dark"
    return style, lum


def _build_render_style(
    image: Image.Image,
    text_size: tuple[int, int],
    options: WatermarkOptions,
    font_size: int,
) -> RenderStyle:
    opacity = max(1, min(100, int(options.opacity)))
    alpha = int(255 * opacity / 100)
    stroke_width = max(1, int(font_size * 0.08)) if options.stroke_enabled else 0
    shadow_offset = max(1, int(font_size * 0.07)) if options.stroke_enabled else 0
    panel_padding = max(6, int(font_size * 0.34))
    content_size = (
        text_size[0] + panel_padding * 2,
        text_size[1] + panel_padding * 2,
    )

    position = options.position
    if position == "smart_corner":
        position = _pick_smart_position(image, content_size, options.margin)
    if position == "tile":
        position = "tile"

    if position == "tile":
        sample_box = (0, 0, image.width, image.height)
    else:
        sample_box = _box_for_position(image.size, content_size, options.margin, position)

    style_name, _lum = _choose_style(image, sample_box, options)
    if style_name == "light":
        fill = (255, 255, 255, alpha)
        stroke = (0, 0, 0, int(alpha * 0.72))
        shadow = (0, 0, 0, int(alpha * 0.42))
        panel = (0, 0, 0, int(alpha * 0.28))
    else:
        fill = (18, 22, 27, alpha)
        stroke = (255, 255, 255, int(alpha * 0.86))
        shadow = (255, 255, 255, int(alpha * 0.28))
        panel = (255, 255, 255, int(alpha * 0.34))

    if options.text_color_mode == "custom":
        fill_rgb = _parse_hex_color(options.text_color, fill[:3])
        fill = (*fill_rgb, alpha)

    if not options.stroke_enabled:
        stroke = (0, 0, 0, 0)
        shadow = (0, 0, 0, 0)
    elif options.stroke_color_mode == "custom":
        stroke_rgb = _parse_hex_color(options.stroke_color, stroke[:3])
        stroke = (*stroke_rgb, int(alpha * 0.9))
        shadow = (*stroke_rgb, int(alpha * 0.38))

    return RenderStyle(
        fill=fill,
        stroke=stroke,
        shadow=shadow,
        panel=panel,
        position=position,
        stroke_width=stroke_width,
        shadow_offset=shadow_offset,
        panel_padding=panel_padding,
    )


def _draw_single_watermark(
    base: Image.Image,
    overlay: Image.Image,
    text: str,
    logo: Optional[Image.Image],
    font: ImageFont.ImageFont,
    text_size: tuple[int, int],
    style: RenderStyle,
    options: WatermarkOptions,
    text_kwargs: Optional[dict[str, str]] = None,
) -> None:
    draw = ImageDraw.Draw(overlay)
    mark_width, mark_height, gap = _combined_mark_size(text_size, logo, options)
    content_size = (
        mark_width + style.panel_padding * 2,
        mark_height + style.panel_padding * 2,
    )
    box = _box_for_position(base.size, content_size, options.margin, style.position)
    x1, y1, x2, y2 = box
    cursor_x = x1 + style.panel_padding
    content_y = y1 + style.panel_padding

    if options.use_panel:
        radius = max(5, int(min(content_size) * 0.2))
        draw.rounded_rectangle(box, radius=radius, fill=style.panel)

    if logo is not None:
        logo_y = content_y + (mark_height - logo.height) // 2
        shadow_alpha = logo.getchannel("A").filter(ImageFilter.GaussianBlur(max(2, style.shadow_offset)))
        shadow = Image.new("RGBA", logo.size, style.shadow)
        shadow.putalpha(shadow_alpha)
        overlay.alpha_composite(shadow, (cursor_x + style.shadow_offset, logo_y + style.shadow_offset))
        overlay.alpha_composite(logo, (cursor_x, logo_y))
        cursor_x += logo.width + gap

    if text:
        text_y = content_y + (mark_height - text_size[1]) // 2
        if style.shadow[3] > 0 and style.shadow_offset > 0:
            draw.text(
                (cursor_x + style.shadow_offset, text_y + style.shadow_offset),
                text,
                font=font,
                fill=style.shadow,
                stroke_width=style.stroke_width,
                stroke_fill=style.shadow,
                **(text_kwargs or {}),
            )
        draw.text(
            (cursor_x, text_y),
            text,
            font=font,
            fill=style.fill,
            stroke_width=style.stroke_width,
            stroke_fill=style.stroke,
            **(text_kwargs or {}),
        )


def _draw_tiled_watermark(
    base: Image.Image,
    overlay: Image.Image,
    text: str,
    logo: Optional[Image.Image],
    font: ImageFont.ImageFont,
    text_size: tuple[int, int],
    style: RenderStyle,
    options: WatermarkOptions,
    text_kwargs: Optional[dict[str, str]] = None,
) -> None:
    mark_width, mark_height, gap = _combined_mark_size(text_size, logo, options)
    tile_width = max(260, mark_width + style.panel_padding * 5)
    tile_height = max(150, mark_height + style.panel_padding * 5)
    tile = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)
    cursor_x = style.panel_padding
    content_y = (tile_height - mark_height) // 2

    if logo is not None:
        logo_y = content_y + (mark_height - logo.height) // 2
        logo_copy = logo.copy()
        alpha = logo_copy.getchannel("A")
        alpha = ImageEnhance.Brightness(alpha).enhance(0.42)
        logo_copy.putalpha(alpha)
        tile.alpha_composite(logo_copy, (cursor_x, logo_y))
        cursor_x += logo.width + gap

    fill = (*style.fill[:3], max(26, int(style.fill[3] * 0.38)))
    stroke_width = max(1, style.stroke_width) if style.stroke_width > 0 and style.stroke[3] > 0 else 0
    stroke = (*style.stroke[:3], max(18, int(style.stroke[3] * 0.35))) if stroke_width else (0, 0, 0, 0)
    if text:
        text_y = content_y + (mark_height - text_size[1]) // 2
        tile_draw.text(
            (cursor_x, text_y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke,
            **(text_kwargs or {}),
        )
    tile = tile.rotate(-24, expand=True, resample=Image.Resampling.BICUBIC)

    for y_pos in range(-tile.height, base.height + tile.height, tile_height):
        for x_pos in range(-tile.width, base.width + tile.width, tile_width):
            overlay.alpha_composite(tile, (x_pos, y_pos))


def render_watermark_overlay(image: Image.Image, options: WatermarkOptions) -> Image.Image:
    text = (options.text or "").strip()
    oriented = ImageOps.exif_transpose(image)
    base = oriented.convert("RGBA")
    logo = _load_logo(base.size, options)
    if not text and logo is None:
        raise ValueError("水印文字和 Logo 至少需要填写一个。")

    render_text, text_kwargs = _prepare_text_for_rendering(text)
    font = _load_font(base.size, options, text)
    font_size = getattr(font, "size", _effective_font_size(base.size, options))
    probe_stroke = max(1, int(font_size * 0.08)) if options.stroke_enabled else 0
    text_size = _measure_text(render_text, font, probe_stroke, text_kwargs)
    mark_width, mark_height, _gap = _combined_mark_size(text_size, logo, options)
    style = _build_render_style(base, (mark_width, mark_height), options, font_size)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    if style.position == "tile":
        _draw_tiled_watermark(base, overlay, render_text, logo, font, text_size, style, options, text_kwargs)
    else:
        _draw_single_watermark(base, overlay, render_text, logo, font, text_size, style, options, text_kwargs)

    return overlay


def render_watermark_on_image(image: Image.Image, options: WatermarkOptions) -> Image.Image:
    oriented = ImageOps.exif_transpose(image)
    base = oriented.convert("RGBA")
    overlay = render_watermark_overlay(oriented, options)

    return Image.alpha_composite(base, overlay)


def watermark_image(input_path: str | Path, options: WatermarkOptions) -> ProcessResult:
    source = Path(input_path)
    output_path = build_output_path(source, options)

    with Image.open(source) as image:
        rendered = render_watermark_on_image(image, options)

        ext = output_path.suffix.lower()
        if ext in {".jpg", ".jpeg", ".bmp"}:
            rendered = rendered.convert("RGB")
        save_kwargs: dict[str, object] = {}
        if ext in {".jpg", ".jpeg", ".webp"}:
            save_kwargs["quality"] = max(1, min(100, int(options.image_quality)))
        if ext in {".jpg", ".jpeg"}:
            save_kwargs["subsampling"] = 0
            save_kwargs["optimize"] = True
        rendered.save(output_path, **save_kwargs)

    return ProcessResult(source, output_path, "image")


def make_preview_image(input_path: str | Path, options: WatermarkOptions, max_size: tuple[int, int]) -> Image.Image:
    with Image.open(input_path) as image:
        rendered = render_watermark_on_image(image, options)
    rendered.thumbnail(max_size, Image.Resampling.LANCZOS)
    return rendered.convert("RGB")


def _ffmpeg_filter_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _ffmpeg_font_path(font_path: str) -> str:
    resolved = font_path or default_font_path()
    return resolved.replace("\\", "/").replace(":", "\\:")


def _ffmpeg_position_expr(position: str, margin: int) -> tuple[str, str]:
    margin = max(0, margin)
    if position == "top_left":
        return str(margin), str(margin)
    if position == "top_right":
        return f"w-text_w-{margin}", str(margin)
    if position == "bottom_left":
        return str(margin), f"h-text_h-{margin}"
    if position == "center":
        return "(w-text_w)/2", "(h-text_h)/2"
    return f"w-text_w-{margin}", f"h-text_h-{margin}"


def extract_video_frame(input_path: str | Path, ffmpeg_path: str) -> Optional[Image.Image]:
    if not ffmpeg_path:
        return None
    with tempfile.TemporaryDirectory(prefix="watermark_preview_") as tmp:
        frame_path = Path(tmp) / "frame.jpg"
        attempts = [
            ["-ss", "00:00:01"],
            [],
        ]
        for seek_args in attempts:
            if frame_path.exists():
                try:
                    frame_path.unlink()
                except OSError:
                    pass
            command = [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                *seek_args,
                "-i",
                str(input_path),
                "-frames:v",
                "1",
                str(frame_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    **_hidden_subprocess_kwargs(),
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                continue
            if frame_path.exists():
                break

        if not frame_path.exists():
            return None
        with Image.open(frame_path) as image:
            return image.convert("RGB").copy()


def make_video_preview_image(
    input_path: str | Path,
    ffmpeg_path: str,
    options: WatermarkOptions,
    max_size: tuple[int, int],
) -> Optional[Image.Image]:
    frame = extract_video_frame(input_path, ffmpeg_path)
    if frame is None:
        return None
    rendered = render_watermark_on_image(frame, options)
    rendered.thumbnail(max_size, Image.Resampling.LANCZOS)
    return rendered.convert("RGB")


def _analyze_video_style(
    input_path: str | Path,
    ffmpeg_path: str,
    options: WatermarkOptions,
) -> tuple[str, str, int]:
    frame = extract_video_frame(input_path, ffmpeg_path)
    if frame is None:
        position = "bottom_right" if options.position == "smart_corner" else options.position
        font_size = max(18, int(options.font_size))
        style = options.style if options.style in {"light", "dark"} else "light"
        return position, style, font_size

    size_options = WatermarkOptions(**{**options.__dict__})
    render_text, text_kwargs = _prepare_text_for_rendering(options.text)
    font = _load_font(frame.size, size_options, options.text)
    font_size = getattr(font, "size", _effective_font_size(frame.size, size_options))
    probe_stroke = max(1, int(font_size * 0.08)) if size_options.stroke_enabled else 0
    text_size = _measure_text(render_text, font, probe_stroke, text_kwargs)
    render_style = _build_render_style(frame.convert("RGBA"), text_size, size_options, font_size)
    style_name = "light" if render_style.fill[:3] == (255, 255, 255) else "dark"
    return render_style.position, style_name, font_size


def watermark_video(
    input_path: str | Path,
    options: WatermarkOptions,
    ffmpeg_path: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> ProcessResult:
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        raise RuntimeError("没有找到 FFmpeg，无法处理视频。请在界面右侧选择 ffmpeg.exe。")

    source = Path(input_path)
    output_path = build_output_path(source, options)

    if progress_callback:
        progress_callback("正在分析视频首帧并生成透明水印层...")

    frame = extract_video_frame(source, ffmpeg_path)
    if frame is None:
        raise RuntimeError("无法读取视频首帧，请确认视频文件可以正常播放。")

    with tempfile.TemporaryDirectory(prefix="watermark_video_") as tmp:
        overlay_path = Path(tmp) / "watermark_overlay.png"
        overlay = render_watermark_overlay(frame, options)
        overlay.save(overlay_path)

        encoder, encoder_args, encoder_label = resolve_video_encoder(ffmpeg_path, options.video_encoder)

        def build_command(active_encoder: str, active_args: list[str]) -> list[str]:
            command = [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-loop",
                "1",
                "-i",
                str(overlay_path),
                "-filter_complex",
                "[0:v][1:v]overlay=0:0:format=auto:shortest=1,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[v]",
                "-map",
                "[v]",
                "-map",
                "0:a?",
                "-c:v",
                active_encoder,
                *active_args,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-shortest",
            ]
            if output_path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
                command.extend(["-movflags", "+faststart"])
            command.append(str(output_path))
            return command

        def run_command(command: list[str]) -> None:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **_hidden_subprocess_kwargs(),
            )
            while process.poll() is None:
                if cancel_callback and cancel_callback():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except OSError:
                            pass
                    raise RuntimeError("已取消")
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass

            stdout, stderr = process.communicate()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)

        if progress_callback:
            progress_callback(f"正在调用 FFmpeg 处理视频，编码器：{encoder_label}")

        try:
            run_command(build_command(encoder, encoder_args))
        except subprocess.CalledProcessError as exc:
            if encoder != "libx264":
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except OSError:
                        pass
                if progress_callback:
                    progress_callback(f"{encoder_label} 启动失败，自动回退到 CPU H.264...")
                try:
                    run_command(build_command("libx264", ["-crf", "18", "-preset", "medium"]))
                    return ProcessResult(source, output_path, "video", f"完成（{encoder_label} 失败，已回退 CPU）")
                except subprocess.CalledProcessError as fallback_exc:
                    detail = (fallback_exc.stderr or fallback_exc.stdout or "").strip()
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except OSError:
                            pass
                    raise RuntimeError(f"FFmpeg 处理失败：{detail[-900:]}") from fallback_exc

            detail = (exc.stderr or exc.stdout or "").strip()
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"FFmpeg 处理失败：{detail[-900:]}") from exc

    return ProcessResult(source, output_path, "video", f"完成（{encoder_label}）")


def process_file(
    input_path: str | Path,
    options: WatermarkOptions,
    ffmpeg_path: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> ProcessResult:
    source = Path(input_path)
    if is_image_file(source):
        if cancel_callback and cancel_callback():
            raise RuntimeError("已取消")
        return watermark_image(source, options)
    if is_video_file(source):
        return watermark_video(source, options, ffmpeg_path, progress_callback, cancel_callback)
    raise ValueError(f"不支持的文件类型：{source.suffix}")
