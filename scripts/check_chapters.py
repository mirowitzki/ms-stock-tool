#!/usr/bin/env python3
"""
check_chapters.py —— 章节卡完备闸门：定了交付标准的章节，必须真的把判断卡填全、把脚手架写进报告，
否则不算合格交付。防的是"有标准不照做、以后股票偷懒跳过"。

来历（2026-06-28）：用户定了第一、二章在交互器里的交付标准（判断卡 + 正文脚手架）后明确要求
"保证以后的股票不会偷懒"。光写文档管不住执行（参照 qc_gate 同一条教训：终点是代码、不是自觉），
所以把"每章该出的卡和脚手架"做成代码校验，挂进 qc_gate 硬闸门（拦 PDF）、并在 render_explorer
渲染时当场报缺。

机制：
  - REQUIRED_CARDS 列出已定标准、必须出卡的章（随"一章一章定标准"逐章增长）。
  - 每张卡校验 valuation_inputs.json 对应块的必填字段非空（判断真的写了、不是空壳）。
  - CHAPTER_SCAFFOLDS 校验报告 .md 对应章含必需的结构脚手架（如第二章必含大事记表 + 总账表）。
  - 任一缺失 → 不合格；qc_gate 据此拦下 PDF、render_explorer 渲染时打印 ⚠。

只查"有没有照标准做"（卡填没填、表写没写），不评判断对不对——那是五道质检关的活。
"""
import json
import re
import sys
from pathlib import Path

# 已定交付标准、必须出判断卡的章。每新定一章标准就往这里加一条。
#   fields：该卡在 valuation_inputs.json 对应块里的必填路径（点号取嵌套；列表/字典按"非空"判）。
REQUIRED_CARDS = {
    "ch1": {
        "name": "第一章 业务质量判断卡",
        # 注：thesis 不列必填——卡里核心论点可来自 ch1.thesis 或报告的"核心论点/核心结论"（build_ch1_card 有 fallback）。
        "fields": ["essence", "quality.verdict", "moat", "evidence",
                   "steelman", "variant", "power_center", "segment_roles"],
    },
    "ch2": {
        "name": "第二章 历程判断卡",
        "fields": ["spine", "phases", "revealed_behavior", "darkline.text",
                   "scorecard_read.exposes", "scorecard_read.hidden_strength"],
    },
    "ch3": {
        "name": "第三章 行业判断卡",
        "fields": ["spine", "segments", "moat", "value_concentration", "pressure", "key_variable"],
    },
    "ch4": {
        "name": "第四章 经营判断卡（商业模式+游戏规则）",
        "fields": ["spine", "segments", "who_earns", "ceo_levers"],
    },
    "ch5": {
        "name": "第五章 资本配置记录卡",
        "fields": ["spine", "stage", "track_record", "per_share_verdict",
                   "for_whom.text", "verdict", "bear_case"],
    },
    "ch6": {
        "name": "第六章 治理判断卡",
        # controller_record 对控股型标的填跨主体记录；独立/无实控人公司可填"无控股股东·独立"。
        "fields": ["spine", "power_structure", "key_people", "controller_record",
                   "integrity_record", "verdict", "swing", "bear_case"],
    },
    "ch7": {
        "name": "第七章 财务判断卡",
        # value_ladder 是把第七章做深的核心（资产地板/按盈利折出的价值/分部加总/成长 + 诊断）。
        "fields": ["spine", "segment_earnings", "earnings_quality", "value_ladder",
                   "reverse_read", "survival", "verdict"],
    },
    "ch8": {
        "name": "第八章 投资决策卡",
        # 三情景/安全边际活数字在交互器顶部仪表盘+三情景滑块，卡刻意不重复情景表、只做判断综合。
        "fields": ["spine", "business_value", "safety", "asymmetry",
                   "catalysts", "verdict"],
    },
}

