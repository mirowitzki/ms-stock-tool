#!/usr/bin/env python3
"""
check_explorers.py —— 交互器批量冒烟测试（O3，2026-07-05）。

来历：16 家共享一个模板（tools/valuation_explorer.html），每次改模板全靠人工开浏览器
逐家看，不可持续、也漏过东西（历史上多次靠"顺手点开才发现"）。这个脚本做静态断言：
批量重渲后必跑，红了就别交付。

查什么（每家 analyses/<T>/valuation_explorer.html）：
  1 数据块合法：<script id="initial-data"> 里是能解析的 JSON、含 facts/scenarios 关键键；
  2 必备元素齐：安全边际头条/四柱/市场vs我/历史图/桑基/三情景可能性/时间线/报告区等 id 都在；
  3 模板部分（剔除注入的 JSON 数据后）不含旧口径词（概率加权中枢等）与已清掉的解说词，
    含区间口径关键词（保守端）——只查模板层，不查嵌入的报告正文（存量报告措辞归 O5 挂账）；
  4 dashboard.html 的数据块能解析、公司列表非空。

用法：python3 scripts/check_explorers.py           # 全部
      python3 scripts/check_explorers.py 600327    # 单家
注意：纯静态检查，抓不住运行时 JS 错误——改共享模板后仍要人工浏览器抽查三型各一家
（盈利分部/亏损/资产型），这里只兜"批量重渲把谁漏了/截断了/带回旧词"这类事故。
"""
import json
import re
import sys
from pathlib import Path

REQUIRED_IDS = [
    "ticker-badge", "safety-headline", "gauges", "section-mvm", "chart-history",
    "chart-sankey", "section-report", "timeline",
    "likelihood-bear", "likelihood-base", "likelihood-bull",
    "fact-revenue", "footer-time", "nav-export",
]
# 模板层禁词：旧估值口径 + 已清掉的常驻解说词（见 2026-07-04 UI 清理）
BANNED_TEMPLATE = [
    "概率加权中枢", "隐含年化回报",
    "安全边际看现价离保守端多远", "差额就是预期差", "条越粗＝营收越大",
    "再挂一个毛估的价值区间", "下次打开会保留你的调整", "可调整，下方所有计算实时更新",
]
REQUIRED_TEMPLATE = ["保守端"]  # 区间口径关键词

DATA_RE = re.compile(r'<script id="initial-data" type="application/json">(.*?)</script>', re.S)
DASH_RE = re.compile(r'<script id="dashboard-data" type="application/json">(.*?)</script>', re.S)


def check_explorer(path: Path):
    problems = []
    html = path.read_text(encoding="utf-8")
    m = DATA_RE.search(html)
    if not m:
        return [f"找不到 initial-data 数据块"]
    raw = m.group(1)
    try:
        data = json.loads(raw)
    except Exception as e:
        problems.append(f"initial-data 不是合法 JSON：{e}")
        data = {}
    for key in ("facts", "scenarios"):
        if key not in data:
            problems.append(f"数据块缺关键键 {key}")
    for el in REQUIRED_IDS:
        if f'id="{el}"' not in html:
            problems.append(f"缺必备元素 id={el}")
    template_part = html.replace(raw, "")
    for w in BANNED_TEMPLATE:
        if w in template_part:
            problems.append(f"模板层出现禁词「{w}」（旧口径/解说词回流）")
    for w in REQUIRED_TEMPLATE:
        if w not in template_part:
            problems.append(f"模板层缺区间口径关键词「{w}」")
    return problems


def check_dashboard():
    p = Path("dashboard.html")
    if not p.exists():
        return ["dashboard.html 不存在"]
    m = DASH_RE.search(p.read_text(encoding="utf-8"))
    if not m:
        return ["找不到 dashboard-data 数据块"]
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        return [f"dashboard-data 不是合法 JSON：{e}"]
    if not data.get("companies"):
        return ["dashboard 公司列表为空"]
    return []


def main():
    only = sys.argv[1].upper() if len(sys.argv) > 1 else None
    base = Path("analyses")
    total_bad = 0
    n = 0
    for d in sorted(base.glob("*")):
        if not d.is_dir() or (only and d.name != only):
            continue
        p = d / "valuation_explorer.html"
        if not p.exists():
            continue
        n += 1
        probs = check_explorer(p)
        if probs:
            total_bad += 1
            print(f"✗ {d.name}")
            for x in probs:
                print(f"    - {x}")
        else:
            print(f"✓ {d.name}")
    if not only:
        probs = check_dashboard()
        if probs:
            total_bad += 1
            print("✗ dashboard.html")
            for x in probs:
                print(f"    - {x}")
        else:
            print("✓ dashboard.html")
    print(f"\n共检 {n} 家交互器" + ("" if only else " + dashboard") + f"，{'全部通过' if total_bad == 0 else f'{total_bad} 处不通过'}")
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
