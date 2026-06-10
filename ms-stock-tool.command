#!/bin/bash
# MS 股票价值分析工具 —— Mac 启动器（对应 Windows 的 ms-stock-tool.bat）
# 首次使用前需赋予执行权限：在终端里 chmod +x ms-stock-tool.command
# 之后在访达里双击本文件即可打开桌面应用窗口。
cd "$(dirname "$0")"
python3 app.py
