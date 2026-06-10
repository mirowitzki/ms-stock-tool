# 在 Mac 上把这个工具装好（搬家后照做一次）

> 用途：从 Windows 把项目拷到 Mac 后，在 Mac 上打开 Claude Code，让它照这份清单把运行环境装好。报告 PDF 和交互器 HTML 本来就能直接双击打开看；这份清单是为了能在 Mac 上继续跑分析脚本和桌面应用。
> 给 Mac 上的 Claude Code 的话：请逐条执行下面步骤，遇到报错就停下来跟用户解释、别跳过。用户不是程序员，所有命令你来跑、用大白话解释。

## 0. 前提
- 装好 Homebrew（https://brew.sh，一行命令）。
- 装好 Python 3.12+（`brew install python@3.12`）。Mac 上命令用 `python3`、`pip3`（不是 Windows 的 `python`/`pythonw`）。

## 1. 装 Python 依赖
在 `ms-stock-tool` 目录里跑：
```
pip3 install -r requirements.txt
```
（会装上 requests、beautifulsoup4、lxml、akshare、pypdf、pywebview，akshare 会自动带上 pandas。）

## 2. 装两个出 PDF 用的外部程序（非 pip）
```
brew install pandoc
brew install --cask wkhtmltopdf
```

## 3. 给 Mac 启动器赋执行权限
```
chmod +x ms-stock-tool.command
```
之后在访达里双击 `ms-stock-tool.command` 就能打开桌面应用窗口（对应 Windows 的 `ms-stock-tool.bat`；那个 .bat 在 Mac 上用不了，忽略它）。

## 4. 配 SEC 身份（抓美股年报用）
`fetch_filings.py` 需要一个真实的 SEC User-Agent。把这行加进 `~/.zshrc`（Mac 默认终端是 zsh）：
```
export SEC_USER_AGENT="Miro Sun sunclothe@gmail.com"
```
然后 `source ~/.zshrc` 生效。

## 5. 把 Windows 路径/命令改成 Mac 版（如果连父目录 .claude 一起拷了）
父目录 `Claude Apps/.claude/` 里有两份配置，是按 Windows 写的，需在 Mac 上各改一处：
- `launch.json`：dashboard 预览那条把 `"python"` 改成 `"python3"`，目录路径改成 Mac 上的实际路径（如 `/Users/<你>/.../Claude Apps/ms-stock-tool`）。
- `settings.json`：队列 hook（queue_hook.py）的命令若是 `python`/`pythonw`，改成 `python3`。
（如果只拷了 `ms-stock-tool` 这一个文件夹、没拷父目录，那就不用管这步；dashboard 预览改用：在 ms-stock-tool 目录里跑 `python3 -m http.server 8137` 再用浏览器打开。）

## 6. 验证装好了
```
python3 scripts/refresh_dashboard.py      # 能扫到 7 家公司、刷新 dashboard.html 就对了
```
再双击 `ms-stock-tool.command` 看桌面窗口能不能开。能跑 `refresh_dashboard.py`、能开窗口、能拿浏览器看 dashboard 和某家公司的交互器，就算装好了。

## Mac 装机实况（2026-06-05 在 Miro 的 M 芯片 Mac 上完成）
- 这台机器没装 Homebrew、只有系统自带 Python 3.9.6。最终方案：依赖装进系统 python3 的用户目录（`pip3 install --user`），不另装 3.12——跑通了。`pywebview` 的 `pyobjc-core` 在旧编译器下源码编译会报错，已通过 `pip` 升级后自动拿到 cp39 预编译 wheel 解决。
- `wkhtmltopdf` 上游停更、Homebrew 已下架：改用官网 `0.12.6-2.macos-cocoa.pkg`（x86_64），靠 Rosetta 2 跑（已 `softwareupdate --install-rosetta` 装好），二进制放在 `/opt/homebrew/bin/wkhtmltopdf`。`pandoc` 用 `brew install pandoc`。出 PDF 实测正常。
- SEC 身份写进了 `~/.zshrc` 和 `~/.zprofile`（后者保证非交互式 shell 也读得到）。
- **项目位置已从 `~/Documents/Vibe Coding/ms-stock-tool` 移到 `~/ms-stock-tool`**：因为 macOS 对「文稿(Documents)」有隐私保护，从 /Applications 启动的 App 读不到 Documents 里的文件（报 Operation not permitted）。挪到家目录根下后，App 双击即可正常读写。**以后开 Claude Code 请在 `~/ms-stock-tool` 打开。**
- **Applications 里的快捷方式**：`/Applications/MS股票价值分析工具.app`（自带图标，已 ad-hoc 签名）。双击 / Launchpad / 拖进 Dock 都能用，无终端窗口。它内部就是 `cd ~/ms-stock-tool && /usr/bin/python3 app.py`，日志写在 `~/Library/Logs/ms-stock-tool.log`。换项目路径时改 `App/Contents/MacOS/launcher` 里的 `PROJECT_DIR` 再 `codesign --force --deep --sign - 那个.app` 重签一次即可。

## 备注
- pywebview 在 Mac 上走系统自带的 WebKit，不像 Windows 用 WebView2——一般开箱即用，不用额外装浏览器内核。
- 已经分析好的 7 家公司（含报告 PDF、交互器、decision.json、CLAUDE.md、教训库）都是文件，拷过来就在，不会丢。新开的 Claude Code 读 `CLAUDE.md` 就能接上进度。
