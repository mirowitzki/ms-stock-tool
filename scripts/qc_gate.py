#!/usr/bin/env python3
"""
qc_gate.py —— 报告交付的硬闸门：不过质检关，就出不来干净 PDF。

来历（2026-06-19）：用户点破"有模板不照做"的执行问题——光写方法论/模板/技能（被动文档）
管不住执行，因为最该做的分析部分会被静默跳过、没有任何一个点强制它暴露。解决办法不是再写
一份文档，而是把质检关变成代码强制的闸门（参照"净债漏算"教训：终点是代码/回归测试、不是
让人每次手工记得）。

机制：
  - 报告作者写完报告、依次跑五道质检关（check_numbers + 防幻觉 + 防成见 + 防写水 + 防浅析）
    后，用 `--record` 把每道关的结论登记进 analyses/<T>/_qc_status.json，同时锁定当前报告的
    sha256 指纹。
  - render_pdf.py 出 PDF 前调用本闸门 verify：只有 ①动笔前四步 _thesis.md 存在 ②五道关全部
    pass ③登记时的报告指纹 == 当前报告指纹（即登记后没再改过报告）——三者同时满足，才放行。
  - 任一不满足 → 闸门拦下、render_pdf 默认拒绝出 PDF。改了报告→指纹不符→必须重跑质检重登记；
    跳过某道关→该关非 pass→拦下。把"应该跑质检"变成"不跑就出不来干净交付物"。

诚实边界：五道关的结论由作者跑独立 agent 后登记，闸门不能阻止"谎报 pass"——但它能堵住真正
高发的失败：忘了跑、跳过某关、质检后又改了报告却没重查。独立对抗 agent 一旦被强制跑起来，
其严格性不依赖作者的诚实、只依赖"真的跑了"，而这正是闸门强制的。

用法：
  python scripts/qc_gate.py 603358                      # 校验（render_pdf 会自动调）
  python scripts/qc_gate.py 603358 --record check_numbers=pass fact=pass discipline=pass depth=pass insight=pass [--note "..."]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_chapters import verify_chapters  # 章节卡完备闸门（防"有标准不照做"）

# 五道关的内部键 + 对外名（顺序即流水线顺序）
LINES = [
    ("check_numbers", "代码对账 check_numbers"),
    ("fact", "防幻觉 fact-check"),
    ("discipline", "防成见 discipline-check"),
    ("depth", "防写水 depth-check"),
    ("insight", "防浅析 insight-check"),
]
LINE_KEYS = {k for k, _ in LINES}
# --record 时允许的别名 → 标准键
ALIASES = {"fact_check": "fact", "factcheck": "fact", "discipline_check": "discipline",
           "depth_check": "depth", "insight_check": "insight", "numbers": "check_numbers"}


def find_report(base: Path):
    """定位被门控的完整报告 .md（唯一交付物）。"""
    reports = sorted(base.glob("*完整报告.md"))
    return reports[0] if reports else None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_qc(ticker: str):
    """返回 (ok: bool, msg: str)。render_pdf.py 调它。"""
    base = Path("analyses") / ticker.upper()
    report = find_report(base)
    if report is None:
        return False, f"找不到 {base}/*完整报告.md"

    problems = []

    # ① 动笔前四步 _thesis.md（强制"分析先于码字"）。2026-07-05 起（O2）：不止查字数、查四步结构——
    # 之前只查 >200 字是纸老虎（600327 那份 407 字的物业修正条混过去了），四步的关键词必须都在。
    thesis = base / "_thesis.md"
    if not thesis.exists() or len(thesis.read_text(encoding="utf-8").strip()) < 200:
        problems.append("缺『动笔前四步』_thesis.md（核心论点/认知差/价值困在哪/主变量，>200字）"
                        "——分析必须先于码字、且落成文件")
    else:
        ttext = thesis.read_text(encoding="utf-8")
        need = {"核心论点": "核心论点", "认知差": "认知差", "价值困": "价值困在哪/靠什么释放", "主变量": "主变量"}
        t_miss = [label for kw, label in need.items() if kw not in ttext]
        if t_miss:
            problems.append("_thesis.md 缺四步结构：" + "、".join(t_miss)
                            + "——只有零散笔记不算完成『分析先于码字』（O2，2026-07-05 起）")

    # ② 章节卡完备（已定交付标准的章必须出卡 + 报告含脚手架）——独立于质检登记、总是检查，防"有标准不照做"
    ch_ok, ch_problems = verify_chapters(ticker)
    if not ch_ok:
        problems.extend("章节卡：" + p for p in ch_problems)

    # ③ 质检登记存在
    status_path = base / "_qc_status.json"
    if not status_path.exists():
        problems.append("无 _qc_status.json：五道质检关结论未登记。先跑完五道关、再 qc_gate.py --record")
        return False, "；\n  ".join(problems)
    status = json.loads(status_path.read_text(encoding="utf-8"))

    # ④ 报告指纹未过期（登记后没再改过报告）
    cur = sha256_of(report)
    if status.get("report_sha256") != cur:
        problems.append("报告在质检登记后被改动过（指纹不符）→ 质检结论已过期，需重跑五道关并重新 --record")

    # ④.5 卡片数据指纹（2026-07-05 起，O1）：valuation_inputs.json 是交互器卡片的数据源、主交付物的主面——
    # 600327 百货 28% 幻觉×7 处、300996 回路/净利率漏同步都出在这里（只改报告不改卡片、或反过来）。
    # 登记后改卡片＝质检过期，与报告同权。decision.json 刻意不进指纹：predictions/invalidation 的状态结算
    # 是复盘的日常簿记、不应作废质检（判断内核若变，本来就要走完整重分析+重登记）。
    vi = base / "valuation_inputs.json"
    if vi.exists():
        cur_vi = sha256_of(vi)
        if not status.get("inputs_sha256"):
            problems.append("质检登记未覆盖卡片数据 valuation_inputs.json（旧版登记）→ 重跑质检并重新 --record"
                            "（新登记会同时锁卡片指纹）")
        elif status.get("inputs_sha256") != cur_vi:
            problems.append("卡片数据 valuation_inputs.json 在质检登记后被改动过（指纹不符）"
                            "→ 卡片与报告可能不同步，需复核后重新 --record")

    # ⑤ 五道关全部 pass
    lines = status.get("lines", {})
    for k, name in LINES:
        v = lines.get(k)
        if v != "pass":
            problems.append(f"第「{name}」关未通过（当前：{v or '未登记'}）")

    if problems:
        return False, "；\n  ".join(problems)
    return True, f"五道质检关全部通过、章节卡完备、_thesis.md 在、指纹匹配（登记于 {status.get('recorded_at','?')}）"


def do_record(ticker: str, kvs, note: str):
    base = Path("analyses") / ticker.upper()
    report = find_report(base)
    if report is None:
        sys.exit(f"找不到 {base}/*完整报告.md")
    lines = {}
    for kv in kvs:
        if "=" not in kv:
            sys.exit(f"参数格式错误：{kv}（应为 键=pass/fail）")
        k, v = kv.split("=", 1)
        k = ALIASES.get(k.strip(), k.strip())
        if k not in LINE_KEYS:
            sys.exit(f"未知的质检关：{k}（应为 {sorted(LINE_KEYS)} 之一）")
        lines[k] = v.strip()
    vi = base / "valuation_inputs.json"
    status = {
        "report_file": report.name,
        "report_sha256": sha256_of(report),
        # O1（2026-07-05）：指纹同时盖住卡片数据源；decision.json 刻意不盖（状态结算属日常簿记）
        "inputs_sha256": sha256_of(vi) if vi.exists() else None,
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lines": lines,
        "note": note or "",
    }
    (base / "_qc_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = [n for k, n in LINES if lines.get(k) != "pass"]
    print(f"已登记 {report.name} 的质检结果（指纹 {status['report_sha256'][:12]}…）")
    if missing:
        print("  ⚠ 尚未全部通过：" + "、".join(missing) + " —— render_pdf 仍会拦下")
    else:
        print("  ✓ 五道关全部 pass")
    ch_ok, ch_problems = verify_chapters(ticker)
    if ch_ok:
        print("  ✓ 章节卡完备（判断卡 + 报告脚手架齐全）—— render_pdf 放行")
    else:
        print("  ⚠ 章节卡未完备（render_pdf 会一并拦下）：")
        for p in ch_problems:
            print("     · " + p)


def main():
    ap = argparse.ArgumentParser(description="报告交付硬闸门：不过质检关、出不来干净 PDF。")
    ap.add_argument("ticker")
    ap.add_argument("--record", nargs="+", metavar="关=pass/fail",
                    help="登记五道关结论，如 check_numbers=pass fact=pass discipline=pass depth=pass insight=pass")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.record:
        do_record(args.ticker, args.record, args.note)
        return
    ok, msg = verify_qc(args.ticker)
    print(("✓ 质检闸门：放行 —— " if ok else "✗ 质检闸门：拦下 —— ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
