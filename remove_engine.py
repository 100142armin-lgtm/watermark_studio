from __future__ import annotations

import math
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

try:
    import numpy as np
except Exception:
    np = None

from watermark_engine import (
    ProcessResult,
    WatermarkOptions,
    _ffmpeg_filter_escape,
    _hidden_subprocess_kwargs,
    extract_video_frame,
    is_image_file,
    is_video_file,
    resolve_video_encoder,
)


Region = tuple[float, float, float, float]
VIDEO_NO_PROGRESS_TIMEOUT = 180.0


@dataclass
class RemovalOptions:
    region: Region | None = None
    regions: list[Region] | None = None
    output_dir: str = ""
    image_quality: int = 95
    video_encoder: str = "auto"
    smart_mask: bool = True
    mask_sensitivity: int = 6
    feather: int = 16
    expand: int = 4
    strength: int = 3


def has_valid_region(region: Region | None) -> bool:
    if region is None:
        return False
    x1, y1, x2, y2 = _sorted_region(region)
    return (x2 - x1) >= 0.004 and (y2 - y1) >= 0.004


def valid_regions(regions: list[Region] | tuple[Region, ...] | None) -> list[Region]:
    if not regions:
        return []
    cleaned: list[Region] = []
    for region in regions:
        if has_valid_region(region):
            cleaned.append(_sorted_region(region))
    return cleaned


def removal_regions(options: RemovalOptions) -> list[Region]:
    regions = valid_regions(options.regions)
    if regions:
        return regions
    if has_valid_region(options.region):
        return [_sorted_region(options.region)]
    return []


def _sorted_region(region: Region) -> Region:
    x1, y1, x2, y2 = region
    left, right = sorted((float(x1), float(x2)))
    top, bottom = sorted((float(y1), float(y2)))
    return (
        max(0.0, min(1.0, left)),
        max(0.0, min(1.0, top)),
        max(0.0, min(1.0, right)),
        max(0.0, min(1.0, bottom)),
    )


def normalized_region_to_box(
    image_size: tuple[int, int],
    region: Region,
    expand: int = 0,
) -> tuple[int, int, int, int]:
    width, height = image_size
    x1, y1, x2, y2 = _sorted_region(region)
    left = int(round(x1 * width)) - expand
    top = int(round(y1 * height)) - expand
    right = int(round(x2 * width)) + expand
    bottom = int(round(y2 * height)) + expand

    left = max(0, min(width - 1, left))
    top = max(0, min(height - 1, top))
    right = max(left + 4, min(width, right))
    bottom = max(top + 4, min(height, bottom))
    return left, top, right, bottom


def normalized_region_to_delogo_box(
    image_size: tuple[int, int],
    region: Region,
    expand: int = 0,
) -> tuple[int, int, int, int]:
    width, height = image_size
    if width < 12 or height < 12:
        return normalized_region_to_box(image_size, region, expand)

    x1, y1, x2, y2 = _sorted_region(region)
    expand = max(0, int(expand))
    margin = 2
    min_size = 4
    max_right = width - margin
    max_bottom = height - margin

    left = int(math.floor(x1 * width)) - expand
    top = int(math.floor(y1 * height)) - expand
    right = int(math.ceil(x2 * width)) + expand
    bottom = int(math.ceil(y2 * height)) + expand

    desired_width = max(min_size, right - left)
    desired_height = max(min_size, bottom - top)

    left = max(margin, min(width - margin - min_size, left))
    top = max(margin, min(height - margin - min_size, top))
    box_width = min(desired_width, max_right - left)
    box_height = min(desired_height, max_bottom - top)

    box_width = max(min_size, box_width)
    box_height = max(min_size, box_height)
    if left + box_width > max_right:
        left = max(margin, max_right - box_width)
    if top + box_height > max_bottom:
        top = max(margin, max_bottom - box_height)

    return left, top, left + box_width, top + box_height