# 报告对应章必须含的结构脚手架（在该章正文里数 markdown 表格）。键＝章标题关键词。
CHAPTER_SCAFFOLDS = {
    "第二章": {"min_tables": 2, "desc": "大事记表 + 上市以来总账表"},
    "第三章": {"min_tables": 1, "desc": "竞争结构表"},
    "第四章": {"min_tables": 1, "desc": "三门生意总览表（本质/客户/怎么赢/赚不赚钱）"},
    "第五章": {"min_tables": 1, "desc": "收购成色表 或 资金去向表 或 每股记分牌表"},
    "第六章": {"min_tables": 1, "desc": "关键人背景背调表"},
    "第七章": {"min_tables": 1, "desc": "5年利润表总览表 或 价值阶梯表"},
    "第八章": {"min_tables": 1, "desc": "三情景表（情景/每股价值/概率/故事/关键前提）"},
}


def _get(d, path):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _nonempty(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def find_report(base):
    rs = sorted(base.glob("*完整报告.md"))
    return rs[0] if rs else None


def _count_tables_in_chapter(md_text, chapter_kw):
    """数 chapter_kw 那一章正文里的 markdown 表格数量（按表头分隔行 |---| 计）。
    兼容报告两种标题约定（# 第X章 一级 / ## 第X章 二级）：以第一个【以关键词开头】的标题层级为章级，
    数到下一个同级或更高级标题为止。用 startswith 而非 in——否则子标题里提到别的章名（如
    『7.7 小结：交给第八章的底子』含"第八章"）会被误当成那一章的开头、错数成 0 张表。"""
    in_chap, chap_level, count = False, None, 0
    for ln in md_text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", ln)
        if m:
            lvl, title = len(m.group(1)), m.group(2)
            if not in_chap:
                if title.startswith(chapter_kw):
                    in_chap, chap_level = True, lvl
            elif lvl <= chap_level:
                in_chap = False
            continue
        if in_chap and "|" in ln and re.match(r"^\s*\|?\s*:?-{3,}", ln):
            count += 1
    return count


def verify_chapters(ticker):
    """返回 (ok: bool, problems: list[str])。qc_gate 和 render_explorer 都调它。"""
    base = Path("analyses") / ticker.upper()
    problems = []

    vi_path = base / "valuation_inputs.json"
    if not vi_path.exists():
        return False, [f"缺 {vi_path}"]
    try:
        inputs = json.loads(vi_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"valuation_inputs.json 解析失败：{e}"]

    # ① 每张必出的判断卡：块在、必填字段非空
    for key, spec in REQUIRED_CARDS.items():
        block = inputs.get(key)
        if not block:
            problems.append(f"缺『{spec['name']}』判断块（valuation_inputs.json 的 \"{key}\"）"
                            f"——这章已定交付标准、必须出卡")
            continue
        miss = [f for f in spec["fields"] if not _nonempty(_get(block, f))]
        if miss:
            problems.append(f"『{spec['name']}』字段未填全：{key} 缺 {', '.join(miss)}")

    # ② 报告对应章的结构脚手架（表格数量）
    report = find_report(base)
    if report is None:
        problems.append("找不到 *完整报告.md")
    else:
        md = report.read_text(encoding="utf-8")
        for kw, spec in CHAPTER_SCAFFOLDS.items():
            n = _count_tables_in_chapter(md, kw)
            if n < spec["min_tables"]:
                problems.append(f"报告『{kw}』缺结构脚手架：需含 {spec['desc']}"
                                f"（应 ≥{spec['min_tables']} 张表，实测 {n} 张）")

    return (not problems), problems


def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python scripts/check_chapters.py <代码>")
    ticker = sys.argv[1]
    ok, problems = verify_chapters(ticker)
    if ok:
        names = "、".join(REQUIRED_CARDS[k]["name"] for k in REQUIRED_CARDS)
        print(f"✓ 章节卡完备：{ticker.upper()} 已定标准的章（{names}）卡与脚手架齐全")
        sys.exit(0)
    print(f"✗ 章节卡不完备：{ticker.upper()}")
    for p in problems:
        print("  - " + p)
    sys.exit(1)


if __name__ == "__main__":
    main()
