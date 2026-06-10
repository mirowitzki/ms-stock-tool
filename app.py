#!/usr/bin/env python3
"""
app.py —— MS 股票价值分析工具 桌面应用启动器

启动顺序：
  1. 自动刷新 dashboard 数据（in-process，避免 subprocess Python 依赖）
  2. 优先：pywebview 真原生窗口（WebView2，Level 2）
  3. 回退：Chrome / Edge --app= 模式（Level 1）
  4. 最后回退：系统默认浏览器

使用：
  双击 ms-stock-tool.bat（推荐，静默运行）
  或 python app.py（命令行模式，可看输出）
"""

import os
import sys
from pathlib import Path


# ============================================================
# 路径与日志
# ============================================================

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent.resolve()
else:
    PROJECT_ROOT = Path(__file__).parent.resolve()

LOG_FILE = PROJECT_ROOT / "app.log"
ICON_ICNS = PROJECT_ROOT / "assets" / "icon.icns"   # macOS Dock 图标
ICON_PNG = PROJECT_ROOT / "assets" / "icon.png"     # 通用位图回退
ICON_ICO = PROJECT_ROOT / "assets" / "icon.ico"     # Windows 窗口图标（若存在）


def log(*parts):
    """写入 app.log；如果在控制台模式也打印一份。"""
    msg = " ".join(str(p) for p in parts)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    # 仅当 stdout 真存在时才打印（pythonw 模式下 stdout 是 None）
    if sys.stdout is not None:
        try:
            print(msg)
        except Exception:
            pass


# ============================================================
# 数据刷新（in-process，避免 subprocess）
# ============================================================

def refresh_dashboard_inproc():
    try:
        os.chdir(PROJECT_ROOT)
        scripts_dir = PROJECT_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from refresh_dashboard import main as refresh_main
        refresh_main()
        return True
    except Exception as e:
        log(f"刷新 dashboard 失败：{e}")
        return False


# ============================================================
# 分析队列 API（暴露给 dashboard 的 JS 调用）
# ============================================================

import json as _json
import re as _re
from datetime import datetime as _dt

QUEUE_PATH = PROJECT_ROOT / "analyses" / "_queue.json"

# 美股：1-5 个大写字母；A 股：6 位纯数字（覆盖沪市 6/68、深市 0/3、北京 4/8）
_US_RE = _re.compile(r"^[A-Z]{1,5}$")
_CN_RE = _re.compile(r"^[0-9]{6}$")