def _rect_mask(size: tuple[int, int], rect: tuple[int, int, int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((rect[0], rect[1], max(rect[0], rect[2] - 1), max(rect[1], rect[3] - 1)), fill=255)
    return mask


def _mask_coverage(mask: Image.Image, rect: tuple[int, int, int, int]) -> float:
    rect_width = max(1, rect[2] - rect[0])
    rect_height = max(1, rect[3] - rect[1])
    if np is None:
        histogram = mask.crop(rect).histogram()
        selected = sum(value * count for value, count in enumerate(histogram)) / 255
        return selected / (rect_width * rect_height)
    crop = np.asarray(mask.crop(rect), dtype="uint8")
    return float((crop > 8).sum()) / float(rect_width * rect_height)


def _clamped_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def describe_removal_options(options: RemovalOptions) -> str:
    smart_label = "开" if options.smart_mask else "关"
    region_count = len(removal_regions(options))
    return (
        f"去水印参数：选区={region_count}个，智能遮罩={smart_label}，"
        f"识别灵敏度={_clamped_int(options.mask_sensitivity, 1, 10)}级，"
        f"区域外扩={_clamped_int(options.expand, 0, 80)}px，"
        f"边缘柔化={_clamped_int(options.feather, 0, 80)}px，"
        f"修复强度={_clamped_int(options.strength, 1, 6)}级"
    )


def _expand_luma_mask(mask: Image.Image, pixels: int) -> Image.Image:
    pixels = max(0, min(96, int(pixels)))
    if pixels <= 0:
        return mask

    expanded = mask
    remaining = pixels
    while remaining > 0:
        step = min(4, remaining)
        expanded = expanded.filter(ImageFilter.MaxFilter(step * 2 + 1))
        remaining -= step
    return expanded


def _smart_watermark_mask(
    image: Image.Image,
    rect: tuple[int, int, int, int],
    options: RemovalOptions,
) -> tuple[Image.Image, float, str]:
    base_mask = _rect_mask(image.size, rect)
    if not options.smart_mask or np is None:
        return base_mask, 1.0, "rect"

    sensitivity = _clamped_int(options.mask_sensitivity, 1, 10)
    expand = _clamped_int(options.expand, 0, 80)
    feather = _clamped_int(options.feather, 0, 80)
    strength = _clamped_int(options.strength, 1, 6)
    left, top, right, bottom = rect
    if right - left < 4 or bottom - top < 4:
        return base_mask, 1.0, "rect"

    crop = image.crop(rect).convert("RGB")
    gray = np.asarray(crop.convert("L"), dtype="int16")
    blur_radius = max(3, int(min(crop.size) * 0.08))
    background = np.asarray(crop.filter(ImageFilter.GaussianBlur(blur_radius)).convert("L"), dtype="int16")
    diff = np.abs(gray - background)

    selected = diff.reshape(-1)
    if selected.size == 0:
        return base_mask, 1.0, "rect"

    adaptive_percentile = max(30, 94 - sensitivity * 6)
    adaptive_threshold = float(np.percentile(selected, adaptive_percentile))
    base_threshold = 32.0 - sensitivity * 2.9
    threshold = max(3.0, min(base_threshold, adaptive_threshold))
    mask_array = diff >= threshold

    mask_crop = Image.fromarray((mask_array.astype("uint8") * 255), "L")
    dilate_pixels = (
        1
        + int(sensitivity >= 6)
        + int(sensitivity >= 9)
        + max(0, strength - 2)
        + expand // 4
        + feather // 18
    )
    mask_crop = _expand_luma_mask(mask_crop, dilate_pixels)
    if feather > 0:
        mask_crop = mask_crop.filter(ImageFilter.GaussianBlur(max(0.3, min(7.0, feather / 10))))

    smart_mask = Image.new("L", image.size, 0)
    smart_mask.paste(mask_crop, (left, top))
    coverage = _mask_coverage(smart_mask, rect)
    if coverage < 0.001 or coverage > 0.94:
        return base_mask, 1.0, "rect"
    return smart_mask, coverage, "smart"


def _video_mask_for_selection(
    frame: Image.Image,
    options: RemovalOptions,
    selected_box: tuple[int, int, int, int],
) -> tuple[Image.Image | None, float, str]:
    if not options.smart_mask:
        return None, 1.0, "rect"
    mask, coverage, mode = _smart_watermark_mask(frame.convert("RGB"), selected_box, options)
    if mode != "smart" or coverage < 0.004:
        return None, coverage, mode
    sensitivity = _clamped_int(options.mask_sensitivity, 1, 10)
    expand = _clamped_int(options.expand, 0, 80)
    feather = _clamped_int(options.feather, 0, 80)
    strength = _clamped_int(options.strength, 1, 6)
    binary_threshold = max(4, 34 - sensitivity * 3)
    binary = mask.point(lambda value: 255 if value > binary_threshold else 0)
    video_expand = max(0, expand // 5 + feather // 14 + max(0, strength - 2))
    binary = _expand_luma_mask(binary, video_expand)
    coverage = _mask_coverage(binary, selected_box)
    return binary, coverage, "smart"


def build_removal_output_path(input_path: str | Path, options: RemovalOptions) -> Path:
    source = Path(input_path)
    output_dir = Path(options.output_dir) if options.output_dir else source.parent / "cleaned"
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    if is_video_file(source) and suffix in {".wmv", ".webm"}:
        suffix = ".mp4"

    base = output_dir / f"{source.stem}_cleaned{suffix}"
    if not base.exists():
        return base

    for index in range(2, 10000):
        candidate = output_dir / f"{source.stem}_cleaned_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("无法生成唯一的输出文件名。")


def _temporary_video_output_path(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix or ".mp4"
    for index in range(1, 10000):
        candidate = output_path.with_name(f".{output_path.stem}_tmp_{os.getpid()}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("无法生成临时视频输出文件名。")


def repair_image_region(image: Image.Image, options: RemovalOptions) -> Image.Image:
    base = ImageOps.exif_transpose(image).convert("RGBA")
    regions = removal_regions(options)
    if not regions:
        return base

    current = base
    for region in regions:
        current = _repair_single_image_region(current, region, options)
    return current


def _repair_single_image_region(base: Image.Image, region: Region, options: RemovalOptions) -> Image.Image:
    base = base.convert("RGBA")
    width, height = base.size
    selected_box = normalized_region_to_box(base.size, region, max(0, int(options.expand)))
    feather = max(0, min(80, int(options.feather)))
    context = max(10, feather * 3, int(min(width, height) * 0.012))
    left, top, right, bottom = selected_box
    crop_box = (
        max(0, left - context),
        max(0, top - context),
        min(width, right + context),
        min(height, bottom + context),
    )

    crop = base.crop(crop_box).convert("RGB")
    rect = (
        left - crop_box[0],
        top - crop_box[1],
        right - crop_box[0],
        bottom - crop_box[1],
    )
    mask, _coverage, mask_mode = _smart_watermark_mask(crop, rect, options)

    strength = _clamped_int(options.strength, 1, 6)
    repaired_crop = _diffuse_repair_crop(crop, mask, strength, feather)
    pasted = base.convert("RGB")
    target = pasted.crop(crop_box)
    blend_radius = feather if mask_mode == "rect" else min(18, max(0, feather // 2 + strength))
    blend_mask = mask.filter(ImageFilter.GaussianBlur(blend_radius)) if blend_radius else mask
    target.paste(repaired_crop, (0, 0), blend_mask)
    pasted.paste(target, crop_box)

    result = pasted.convert("RGBA")
    result.putalpha(base.getchannel("A"))
    return result


def _diffuse_repair_crop(crop: Image.Image, mask: Image.Image, strength: int, feather: int) -> Image.Image:
    if np is None:
        radius = max(8, feather * 2, min(crop.size) // 10)
        return crop.filter(ImageFilter.GaussianBlur(radius))

    crop_small, mask_small, scale = _downscale_for_repair(crop, mask)
    work = np.asarray(crop_small).astype("float32").copy()
    strength = _clamped_int(strength, 1, 6)
    feather = _clamped_int(feather, 0, 80)
    mask_threshold = max(6, 26 - strength * 3)
    mask_array = np.asarray(mask_small) > mask_threshold
    if not mask_array.any():
        return crop

    blur_radius = max(3, int((feather + strength * 3) * scale * 1.3), int(min(crop_small.size) * 0.035))
    blurred = np.asarray(crop_small.filter(ImageFilter.GaussianBlur(blur_radius))).astype("float32")
    work[mask_array] = blurred[mask_array]

    selected = int(mask_array.sum())
    side_hint = int(math.sqrt(max(1, selected)))
    iterations = int(30 + strength * 48 + min(160, side_hint * (0.2 + strength * 0.035)))
    iterations = max(45, min(360, iterations))

    for _ in range(iterations):
        padded = np.pad(work, ((1, 1), (1, 1), (0, 0)), mode="edge")
        average = (
            padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
        ) * 0.25
        work[mask_array] = average[mask_array]

    repaired = Image.fromarray(np.clip(work, 0, 255).astype("uint8"), "RGB")
    if repaired.size != crop.size:
        repaired = repaired.resize(crop.size, Image.Resampling.LANCZOS)
    return repaired


def _downscale_for_repair(crop: Image.Image, mask: Image.Image) -> tuple[Image.Image, Image.Image, float]:
    width, height = crop.size
    max_pixels = 1_250_000
    pixels = width * height
    if pixels <= max_pixels:
        return crop, mask, 1.0

    scale = math.sqrt(max_pixels / pixels)
    new_size = (max(16, int(width * scale)), max(16, int(height * scale)))
    return (
        crop.resize(new_size, Image.Resampling.LANCZOS),
        mask.resize(new_size, Image.Resampling.NEAREST),
        scale,
    )


def remove_watermark_image(input_path: str | Path, options: RemovalOptions) -> ProcessResult:
    region_count = len(removal_regions(options))
    if region_count <= 0:
        raise ValueError("请先在预览图上框选需要修复的水印区域。")

    source = Path(input_path)
    output_path = build_removal_output_path(source, options)

    with Image.open(source) as image:
        rendered = repair_image_region(image, options)
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

    return ProcessResult(source, output_path, "image", f"已修复 {region_count} 个选区")


def make_removal_preview_image(
    input_path: str | Path,
    ffmpeg_path: str,
    options: RemovalOptions,
    max_size: tuple[int, int],
) -> Optional[Image.Image]:
    if is_image_file(input_path):
        with Image.open(input_path) as image:
            preview = repair_image_region(image, options) if removal_regions(options) else ImageOps.exif_transpose(image).convert("RGBA")
    elif is_video_file(input_path):
        frame = extract_video_frame(input_path, ffmpeg_path)
        if frame is None:
            return None
        preview = repair_image_region(frame, options) if removal_regions(options) else frame.convert("RGBA")
    else:
        return None

    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    return preview.convert("RGB")


def remove_watermark_video(
    input_path: str | Path,
    options: RemovalOptions,
    ffmpeg_path: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> ProcessResult:
    regions = removal_regions(options)
    if not regions:
        raise ValueError("请先在预览图上框选需要修复的水印区域。")
    if not ffmpeg_path or not Path(ffmpeg_path).is_file():
        raise RuntimeError("没有找到 FFmpeg，无法处理视频。请在界面右侧选择 ffmpeg.exe。")

    source = Path(input_path)
    output_path = build_removal_output_path(source, options)

    if progress_callback:
        progress_callback("正在读取视频尺寸并换算修复区域...")

    frame = extract_video_frame(source, ffmpeg_path)
    if frame is None:
        raise RuntimeError("无法读取视频首帧，请确认视频文件可以正常播放。")

    if progress_callback:
        progress_callback(describe_removal_options(options))

    repair_boxes: list[tuple[int, int, int, int]] = []
    rect_filters: list[tuple[int, int, int, int]] = []
    smart_mask = Image.new("L", frame.size, 0)
    smart_count = 0
    smart_coverage_values: list[float] = []
    for region in regions:
        x1, y1, x2, y2 = normalized_region_to_delogo_box(frame.size, region, max(0, int(options.expand)))
        box_width = max(4, x2 - x1)
        box_height = max(4, y2 - y1)
        repair_boxes.append((x1, y1, box_width, box_height))
        mask_piece, mask_coverage, mask_mode = _video_mask_for_selection(frame, options, (x1, y1, x2, y2))
        if mask_piece is not None:
            smart_mask = ImageChops.lighter(smart_mask, mask_piece)
            smart_count += 1
            smart_coverage_values.append(mask_coverage)
        else:
            rect_filters.append((x1, y1, box_width, box_height))

    mask_image = smart_mask if smart_count else None
    mask_coverage = sum(smart_coverage_values) / len(smart_coverage_values) if smart_coverage_values else 0.0
    requested_encoder = "cpu" if options.video_encoder == "auto" else options.video_encoder
    encoder, encoder_args, encoder_label = resolve_video_encoder(ffmpeg_path, requested_encoder)
    if progress_callback and options.video_encoder == "auto":
        progress_callback("去水印自动模式已使用 CPU H.264，避免硬件编码卡住或生成损坏视频。")
    if progress_callback:
        if mask_image is not None:
            progress_callback(
                f"视频帧尺寸：{frame.width}x{frame.height}，选区：{len(regions)} 个，智能遮罩：{smart_count} 个，平均覆盖：{mask_coverage:.1%}"
            )
        else:
            details = "；".join(f"x={x}, y={y}, w={w}, h={h}" for x, y, w, h in repair_boxes[:4])
            if len(repair_boxes) > 4:
                details += f"；另 {len(repair_boxes) - 4} 个"
            progress_callback(f"视频帧尺寸：{frame.width}x{frame.height}，矩形修复区域：{details}")

    temp_output_path = _temporary_video_output_path(output_path)

    def build_command(active_encoder: str, active_args: list[str], vf: str, active_output: Path) -> list[str]:
        command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            vf,
            "-map",
            "0:v:0",
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
        if active_output.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            command.extend(["-movflags", "+faststart"])
        command.append(str(active_output))
        return command

    def cleanup_temp_output() -> None:
        if temp_output_path.exists():
            try:
                temp_output_path.unlink()
            except OSError:
                pass

    def run_command(command: list[str]) -> None:
        cleanup_temp_output()
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **_hidden_subprocess_kwargs(),
        )
        started_at = time.monotonic()
        last_progress_at = started_at
        last_size = -1
        while process.poll() is None:
            if cancel_callback and cancel_callback():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                cleanup_temp_output()
                raise RuntimeError("已取消")
            if temp_output_path.exists():
                try:
                    current_size = temp_output_path.stat().st_size
                except OSError:
                    current_size = last_size
                if current_size != last_size:
                    last_size = current_size
                    last_progress_at = time.monotonic()
            if time.monotonic() - last_progress_at > VIDEO_NO_PROGRESS_TIMEOUT:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                cleanup_temp_output()
                raise RuntimeError(f"FFmpeg 超过 {int(VIDEO_NO_PROGRESS_TIMEOUT)} 秒没有写入进度，已自动终止。建议使用 CPU H.264 或缩小框选区域。")
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                pass

        stdout, stderr = process.communicate()
        if process.returncode:
            cleanup_temp_output()
            raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
        if not temp_output_path.exists() or temp_output_path.stat().st_size <= 0:
            cleanup_temp_output()
            raise RuntimeError("FFmpeg 没有生成有效的视频文件。")

    if progress_callback:
        progress_callback(f"正在调用 FFmpeg 修复视频，编码器：{encoder_label}")

    with tempfile.TemporaryDirectory(prefix="watermark_remove_") as tmp:
        filters: list[str] = []
        if mask_image is not None:
            mask_path = Path(tmp) / "removelogo_mask.png"
            mask_image.save(mask_path)
            mask_filter_path = _ffmpeg_filter_escape(str(mask_path).replace("\\", "/"))
            filters.append(f"removelogo=filename='{mask_filter_path}'")
        for x, y, box_width, box_height in rect_filters:
            filters.append(f"delogo=x={x}:y={y}:w={box_width}:h={box_height}:show=0")
        filters.extend(["scale=trunc(iw/2)*2:trunc(ih/2)*2", "format=yuv420p"])
        vf = ",".join(filters)
        if mask_image is not None and rect_filters:
            method_label = f"智能遮罩+矩形修复，{len(regions)} 个选区"
        elif mask_image is not None:
            method_label = f"智能遮罩，{len(regions)} 个选区"
        else:
            method_label = f"矩形修复，{len(regions)} 个选区"

        try:
            run_command(build_command(encoder, encoder_args, vf, temp_output_path))
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            if encoder != "libx264":
                cleanup_temp_output()
                if progress_callback:
                    progress_callback(f"{encoder_label} 启动失败，自动回退到 CPU H.264...")
                try:
                    run_command(build_command("libx264", ["-crf", "18", "-preset", "medium"], vf, temp_output_path))
                    temp_output_path.replace(output_path)
                    return ProcessResult(source, output_path, "video", f"已修复选区（{method_label}，{encoder_label} 失败，已回退 CPU）")
                except (subprocess.CalledProcessError, RuntimeError) as fallback_exc:
                    if isinstance(fallback_exc, subprocess.CalledProcessError):
                        detail = (fallback_exc.stderr or fallback_exc.stdout or "").strip()
                    else:
                        detail = str(fallback_exc)
                    cleanup_temp_output()
                    raise RuntimeError(f"FFmpeg 修复失败：{detail[-900:]}") from fallback_exc

            if isinstance(exc, subprocess.CalledProcessError):
                detail = (exc.stderr or exc.stdout or "").strip()
            else:
                detail = str(exc)
            cleanup_temp_output()
            raise RuntimeError(f"FFmpeg 修复失败：{detail[-900:]}") from exc

        temp_output_path.replace(output_path)

    return ProcessResult(source, output_path, "video", f"已修复选区（{method_label}，{encoder_label}）")


def process_removal_file(
    input_path: str | Path,
    options: RemovalOptions,
    ffmpeg_path: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> ProcessResult:
    if is_image_file(input_path):
        return remove_watermark_image(input_path, options)
    if is_video_file(input_path):
        return remove_watermark_video(input_path, options, ffmpeg_path, progress_callback, cancel_callback)
    raise ValueError(f"不支持的文件格式：{input_path}")
