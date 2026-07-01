# 智影水印

一个本地桌面批量水印工具，支持图片和视频。

## 当前能力

- 批量添加图片：`jpg`、`png`、`webp`、`bmp`、`tiff`
- 批量添加视频：`mp4`、`mkv`、`mov`、`avi`、`wmv`
- 图片水印真实处理输出
- 视频通过 FFmpeg 处理输出
- 智能角落：自动选择较干净的角落放水印
- 智能文字风格：根据背景自动选择白字/黑字、描边、阴影、半透明底衬
- 可选 Logo 图片水印，支持文字 + Logo 组合
- 视频编码器支持自动选择、CPU H.264、NVIDIA NVENC、Intel Quick Sync、AMD AMF
- 硬件编码失败会自动回退到 CPU H.264，避免批量任务中断
- 底部处理日志会记录当前文件、输出路径和失败原因
- 支持在 Windows 上直接拖拽文件或文件夹到窗口
- 自动保存上次使用的水印、Logo、输出目录和编码器设置
- 支持取消批处理；视频编码中也会尝试停止 FFmpeg
- 支持处理完成后自动打开输出目录
- 内置水印预设：清晰角标、轻量标记、强可见、平铺防盗、Logo 品牌
- 支持导出处理日志
- 提供 PyInstaller 打包脚本，可生成 Windows `.exe`
- 浅色专业工具界面，顶部状态徽标、预览区、日志区和设置面板更清晰
- FFmpeg 在后台隐藏执行，不弹出 CMD 黑框
- 预览在后台生成，减少按钮和滑块卡顿
- 便携打包脚本可生成 zip，方便分享给其它电脑
- 图片预览；视频在 FFmpeg 可用时预览首帧效果

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