class DashboardApi:
    """暴露给浏览器 JS 调用的 Python 接口（通过 window.pywebview.api.*）。
    所有方法返回 dict，包含 ok 字段；失败时含 error 字段。
    """

    def _read_queue(self):
        if not QUEUE_PATH.exists():
            return []
        try:
            # utf-8-sig 兼容 BOM
            data = _json.loads(QUEUE_PATH.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, list) else []
        except Exception as e:
            log(f"读队列失败：{e}")
            return []

    def _write_queue(self, queue):
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_PATH.write_text(
            _json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _classify(ticker):
        t = (ticker or "").strip()
        # A 股：6 位数字（保留原值，不大写）
        if _CN_RE.match(t):
            return t, "CN"
        # 美股：1-5 字母，转大写
        upper = t.upper()
        if _US_RE.match(upper):
            return upper, "US"
        return None, None

    def queue_analysis(self, ticker):
        """把一个股票代码加入分析队列。"""
        normalized, kind = self._classify(ticker)
        if not normalized:
            return {
                "ok": False,
                "error": "无效的股票代码：美股请输入 1-5 个字母（如 NVDA），A 股请输入 6 位数字（如 600519）",
            }
        queue = self._read_queue()
        # 去重：已在队列里就不重复加
        if any(item.get("ticker") == normalized for item in queue):
            return {"ok": False, "error": f"{normalized} 已在队列中（{kind}）"}
        # 去重：已经分析过（有 dossier.md）就也不加，让用户改用别的方式
        analyzed = (PROJECT_ROOT / "analyses" / normalized / "dossier.md").exists()
        queue.append({
            "ticker": normalized,
            "type": kind,
            "queued_at": _dt.now().isoformat(timespec="seconds"),
            "already_analyzed": analyzed,
        })
        self._write_queue(queue)
        return {
            "ok": True,
            "ticker": normalized,
            "type": kind,
            "queue_size": len(queue),
            "already_analyzed": analyzed,
        }

    def get_queue(self):
        """返回当前队列。"""
        return {"ok": True, "queue": self._read_queue()}

    def clear_queue(self):
        """清空整个队列。"""
        if QUEUE_PATH.exists():
            QUEUE_PATH.unlink()
        return {"ok": True}

    def remove_from_queue(self, ticker):
        """从队列里移除一个 ticker。"""
        queue = self._read_queue()
        new_queue = [item for item in queue if item.get("ticker") != ticker]
        self._write_queue(new_queue)
        return {"ok": True, "removed": ticker, "queue_size": len(new_queue)}

    def delete_company(self, ticker):
        """删除一家公司的所有分析文件（analyses/<TICKER>/ 整个目录）。不可恢复。"""
        import shutil
        t = (ticker or "").strip()
        # 安全：只允许字母数字（美股代码 / A 股 6 位数字），挡住路径穿越
        if not _re.match(r"^[A-Za-z0-9]{1,10}$", t):
            return {"ok": False, "error": "非法股票代码"}
        analyses_root = (PROJECT_ROOT / "analyses").resolve()
        target = (analyses_root / t).resolve()
        # 必须是 analyses/ 的直接子目录，且确实存在
        if target.parent != analyses_root or not target.is_dir():
            return {"ok": False, "error": f"找不到 {t} 的分析目录"}
        try:
            shutil.rmtree(target)
        except Exception as e:
            log(f"删除公司 {t} 失败：{e}")
            return {"ok": False, "error": str(e)}
        # 如果它还在排队，一并清掉
        queue = self._read_queue()
        new_queue = [item for item in queue if item.get("ticker") != t]
        if len(new_queue) != len(queue):
            self._write_queue(new_queue)
        # 重新扫描、刷新 dashboard.html，使卡片消失
        refresh_dashboard_inproc()
        log(f"已删除公司 {t} 的全部分析文件")
        return {"ok": True, "ticker": t}


# ============================================================
# Level 2：pywebview 真原生窗口
# ============================================================

def _apply_native_icon():
    """窗口启动后设置原生应用图标。
    在 webview.start() 的 GUI 线程就绪后被调用（macOS 走 AppKit 设 Dock 图标）。
    纯尽力而为，失败只记日志、不影响主流程。
    """
    try:
        if sys.platform == "darwin":
            from AppKit import NSApplication, NSImage  # pyobjc，随 pywebview 一起装
            icon_path = ICON_ICNS if ICON_ICNS.exists() else ICON_PNG
            if icon_path.exists():
                img = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
                if img is not None:
                    NSApplication.sharedApplication().setApplicationIconImage_(img)
                    log(f"已设置 macOS Dock 图标：{icon_path.name}")
    except Exception as e:
        log(f"设置原生图标失败（忽略）：{e}")


def open_with_pywebview(dashboard_path):
    try:
        import webview
    except ImportError as e:
        log(f"pywebview 未安装：{e}")
        return False

    try:
        log("用 pywebview 打开原生窗口...")
        api = DashboardApi()
        webview.create_window(
            title="MS 股票价值分析工具",
            url=dashboard_path.as_uri(),
            width=1440,
            height=900,
            min_size=(1024, 700),
            text_select=True,
            confirm_close=False,
            js_api=api,
        )
        # icon 参数 pywebview 仅在 GTK/Qt 后端支持；Windows 给个 .ico（存在才传），
        # 否则不传，避免在不支持的后端报错。macOS 的 Dock 图标走 _apply_native_icon。
        start_kwargs = {}
        if os.name == "nt" and ICON_ICO.exists():
            start_kwargs["icon"] = str(ICON_ICO)
        webview.start(_apply_native_icon, **start_kwargs)  # 阻塞直到窗口关闭
        log("窗口已关闭。")
        return True
    except Exception as e:
        log(f"pywebview 启动失败（可能 WebView2 runtime 未安装）：{e}")
        return False


# ============================================================
# Level 1 回退：Chrome / Edge --app= 模式
# ============================================================

def open_with_browser_app(dashboard_path):
    import subprocess
    import webbrowser

    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    ]
    browser = next((p for p in candidates if p and Path(p).exists()), None)

    if not browser:
        log("Chrome/Edge 均未找到，降级到系统默认浏览器")
        webbrowser.open(dashboard_path.as_uri())
        return True

    log(f"回退到 {Path(browser).stem} app 模式...")
    profile_dir = PROJECT_ROOT / ".browser-profile"
    profile_dir.mkdir(exist_ok=True)
    subprocess.Popen([
        browser,
        f"--app={dashboard_path.as_uri()}",
        "--window-size=1440,900",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_dir}",
    ])
    return True


# ============================================================
# 主入口
# ============================================================

def main():
    log("=" * 50)
    log("MS 股票价值分析工具 启动中")
    log(f"项目根目录: {PROJECT_ROOT}")

    dashboard = PROJECT_ROOT / "dashboard.html"
    if not dashboard.exists():
        log(f"错误：找不到 {dashboard}")
        return 1

    # 第一步：刷新数据
    if refresh_dashboard_inproc():
        log("Dashboard 数据已刷新")
    else:
        log("跳过刷新，使用旧快照")

    # 第二步：尝试 Level 2，失败则回退 Level 1
    if open_with_pywebview(dashboard):
        return 0

    log("Level 2 失败，回退到 Level 1（浏览器 app 模式）")
    open_with_browser_app(dashboard)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户取消")
        sys.exit(0)
    except Exception as e:
        log(f"未预期错误：{e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)
