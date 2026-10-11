from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

APP_VERSION = "1.1.0"
GITHUB_REPO = "100142armin-lgtm/watermark_studio"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
USER_AGENT = f"WatermarkStudio/{APP_VERSION}"


@dataclass
class UpdateInfo:
    has_update: bool
    current_version: str
    latest_version: str
    title: str = ""
    description: str = ""
    release_url: str = ""
    download_url: str = ""
    asset_name: str = ""
    asset_size: int = 0
    is_zip: bool = False


def parse_version(version_str: str) -> tuple[int, ...]:
    cleaned = re.sub(r"^[^\d]*", "", str(version_str).strip())
    parts = []
    for piece in cleaned.split("."):
        match = re.match(r"^\d+", piece)
        if match:
            parts.append(int(match.group()))
        else:
            break
    return tuple(parts) if parts else (0, 0, 0)


def is_newer_version(remote_ver: str, current_ver: str = APP_VERSION) -> bool:
    return parse_version(remote_ver) > parse_version(current_ver)


def check_for_updates(timeout: int = 8) -> UpdateInfo:
    current = APP_VERSION
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }

    data = None
    try:
        req = urllib.request.Request(API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        data = None

    if data and "tag_name" in data:
        tag_name = data.get("tag_name", "").strip()
        latest_ver = tag_name.lstrip("vV")
        has_update = is_newer_version(latest_ver, current)
        title = data.get("name", "") or f"v{latest_ver}"
        description = data.get("body", "") or "暂无更新说明"
        release_url = data.get("html_url", "") or f"https://github.com/{GITHUB_REPO}/releases/latest"

        assets = data.get("assets", [])
        exe_url = ""
        zip_url = ""
        exe_size = 0
        zip_size = 0

        for asset in assets:
            name = asset.get("name", "")
            download_url = asset.get("browser_download_url", "")
            size = asset.get("size", 0)
            if name.lower().endswith(".exe"):
                exe_url = download_url
                exe_size = size
            elif name.lower().endswith(".zip"):
                zip_url = download_url
                zip_size = size

        is_frozen = getattr(sys, "frozen", False)
        prefer_zip = False
        if is_frozen:
            exe_dir = Path(sys.executable).parent
            if (exe_dir / "_internal").exists() and zip_url:
                prefer_zip = True

        if prefer_zip and zip_url:
            download_url = zip_url
            asset_name = "WatermarkStudio_Portable.zip"
            asset_size = zip_size
            is_zip = True
        elif exe_url:
            download_url = exe_url
            asset_name = "WatermarkStudio.exe"
            asset_size = exe_size
            is_zip = False
        else:
            download_url = zip_url or release_url
            asset_name = "WatermarkStudio_Portable.zip" if zip_url else ""
            asset_size = zip_size
            is_zip = bool(zip_url)

        return UpdateInfo(
            has_update=has_update,
            current_version=current,
            latest_version=latest_ver,
            title=title,
            description=description,
            release_url=release_url,
            download_url=download_url,
            asset_name=asset_name,
            asset_size=asset_size,
            is_zip=is_zip,
        )

    try:
        req = urllib.request.Request(RAW_VERSION_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw_info = json.loads(resp.read().decode("utf-8"))
                latest_ver = raw_info.get("version", "").strip().lstrip("vV")
                has_update = is_newer_version(latest_ver, current)
                return UpdateInfo(
                    has_update=has_update,
                    current_version=current,
                    latest_version=latest_ver,
                    title=raw_info.get("name", f"v{latest_ver}"),
                    description=raw_info.get("description", ""),
                    release_url=raw_info.get("release_url", f"https://github.com/{GITHUB_REPO}/releases/latest"),
                    download_url=raw_info.get("exe_url", ""),
                    asset_name="WatermarkStudio.exe",
                    asset_size=0,
                    is_zip=False,
                )
    except Exception:
        pass

    return UpdateInfo(
        has_update=False,
        current_version=current,
        latest_version=current,
        title="",
        description="",
    )


def download_update_file(
    download_url: str,
    target_path: Path,
    progress_callback: Optional[Callable[[float, int, int], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> bool:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target_path.with_suffix(target_path.suffix + ".downloading")
    if temp_target.exists():
        try:
            temp_target.unlink()
        except OSError:
            pass

    headers = {"User-Agent": USER_AGENT}
    req = urllib.request.Request(download_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        total_length = response.headers.get("Content-Length")
        total_size = int(total_length) if total_length and total_length.isdigit() else 0
        downloaded = 0
        chunk_size = 64 * 1024

        with open(temp_target, "wb") as f:
            while True:
                if cancel_callback and cancel_callback():
                    f.close()
                    try:
                        temp_target.unlink()
                    except OSError:
                        pass
                    return False
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    percent = (downloaded / total_size * 100) if total_size > 0 else 0.0
                    progress_callback(percent, downloaded, total_size)

    if temp_target.exists():
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        temp_target.rename(target_path)
        return True
    return False


def apply_update_and_restart(new_file_path: Path, is_zip: bool = False) -> None:
    if not getattr(sys, "frozen", False):
        return

    current_pid = os.getpid()
    target_exe = Path(sys.executable).resolve()
    target_dir = target_exe.parent
    new_file = Path(new_file_path).resolve()

    if is_zip:
        ps_script = (
            f"$targetPid = {current_pid}; "
            f"$zipPath = '{str(new_file).replace("'", "''")}'; "
            f"$targetDir = '{str(target_dir).replace("'", "''")}'; "
            f"$targetExe = '{str(target_exe).replace("'", "''")}'; "
            f"Wait-Process -Id $targetPid -Timeout 20 -ErrorAction SilentlyContinue; "
            f"Start-Sleep -Milliseconds 600; "
            f"Expand-Archive -Path $zipPath -DestinationPath $targetDir -Force; "
            f"Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue; "
            f"Start-Process -FilePath $targetExe"
        )
    else:
        ps_script = (
            f"$targetPid = {current_pid}; "
            f"$src = '{str(new_file).replace("'", "''")}'; "
            f"$dst = '{str(target_exe).replace("'", "''")}'; "
            f"Wait-Process -Id $targetPid -Timeout 20 -ErrorAction SilentlyContinue; "
            f"Start-Sleep -Milliseconds 600; "
            f"Copy-Item -Path $src -Destination $dst -Force; "
            f"Remove-Item -Path $src -Force -ErrorAction SilentlyContinue; "
            f"Start-Process -FilePath $dst"
        )

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
        creationflags=flags,
        close_fds=True,
    )
    sys.exit(0)
