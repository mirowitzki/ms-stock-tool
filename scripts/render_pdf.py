#!/usr/bin/env python3
"""
render_pdf.py —— 把 analyses/<TICKER>/ 下的中文 Markdown 报告渲染成 PDF。

依赖（一次性）：
  - Pandoc        winget install JohnMacFarlane.Pandoc
  - wkhtmltopdf   winget install wkhtmltopdf.wkhtmltox
  - 字体          微软雅黑（Windows 自带）

用法：
  python scripts/render_pdf.py RKLB                     # 默认：渲染 3 份用户交付物
                                                          (*完整报告.md / dossier.md / memo.md)
  python scripts/render_pdf.py RKLB --file dossier.md   # 指定单个文件

输出：
  与源 .md 同目录、同名的 .pdf 文件
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 质检硬闸门：完整报告不过五道质检关、不出干净 PDF（解决"有模板不照做"的执行问题）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qc_gate import verify_qc


# 自动定位 pandoc / wkhtmltopdf（Windows 常见路径 + PATH 搜索）
def find_executable(name, common_paths):
    found = shutil.which(name)
    if found:
        return found
    for p in common_paths:
        if Path(p).exists():
            return p
    return None


def find_pandoc():
    return find_executable("pandoc", [
        r"C:\Program Files\Pandoc\pandoc.exe",
        r"C:\Users\%s\AppData\Local\Pandoc\pandoc.exe" % os.environ.get("USERNAME", ""),
    ])


def find_wkhtmltopdf():
    return find_executable("wkhtmltopdf", [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ])


def render_one(md_path, pandoc_exe, wkhtmltopdf_exe, css_path):
    """渲染单个 .md 为同名 .pdf。"""
    md_path = Path(md_path)
    pdf_path = md_path.with_suffix(".pdf")
    title = md_path.stem  # 文件名（不带扩展名）作为 PDF 元数据标题

    cmd = [
        pandoc_exe,
        str(md_path),
        "-o", str(pdf_path),
        f"--pdf-engine={wkhtmltopdf_exe}",
        f"--css={css_path}",
        "--toc",
        "--toc-depth=3",
        f"--metadata=title:{title}",
        "--pdf-engine-opt=--enable-local-file-access",
        "--pdf-engine-opt=--encoding", "--pdf-engine-opt=UTF-8",
        "--pdf-engine-opt=--footer-center", "--pdf-engine-opt=[page] / [topage]",
        "--pdf-engine-opt=--footer-font-size", "--pdf-engine-opt=9",
        "--pdf-engine-opt=--footer-spacing", "--pdf-engine-opt=8",
    ]

    print(f"  正在渲染 {md_path.name} ...")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"  失败：{result.stderr}", file=sys.stderr)
        return None
    print(f"  完成 → {pdf_path.name}（{pdf_path.stat().st_size // 1024} KB）")
    return pdf_path


def main():
    ap = argparse.ArgumentParser(description="把中文 Markdown 报告渲染成排版工整的 PDF。")
    ap.add_argument("ticker", help="股票代码，如 RKLB")
    ap.add_argument("--file", help="指定单个 .md 文件名（相对 analyses/<TICKER>/）；不指定则渲染所有 *_完整报告.md")
    ap.add_argument("--draft", action="store_true", help="跳过质检硬闸门、强制出草稿 PDF（默认不过五道质检关拒绝出完整报告 PDF）")
    args = ap.parse_args()

    pandoc_exe = find_pandoc()
    if not pandoc_exe:
        sys.exit("错误：找不到 pandoc。请先装：winget install JohnMacFarlane.Pandoc")
    wk_exe = find_wkhtmltopdf()
    if not wk_exe:
        sys.exit("错误：找不到 wkhtmltopdf。请先装：winget install wkhtmltopdf.wkhtmltox")

    css_path = Path("scripts") / "pdf_style.css"
    if not css_path.exists():
        sys.exit(f"错误：找不到 CSS 样式 {css_path}")

    ticker = args.ticker.upper()
    base = Path("analyses") / ticker
    if not base.exists():
        sys.exit(f"错误：找不到 {base}。先跑 fetch_filings.py。")

    # 找要渲染的 .md 文件
    if args.file:
        targets = [base / args.file]
        if not targets[0].exists():
            sys.exit(f"错误：找不到 {targets[0]}")
    else:
        # 默认：渲染 3 份用户交付物（深度报告 + dossier + memo）
        # 任何一个不存在的会被静默跳过，方便部分完成的分析也能跑
        targets = []
        targets.extend(sorted(base.glob("*完整报告.md")))
        for fname in ("dossier.md", "memo.md"):
            p = base / fname
            if p.exists():
                targets.append(p)
        if not targets:
            sys.exit(
                f"错误：在 {base} 下找不到任何可渲染的 .md 文件。\n"
                f"期望以下任一存在：*完整报告.md、dossier.md、memo.md"
            )

    print(f"准备渲染 {ticker} 的 {len(targets)} 份报告：")
    rendered = []
    for md in targets:
        # 完整报告走质检硬闸门：五道关全过 + _thesis.md 在 + 报告指纹未过期，才放行
        if "完整报告" in md.name and not args.draft:
            ok, msg = verify_qc(ticker)
            if not ok:
                print(f"  ⛔ {md.name} 未过质检闸门、拒绝出 PDF：\n     {msg}")
                print(f"     跑完五道质检关后登记：python scripts/qc_gate.py {ticker} --record "
                      f"check_numbers=pass fact=pass discipline=pass depth=pass insight=pass")
                print(f"     （确需草稿可加 --draft 跳过闸门）")
                continue
            print(f"  ✓ 质检闸门放行：{msg}")
        result = render_one(md, pandoc_exe, wk_exe, css_path.absolute())
        if result:
            rendered.append(result)

    print()
    print(f"完成 {len(rendered)}/{len(targets)} 份。输出在 {base}/")
    return rendered


if __name__ == "__main__":
    main()
