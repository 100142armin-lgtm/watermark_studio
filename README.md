# 智影水印 (Watermark Studio)

当前版本：`v1.1.0`

一个功能强大的本地桌面批量水印与去水印工具，支持图片和视频。

## 当前能力

- **双操作模式**：支持一键切换“批量加水印”与“批量去水印修复”；
- **智能去水印**：
  - 交互式大预览框选，支持同时添加多个去水印选区、拖拽移动选区与撤销（Undo）；
  - 智能边缘检测（只修复文字/Logo痕迹），支持灵敏度、外扩、边缘柔化与强度调节；
  - 基于热传导偏微分扩散修复算法，兼顾大图平滑修补效果；
  - 视频支持智能遮罩（FFmpeg `removelogo`）与选区修复（FFmpeg `delogo`）；
- **批量添加图片**：`jpg`、`png`、`webp`、`bmp`、`tiff`
- **批量添加视频**：`mp4`、`mkv`、`mov`、`avi`、`wmv`
- **智能角落与风格**：自动分析图像四角背景干扰度，自动选择白字/黑字、描边、阴影、半透明底衬；
- **Logo 品牌水印**：可选 Logo 图片，支持文字 + Logo 组合排版与平铺防盗；
- **视频硬件加速**：支持 CPU H.264、NVIDIA NVENC、Intel Quick Sync、AMD AMF，失败自动回退 CPU；
- **静默在线更新**：
  - 启动时自动静默检查 GitHub 仓库最新版本；
  - 检测到新版后可在后台静默下载，不弹窗、不卡顿、不影响任何正常电脑操作；
  - 下载完成后一键重启平滑生效，并支持界面右上角与设置面板随时手动检查；
- **Windows 原生拖拽**：支持文件与文件夹直接拖拽添加；
- **现代化深浅主题**：一键切换黑夜/白天模式，大图支持缩放与平移预览；

## 启动

双击 `run.bat`，或在 PowerShell 中运行：

```powershell
.\run.ps1
```

## FFmpeg

程序会自动查找常见位置的 `ffmpeg.exe`。如果界面顶部显示未找到，点击右侧 FFmpeg 的“选择”，手动选择 `ffmpeg.exe`。

没有 FFmpeg 时，图片处理仍然可用，视频处理不可用。

## 打包

详见 `BUILD.md`。最常用命令：

```powershell
.\build_exe.ps1 -InstallPyInstaller
```

## 分享给别人或其它设备

推荐生成便携 zip：

```powershell
.\package_portable.ps1 -IncludeFfmpeg
```

生成的 `release\WatermarkStudio_Portable.zip` 可以发给别人。对方解压后运行 `WatermarkStudio.exe` 即可。

如果不包含 `ffmpeg.exe`，图片水印仍可用；视频水印需要在对方电脑上手动选择 `ffmpeg.exe`。
