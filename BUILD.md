# 打包成 EXE

在 PowerShell 中进入本目录，然后运行：

```powershell
.\build_exe.ps1 -InstallPyInstaller
```

首次运行会安装 PyInstaller，然后生成：

```text
dist\WatermarkStudio\WatermarkStudio.exe
```

如果已经安装过 PyInstaller，之后可以直接运行：

```powershell
.\build_exe.ps1
```

如果想生成单文件版：

```powershell
.\build_exe.ps1 -OneFile
```

单文件版启动会慢一点；文件夹版更稳定，也更适合放 `ffmpeg.exe`。

## 生成便携包

先打包 exe，然后运行：

```powershell
.\package_portable.ps1 -IncludeFfmpeg
```

输出：

```text
release\WatermarkStudio_Portable.zip
```

把这个 zip 发给别人或拷贝到其它设备，解压后运行 `WatermarkStudio.exe`。
