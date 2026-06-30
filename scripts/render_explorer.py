#!/usr/bin/env python3
"""
render_explorer.py —— 为指定股票生成专属的价值分析交互器 HTML。

读取：
  - analyses/<TICKER>/financials/financials.csv     历史财务（自动）
  - analyses/<TICKER>/valuation_inputs.json         情景假设（必需，可由 starter 生成）
  - tools/valuation_explorer.html                    通用模板

写入：
  - analyses/<TICKER>/valuation_explorer.html       专属交互器

用法：
  python scripts/render_explorer.py RKLB

如果不存在 valuation_inputs.json，加 --starter 参数生成一份"占位"版本，
然后手动调整后再跑一次：
  python scripts/render_explorer.py RKLB --starter
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _find_pandoc():
    """定位 pandoc（把报告 Markdown 转成 HTML 片段嵌进交互器用；与 render_pdf 同一渲染器、口径一致）。"""
    found = shutil.which("pandoc")
    if found:
        return found
    import os
    for p in (
        r"C:\Program Files\Pandoc\pandoc.exe",
        r"C:\Users\%s\AppData\Local\Pandoc\pandoc.exe" % os.environ.get("USERNAME", ""),
    ):
        if Path(p).exists():
            return p
    return None


# 把 SEC XBRL 原始美元（10 亿级整数）规范化成"百万美元"，便于人类阅读
def to_millions(v):
    if v is None:
        return None
    return round(v / 1_000_000, 2)


def load_financials_csv(ticker):
    path = Path("analyses") / ticker.upper() / "financials" / "financials.csv"
    if not path.exists():
        return {}
    data = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                fy = int(row["fiscal_year"])
                val = float(row["value"])
            except (ValueError, TypeError):
                continue
            data.setdefault(row["concept"], {})[fy] = val
    return data


def load_metrics(ticker):
    """读 financials/metrics.json（价值判断四柱真相源）。没有就返回 None（交互器隐藏仪表盘）。"""
    path = Path("analyses") / ticker.upper() / "financials" / "metrics.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_prices(ticker):
    """读 financials/prices.json（近 5 年月度收盘价）。没有就返回 None（交互器隐藏股价图）。"""
    path = Path("analyses") / ticker.upper() / "financials" / "prices.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("prices")
    except Exception:
        return None


def load_quote(ticker):
    """读 analyses/_quotes.json 里这只票的最新收盘报价（refresh_quotes.py 产出）。没有就返回 None。"""
    path = Path("analyses") / "_quotes.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("quotes", {}).get(ticker.upper())
    except Exception:
        return None


def load_layout(ticker):
    """读 layout.json（产业布局雷达：近期布局动作 + 推断指向的产业），喂交互器的布局雷达区。
    没有就返回 None（交互器自动隐藏该区）。由分析时写 / explorer-updater 联网刷新。"""
    path = Path("analyses") / ticker.upper() / "layout.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_decision(ticker):
    """读 decision.json 的时间线相关字段（催化剂预测 / 复盘日 / 入场观察区），喂交互器的催化剂时间线。
    没有就返回 None（交互器隐藏时间线）。判断内核不动、只取可证伪预测的日期与阈值。"""
    path = Path("analyses") / ticker.upper() / "decision.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    preds = [{k: p.get(k) for k in
              ("id", "claim", "metric", "threshold", "check_by", "source", "scenario_link", "status")}
             for p in (d.get("predictions") or [])]
    return {
        "date": d.get("date"),
        "review_by": d.get("review_by"),
        "entry_watch": d.get("entry_watch"),
        "predictions": preds,
    }


def _strip_exec_summary(body):
    """去掉章内的"执行摘要"小节(## 或 ### 级都认)——执行摘要已由章首判断卡承担、正文里重复。
    从"执行摘要"标题起跳过，直到遇到同级或更高级的下一个标题为止。只改交互器渲染、不动报告 .md 源。"""
    out, skip_level = [], None
    for ln in body.split("\n"):
        m = re.match(r"^(#{2,4})\s+(.+?)\s*$", ln)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if skip_level is None and title.startswith("执行摘要"):
                skip_level = level
                continue
            if skip_level is not None and level <= skip_level:
                skip_level = None
        if skip_level is None:
            out.append(ln)
    return "\n".join(out).strip()


def load_report_chapters(ticker):
    """把 <TICKER>_公司完整报告.md 按章拆开、各自用 pandoc 转 HTML 片段，返回 (chapters, thesis_html)。
    - chapters：[{id, title, html}, ...]，喂交互器按章嵌入的正文（已剔除导读/执行摘要/核心论点）。
    - thesis_html：核心论点那段的 HTML，喂第一章判断卡（"核心论点进卡片"）。

    报告 Markdown 仍是唯一正文真相源；这里只做渲染层转换，与 render_pdf 同一个 pandoc、口径一致。
    找不到报告 / 没有 pandoc → 返回 (None, None)（交互器自动隐藏正文区）。
    """
    base = Path("analyses") / ticker.upper()
    mds = sorted(base.glob("*完整报告.md"))
    if not mds:
        return None, None
    pandoc = _find_pandoc()
    if not pandoc:
        print("  ⚠ 找不到 pandoc，跳过报告正文嵌入（交互器其余部分照常）。")
        return None, None

    def md2html(md):
        if not (md or "").strip():
            return ""
        try:
            r = subprocess.run(
                [pandoc, "-f", "markdown-auto_identifiers", "-t", "html5"],
                input=md, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0:
                # 去掉 pandoc 给表格塞的等宽 <colgroup>（它按分隔行 --- 等长把每列锁成等宽，
                # 长文本列被挤窄换行、短列留大片白）；去掉后由 CSS(table-layout:auto + width:100%)
                # 按内容分配列宽——长列自然变宽、短列收紧。
                return re.sub(r"<colgroup>.*?</colgroup>", "", r.stdout, flags=re.S)
            print(f"  ⚠ pandoc 转换失败：{r.stderr.strip()[:120]}")
        except Exception as e:
            print(f"  ⚠ pandoc 转换异常：{e}")
        return ""

    lines = mds[0].read_text(encoding="utf-8").splitlines()

    # 报告标题层级不统一：有的用 # 第X章(一级)、有的用 ## 第X章(二级、一级只留给报告名)。
    n_h1 = sum(1 for l in lines if re.match(r"^# (?!#)", l))
    chap_re = re.compile(r"^# (?!#)(.+?)\s*$") if n_h1 >= 3 else re.compile(r"^## (?!#)(.+?)\s*$")

    chapters, preface = [], []
    cur_title, cur_body = None, []
    for ln in lines:
        m = chap_re.match(ln)
        if m:
            if cur_title is not None:
                chapters.append([cur_title, "\n".join(cur_body).strip()])
            cur_title, cur_body = m.group(1).strip(), []
        elif cur_title is not None:
            cur_body.append(ln)
        else:
            preface.append(ln)
    if cur_title is not None:
        chapters.append([cur_title, "\n".join(cur_body).strip()])
    if not chapters:
        return None, None

    # 抽出"核心论点"做判断卡的 thesis；丢掉无意义的导读/前言/元信息段（分析时点·口径声明这类）。
    thesis_md = None
    if n_h1 >= 3:
        # 一级模式：首章是报告名(# XX完整报告)、正文含元信息 + ## 核心论点/核心结论；抽出来、整章移除。
        m_core = re.search(r"(?m)^##\s*核心(论点|结论)[^\n]*$", chapters[0][1])
        if m_core:
            thesis_md = chapters[0][1][m_core.end():].strip()
        chapters.pop(0)
    else:
        # 二级模式：核心论点/核心结论 是独立的 ## 章，抽出来；# 报告名 + 元信息前言已落在 preface、自然丢弃。
        for i, (title, body) in enumerate(chapters):
            if title.startswith("核心论点") or title.startswith("核心结论"):
                thesis_md = body.strip()
                chapters.pop(i)
                break

    # 每章去掉"执行摘要"小节——执行摘要已由判断卡承担（报告 .md 源不动、PDF 仍保留）
    for ch in chapters:
        ch[1] = _strip_exec_summary(ch[1])
    chapters = [c for c in chapters if c[1].strip()]

    out = [{"id": f"ch-{i}", "title": t, "html": md2html(b)} for i, (t, b) in enumerate(chapters)]
    return (out or None), (md2html(thesis_md) or None)


def build_ch1_card(inputs, base, thesis_html):
    """组装第一章判断卡数据：数字(各业务营收/占比/毛利/同比)来自 segments.json，
    判断(本质/光谱位置/护城河/证据/最强多头/认知差/钱权重心/各业务角色)来自 valuation_inputs.json 的 ch1 块，
    核心论点来自报告 markdown(thesis_html)。没有 ch1 块就返回 None（卡片自动隐藏）。"""
    ch1 = inputs.get("ch1")
    if not ch1:
        return None
    rows = []
    seg_path = base / "financials" / "segments.json"
    if seg_path.exists():
        try:
            data = json.loads(seg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        roles = ch1.get("segment_roles", {})
        # 可选 segment_dim 强制用某维度（如 600327 用 by_industry 才干净）；否则按默认顺序取第一个有数的
        dims = [ch1["segment_dim"]] if ch1.get("segment_dim") else ["by_product", "by_industry", "by_market", "by_region"]
        for key in dims:
            grp = data.get(key) or {}
            annual = sorted(p for p in grp if str(p).endswith("12-31")) or sorted(grp.keys())
            if not annual:
                continue
            cur = [s for s in grp[annual[-1]] if (s.get("revenue") or 0) > 0]  # 跳过抵消等非正项
            if not cur:
                continue
            prev = {s.get("name"): s.get("revenue")
                    for s in (grp[annual[-2]] if len(annual) >= 2 else [])}
            total = sum(s.get("revenue") or 0 for s in cur)  # 占比按主营全口径算（含未单列的残差），分母诚实
            for s in cur:
                name, rev = s.get("name"), (s.get("revenue") or 0)
                if name not in roles:  # 只显示我打了角色判断的业务；残差/补充项不进表
                    continue
                r = roles[name]
                yoy = round((rev / prev[name] - 1) * 100, 1) if prev.get(name) else None
                rows.append({
                    "name": name, "revenue": to_millions(rev),
                    "pct": round(rev / total * 100, 1) if total else None,
                    "margin": round(s["margin"] * 100, 1) if s.get("margin") is not None else None,
                    "yoy": yoy, "source": r.get("source", ""),
                    "role": r.get("role", ""), "kind": r.get("kind", ""),
                })
            break
    # 卡片里的核心论点：优先用 ch1.thesis（我写的精炼版），否则用从报告抽出的核心论点/核心结论
    thesis_out = ("<p>" + ch1["thesis"] + "</p>") if ch1.get("thesis") else (thesis_html or "")
    return {
        "essence": ch1.get("essence", ""),
        "thesis_html": thesis_out,
        "quality": ch1.get("quality", {}),
        "moat": ch1.get("moat", ""),
        "evidence": ch1.get("evidence", ""),
        "steelman": ch1.get("steelman", ""),
        "variant": ch1.get("variant", ""),
        "power_center": ch1.get("power_center", ""),
        "segments": rows,
    }


def build_ch2_card(inputs, fin):
    """组装第二章历程判断卡：判断（脊梁/四段时间轴/行为模式/暗线/双面判读/峰值坐标）来自
    valuation_inputs.json 的 ch2 块，总账速览（多年营收/归母/经营现金流）由代码从 financials.csv
    算（复用 build_history）。没有 ch2 块就返回 None（卡片自动隐藏）。"""
    ch2 = inputs.get("ch2")
    if not ch2:
        return None
    cfo_keys = ["NetCashProvidedByUsedInOperatingActivities"]
    rows = []
    for h in build_history(fin):
        if h.get("revenue") is None and h.get("net_income") is None:
            continue
        y = h["year"]
        cfo = next((fin[k][y] for k in cfo_keys if k in fin and y in fin[k]), None)
        rows.append({
            "year": y,
            "revenue": h.get("revenue"),       # 已是百万本币（build_history 里 to_millions 过）
            "net_income": h.get("net_income"),
            "cfo": to_millions(cfo) if cfo is not None else None,
        })
    return {
        "spine": ch2.get("spine", ""),
        "phases": ch2.get("phases", []),
        "revealed_behavior": ch2.get("revealed_behavior", ""),
        "darkline": ch2.get("darkline", {}),
        "peak_anchor": ch2.get("peak_anchor", ""),
        "scorecard_read": ch2.get("scorecard_read", {}),
        "scorecard": rows[-6:],                # 最近 6 个年度，避免铺满 20 余年历史
    }


def build_ch3_card(inputs, base):
    """组装第三章行业判断卡：竞争结构地图的营收/占比由代码从 segments.json 算（复用第一章那套机制），
    竞争判断（行业/结构/位置/谁掌握价值/市场往哪走）来自 valuation_inputs.json 的 ch3 块。
    没有 ch3 块就返回 None（卡片自动隐藏）。门道细节留在正文，卡片只做精炼的判断速览。"""
    ch3 = inputs.get("ch3")
    if not ch3:
        return None
    segs = ch3.get("segments", {})
    rows = []
    seg_path = base / "financials" / "segments.json"
    if seg_path.exists():
        try:
            data = json.loads(seg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        dims = [ch3["segment_dim"]] if ch3.get("segment_dim") else ["by_industry", "by_product", "by_market", "by_region"]
        for key in dims:
            grp = data.get(key) or {}
            annual = sorted(p for p in grp if str(p).endswith("12-31")) or sorted(grp.keys())
            if not annual:
                continue
            cur = [s for s in grp[annual[-1]] if (s.get("revenue") or 0) > 0]
            if not cur:
                continue
            total = sum(s.get("revenue") or 0 for s in cur)
            for s in cur:
                name, rev = s.get("name"), (s.get("revenue") or 0)
                if name not in segs:            # 只显示我打了竞争判断的业务
                    continue
                j = segs[name]
                rows.append({
                    "name": name, "revenue": to_millions(rev),
                    "pct": round(rev / total * 100, 1) if total else None,
                    "industry": j.get("industry", ""), "structure": j.get("structure", ""),
                    "position": j.get("position", ""), "kind": j.get("kind", ""),
                    "control": j.get("control", ""), "control_kind": j.get("control_kind", ""),
                    "control_note": j.get("control_note", ""), "market": j.get("market", ""),
                })
            break
    return {
        "spine": ch3.get("spine", ""),
        "moat": ch3.get("moat", ""),
        "value_concentration": ch3.get("value_concentration", ""),
        "pressure": ch3.get("pressure", ""),
        "key_variable": ch3.get("key_variable", ""),
        "segments": rows,
    }


def build_ch4_card(inputs, base):
    """组装第四章经营判断卡（商业模式 + 游戏规则，CEO 经营说明书视角）：每门生意的营收/占比由代码从
    segments.json 算（同第一/三章机制），本质/怎么玩/赚不赚钱/谁真赚钱/CEO 操作杆来自 valuation_inputs.json
    的 ch4 块。没有 ch4 块就返回 None（卡片自动隐藏）。财务报表分析不在本章、在第七章。"""
    ch4 = inputs.get("ch4")
    if not ch4:
        return None
    segs = ch4.get("segments", {})
    rows = []
    seg_path = base / "financials" / "segments.json"
    if seg_path.exists():
        try:
            data = json.loads(seg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        dims = [ch4["segment_dim"]] if ch4.get("segment_dim") else ["by_industry", "by_product", "by_market", "by_region"]
        for key in dims:
            grp = data.get(key) or {}
            annual = sorted(p for p in grp if str(p).endswith("12-31")) or sorted(grp.keys())
            if not annual:
                continue
            cur = [s for s in grp[annual[-1]] if (s.get("revenue") or 0) > 0]
            if not cur:
                continue
            total = sum(s.get("revenue") or 0 for s in cur)
            for s in cur:
                name, rev = s.get("name"), (s.get("revenue") or 0)
                if name not in segs:            # 只显示我打了盈利角色的业务
                    continue
                j = segs[name]
                rows.append({
                    "name": name, "revenue": to_millions(rev),
                    "pct": round(rev / total * 100, 1) if total else None,
                    "essence": j.get("essence", ""), "play": j.get("play", ""),
                    "role": j.get("role", ""), "role_kind": j.get("role_kind", ""),
                })
            break
    return {
        "spine": ch4.get("spine", ""),
        "who_earns": ch4.get("who_earns", ""),
        "ceo_levers": ch4.get("ceo_levers", ""),
        "segments": rows,
    }


def build_ch5_card(inputs, fin):
    """组装第五章资本配置记录卡：判断（脊梁/阶段诊断/资金来去/大决策剖检/分红轨迹/为谁配置/激励/分级结论/
    最强反方）来自 valuation_inputs.json 的 ch5 块；每股记分牌里的归母、经营现金流两行由代码从 financials.csv
    算（÷ 总股本），扣非、分红两行因不在 XBRL 里、由 ch5 块手工供（已对年报核）。没有 ch5 块就返回 None。"""
    ch5 = inputs.get("ch5")
    if not ch5:
        return None
    shares = ch5.get("shares")                                              # 总股本（股）
    years = ch5.get("years") or []
    deps = {int(k): v for k, v in (ch5.get("deducted_eps") or {}).items()}  # 扣非每股（手抄·已核）
    dps = {int(k): v for k, v in (ch5.get("dividend_ps") or {}).items()}    # 每股分红（手抄·已核）
    ni = fin.get("NetIncomeLoss", {})
    cfo = fin.get("NetCashProvidedByUsedInOperatingActivities", {})
    def ps(v):
        return round(v / shares, 2) if (v is not None and shares) else None
    rows = [{
        "year": y,
        "eps": ps(ni.get(y)),          # 归母每股（代码算）
        "deducted_eps": deps.get(y),   # 扣非每股（手抄）
        "cfo_ps": ps(cfo.get(y)),      # 经营现金流每股（代码算）
        "div_ps": dps.get(y),          # 每股分红（手抄）
    } for y in years]
    return {
        "spine": ch5.get("spine", ""),
        "stage": ch5.get("stage", ""),
        "sources_uses": ch5.get("sources_uses", ""),
        "track_record": ch5.get("track_record", []),
        "dividend_arc": ch5.get("dividend_arc", {}),
        "per_share": rows,
        "per_share_verdict": ch5.get("per_share_verdict", ""),
        "shares_yi": round(shares / 1e8, 2) if shares else None,
        "for_whom": ch5.get("for_whom", {}),
        "incentive": ch5.get("incentive", ""),
        "verdict": ch5.get("verdict", ""),
        "bear_case": ch5.get("bear_case", ""),
    }


def build_ch6_card(inputs):
    """组装第六章治理判断卡：能不能信任掌控公司的人——权力结构 / 关键人背景背调 / 控股股东跨主体记录 /
    诚信记录 / 分级结论 / 胜负手 / 最强反方，全部来自 valuation_inputs.json 的 ch6 块。这一章研究/判断
    密集、几乎没有可由代码计算的结构化数据（无 segments / 财务那种），背调与治理记录全由人第一手从年报+
    公开工商/监管/裁判文书挖，故代码只做透传。没有 ch6 块就返回 None（卡片自动隐藏）。"""
    ch6 = inputs.get("ch6")
    if not ch6:
        return None
    return {
        "spine": ch6.get("spine", ""),
        "power_structure": ch6.get("power_structure", ""),
        "key_people": ch6.get("key_people", []),
        "controller_record": ch6.get("controller_record", ""),
        "integrity_record": ch6.get("integrity_record", ""),
        "verdict": ch6.get("verdict", ""),
        "swing": ch6.get("swing", ""),
        "bear_case": ch6.get("bear_case", ""),
    }


def build_ch7_card(inputs, fin, metrics):
    """组装第七章财务判断卡：利润表透视（营收/归母/营业利润/投资收益/资本回报率）由代码从 financials.csv +
    metrics 算（扣非不在 XBRL 里、由 ch7 块手工供、已核年报）；价值阶梯诊断/分部盈利真相/盈利质量与会计可信度/
    反向体质画像/交底第八章＝我写进 ch7 块。这章代码供数最多（四柱硬数字另在顶部仪表盘）。没有 ch7 块返回 None。"""
    ch7 = inputs.get("ch7")
    if not ch7:
        return None
    years = ch7.get("years") or []
    ded = {int(k): v for k, v in (ch7.get("deducted") or {}).items()}   # 扣非（亿，手抄·已核）
    rev = fin.get("Revenues", {})
    ni = fin.get("NetIncomeLoss", {})
    op = fin.get("OperatingIncomeLoss", {})
    iv = fin.get("InvestmentIncome", {})
    roic = {}
    try:
        for r in (metrics or {}).get("metrics", {}).get("compounding_engine", {}).get("roic_series", []):
            roic[r["fy"]] = r["roic"]
    except Exception:
        pass
    def yi(v):
        return round(v / 1e8, 2) if v is not None else None
    rows = [{
        "year": y,
        "revenue": yi(rev.get(y)),         # 营收（亿，代码）
        "net_income": yi(ni.get(y)),       # 归母（亿，代码）
        "deducted": ded.get(y),            # 扣非（亿，手抄）
        "op_income": yi(op.get(y)),        # 营业利润（亿，代码）
        "invest_income": yi(iv.get(y)),    # 投资收益（亿，代码）
        "roic": round(roic[y] * 100, 1) if y in roic else None,  # 资本回报率（代码）
    } for y in years]
    return {
        "spine": ch7.get("spine", ""),
        "pl_table": rows,
        "pl_read": ch7.get("pl_read", ""),
        "segment_earnings": ch7.get("segment_earnings", ""),
        "earnings_quality": ch7.get("earnings_quality", ""),
        "value_ladder": ch7.get("value_ladder", {}),
        "survival": ch7.get("survival", ""),
        "reverse_read": ch7.get("reverse_read", ""),
        "verdict": ch7.get("verdict", ""),
    }


def build_ch8_card(inputs):
    """组装第八章投资决策卡（整份报告的收口 capstone）：作为生意值多少 + 安全边际/市场买了什么 + 不对称性 +
    催化剂 + 决策，全部来自 valuation_inputs.json 的 ch8 块。三情景/安全边际/反向DCF 的活数字已在交互器顶部
    的仪表盘、三情景滑块、市场vs我里（**这张卡刻意不重复情景表**），只做判断综合。没有 ch8 块就返回 None。"""
    ch8 = inputs.get("ch8")
    if not ch8:
        return None
    return {
        "spine": ch8.get("spine", ""),
        "business_value": ch8.get("business_value", ""),
        "safety": ch8.get("safety", ""),
        "asymmetry": ch8.get("asymmetry", {}),
        "catalysts": ch8.get("catalysts", []),
        "verdict": ch8.get("verdict", ""),
    }


def build_ch9_card(inputs):
    """组装第九章风险判断卡：风险脊梁 + 排序的风险矩阵（每条 等级/已被定价/盯什么）+ 事前验尸（往下错/往上错）
    + 净风险画像与监控清单，全部来自 valuation_inputs.json 的 ch9 块。风险全景是判断密集、代码不供数（透传）。
    没有 ch9 块就返回 None（卡片自动隐藏）。"""
    ch9 = inputs.get("ch9")
    if not ch9:
        return None
    return {
        "spine": ch9.get("spine", ""),
        "top_risks": ch9.get("top_risks", []),
        "premortem": ch9.get("premortem", {}),
        "verdict": ch9.get("verdict", ""),
    }


def build_history(fin):
    """从财务数据提取年度历史，返回按年份排序的 list。"""
    revenue_keys = [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ]
    gross_keys = ["GrossProfit"]
    op_keys = ["OperatingIncomeLoss"]
    ni_keys = ["NetIncomeLoss", "ProfitLoss"]
    cfo_keys = ["NetCashProvidedByUsedInOperatingActivities"]
    capex_keys = ["PaymentsToAcquirePropertyPlantAndEquipment"]

    def first_val(keys, year):
        for k in keys:
            if k in fin and year in fin[k]:
                return fin[k][year]
        return None

    all_years = set()
    for k_list in (revenue_keys, op_keys, ni_keys, cfo_keys):
        for k in k_list:
            if k in fin:
                all_years.update(fin[k].keys())

    history = []
    for y in sorted(all_years):
        rev = first_val(revenue_keys, y)
        gross = first_val(gross_keys, y)
        op = first_val(op_keys, y)
        ni = first_val(ni_keys, y)
        cfo = first_val(cfo_keys, y)
        capex = first_val(capex_keys, y)
        fcf = (cfo - capex) if (cfo is not None and capex is not None) else None
        history.append({
            "year": y,
            "revenue": to_millions(rev),
            "gross_profit": to_millions(gross),
            "operating_income": to_millions(op),
            "net_income": to_millions(ni),
            "fcf": to_millions(fcf),
        })
    return history


# 利润表科目映射：A 股精确 concept（fetch_a_stocks 落库）+ 美股 XBRL 兜底 key。
# 用于"最新年报利润表流向图"。每组取第一个命中的。
INCOME_CONCEPTS = {
    "revenue":    ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "cost":       ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross":      ["GrossProfit"],
    "selling":    ["SellingExpense"],
    "admin":      ["GeneralAndAdministrativeExpense"],
    "rnd":        ["ResearchAndDevelopmentExpense"],
    "taxsur":     ["TaxesAndSurcharges"],
    "finance":    ["FinanceExpense"],
    "operating":  ["OperatingIncomeLoss"],
    "pretax":     ["IncomeLossBeforeIncomeTaxes"],
    "net":        ["NetIncomeLossTotal", "NetIncomeLoss", "ProfitLoss"],
    "net_parent": ["NetIncomeLoss", "ProfitLoss"],
}


def build_income_statement(fin):
    """构建"最新一期年报"的利润表瀑布步骤（值单位=百万本币，与 history/facts 一致）。

    返回 {year, steps:[{label,kind,value,running,pct,...}], revenue, net_income, ...}。
    数据不足（缺营收或净利）时返回 None——此时交互器自动隐藏该模块。

    设计要点（诚实可对账）：
      - start=营业总收入，final=净利润，中间每一步都按真实科目扣减/加回；
      - "营业利润"前用一个"投资收益及其他(净)"残差桶精确对到营业利润，
        所得税步用 (税前 − 净利) 兜平，保证首尾与三大节点严格勾稽。
    """
    rev_years = set()
    for k in INCOME_CONCEPTS["revenue"]:
        if k in fin:
            rev_years.update(fin[k].keys())
    if not rev_years:
        return None
    year = max(rev_years)

    def val(group):
        for k in INCOME_CONCEPTS[group]:
            if k in fin and year in fin[k]:
                v = fin[k][year]
                if v is None:
                    continue
                try:
                    if v != v:  # NaN
                        continue
                except TypeError:
                    continue
                return to_millions(v)
        return None

    rev = val("revenue")
    net = val("net")
    if rev is None or net is None or rev <= 0:
        return None

    op = val("operating")
    cost = val("cost"); selling = val("selling"); admin = val("admin")
    rnd = val("rnd"); taxsur = val("taxsur"); finance = val("finance")
    pretax = val("pretax"); net_parent = val("net_parent")

    steps = []

    def push(label, kind, value, running, **extra):
        s = {"label": label, "kind": kind,
             "value": round(value, 2), "running": round(running, 2),
             "pct": round(value / rev * 100, 1)}
        s.update(extra)
        steps.append(s)

    running = rev
    push("营业总收入", "start", rev, running)

    for label, v in [("营业成本", cost), ("销售费用", selling), ("管理费用", admin),
                     ("研发费用", rnd), ("税金及附加", taxsur)]:
        if v is None:
            continue
        running -= v
        push(label, "out", v, running)

    if finance is not None:
        if finance >= 0:
            running -= finance
            push("财务费用", "out", finance, running)
        else:
            running += -finance
            push("财务费用", "in", -finance, running, note="财务费用为负=净利息收入冲减")

    if op is not None:
        resid = op - running
        if abs(resid) >= 0.5:  # ≥50 万才单独画一桶
            push("投资收益及其他(净)", "in" if resid >= 0 else "out", abs(resid), op,
                 note="投资收益、公允价值变动、其他收益、资产处置、减值损失等的净额")
        running = op
        push("营业利润", "subtotal", op, running)

    # 营业利润 → 利润总额（营业外及其他）
    if pretax is not None and op is not None and abs(pretax - op) >= 0.5:
        d = pretax - op
        running = pretax
        push("营业外及其他(净)", "in" if d >= 0 else "out", abs(d), running)

    # → 净利润（所得税等，用差额兜平到净利）
    tax_like = running - net
    tax_label = "所得税" if pretax is not None else "所得税及其他"
    if abs(tax_like) >= 0.5:
        push(tax_label, "out" if tax_like >= 0 else "in", abs(tax_like), net)
    push("净利润", "final", net, net)

    return {
        "year": year,
        "steps": steps,
        "revenue": round(rev, 2),
        "operating_income": round(op, 2) if op is not None else None,
        "net_income": round(net, 2),
        "net_income_parent": round(net_parent, 2) if net_parent is not None else None,
    }


def _seg_latest_annual(base):
    """读 segments.json，返回 (period, [seg...])：按产品优先、按行业兜底，取最新的年度(12-31)期。"""
    seg_path = base / "financials" / "segments.json"
    if not seg_path.exists():
        return None, None, None
    try:
        data = json.loads(seg_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None
    # 优先业务维度(产品/行业/终端市场)；都没有时才退回地区(单一产品线公司如 SITM 只披露地区)
    for key, dim in (("by_product", "按产品"), ("by_industry", "按行业"), ("by_market", "按终端市场"), ("by_region", "按地区")):
        grp = data.get(key) or {}
        annual = sorted(p for p in grp if str(p).endswith("12-31"))
        # A 股财年=日历年(取 12-31 年度期)；美股财年常非日历年(如 9/10 月结)，退回取最新一期
        periods = annual or sorted(grp.keys())
        if periods:
            period = periods[-1]
            segs = [s for s in grp[period] if s.get("revenue")]
            if segs:
                return period, dim, segs
    return None, None, None


def _build_sankey_loss(year, rev, net, op, cost, sell, admin, rnd, taxsur,
                       finance, G, seg_period, seg_dim, segs, nodes, links,
                       node, link):
    """亏损 / 不规则利润的资金流向桑基图（用红色虚线诚实表示"净亏损"，流量守恒不崩）。

    模型：左侧"资金来源" → 中枢"全年总支出" → 右侧"资金去向"。
      来源 = 营业收入(实线) + 净亏损(红色虚线·自有资金弥补) [+ 净利息收入/投资收益等]
      去向 = 营业成本 + 各项费用 + 其他营业费用·损益(净) [+ 营业外支出及税(净)] [+ 净利润]
    用 max(0,·) 把每一项按正负号路由到来源或去向，再用一只"残差桶"兜平，
    保证 left==right（代数恒等，对任意盈亏符号都成立）。美股缺销管明细时，
    "其他营业费用(含销管等,净)"这只桶把营业层缺口补齐、让瀑布闭合。
    """
    sources, sinks = [], []  # 每项 (id, label, value, kind)
    sources.append(("rev", "营业收入", rev, "revenue"))
    if net < 0:
        sources.append(("netloss", "净亏损·自有资金弥补", -net, "loss"))

    sinks.append(("cost", "营业成本", cost, "cost"))
    opex = []
    for lid, label, val in [("sell", "销售费用", sell), ("admin", "管理费用", admin),
                            ("rnd", "研发费用", rnd), ("taxsur", "税金及附加", taxsur)]:
        if val and val > 0:
            opex.append((lid, label, val, "expense"))
    if finance is not None and finance > 0:
        opex.append(("finance", "财务费用", finance, "expense"))
    elif finance is not None and finance < 0:  # 财务费用为负=净利息收入，是资金来源
        sources.append(("fininc", "净利息收入", -finance, "external"))
    sinks.extend(opex)
    E = sum(x[2] for x in opex)

    has_detail_opex = (sell is not None) or (admin is not None)
    non_op = None
    if op is not None:
        op_resid = G - E - op   # 营业层其他净损益（美股=缺失的销管；A股=减值/资产处置/其他）
        non_op = net - op       # 营业利润→净利润的桥（营业外 + 投资收益(美股) + 所得税）
        if op_resid > 0.5:
            lbl = "其他经营损益(净)" if has_detail_opex else "其他营业费用(含销管等,净)"
            sinks.append(("opresid", lbl, op_resid, "expense"))
        elif op_resid < -0.5:
            sources.append(("opgain", "其他经营收益(净)", -op_resid, "external"))
        if non_op > 0.5:
            sources.append(("nonop", "投资收益及其他(净)", non_op, "external"))
        elif non_op < -0.5:
            sinks.append(("nonopsink", "营业外支出及所得税(净)", -non_op, "expense"))

    if net > 0:  # 仅营业亏损但整体盈利：净利润作为正向流出
        sinks.append(("netprofit", "净利润", net, "net"))

    # 兜底兜平（op 缺失或残余漂移都靠这一桶归零，保证严格守恒：left==right）
    drift = round(sum(x[2] for x in sources) - sum(x[2] for x in sinks), 2)
    if drift > 0.5:
        sinks.append(("resid", "其他费用及税(净)", drift, "expense"))
    elif drift < -0.5:
        sources.append(("residsrc", "其他收益(净)", -drift, "external"))

    T = round(sum(x[2] for x in sources), 2)  # 全年总支出 = 全部来源 = 全部去向

    # ---- 左：业务板块（有 segments.json 才画，A股）----
    if segs:
        conv = []
        for s in segs:
            srev = to_millions(s.get("revenue")) or 0.0
            conv.append({"name": s.get("name"), "rev": srev, "margin": s.get("margin")})
        conv.sort(key=lambda c: c["rev"], reverse=True)
        sum_rev = sum(c["rev"] for c in conv)
        if rev - sum_rev > rev * 0.005:  # 残差段（占营收>0.5%才单列）
            conv.append({"name": "其他业务", "rev": rev - sum_rev, "margin": None})
        for i, c in enumerate(conv):
            mpct = round(c["margin"] * 100, 1) if c.get("margin") is not None else None
            node(f"seg{i}", 0, c["name"], c["rev"], "segment", order=i, margin=mpct)
            link(f"seg{i}", "rev", c["rev"])

    # ---- 中：资金来源（col 1）→ 全年总支出枢纽（col 2）----
    for i, (sid, label, val, kind) in enumerate(sources):
        extra = {"note": "营收覆盖不了的开支，由自有资金/历史积累弥补"} if kind == "loss" else {}
        node(sid, 1, label, val, kind, order=i, **extra)
        link(sid, "hub", val, kind=("loss" if kind == "loss" else None))
    node("hub", 2, "全年总支出", T, "flow", order=0,
         note="营业收入 + 净亏损(自有资金) = 全部成本费用，共同覆盖右侧全部开支")

    # ---- 右：资金去向（col 3）----
    for i, (kid, label, val, kind) in enumerate(sinks):
        node(kid, 3, label, val, kind, order=i)
        link("hub", kid, val)

    return {
        "year": year,
        "seg_period": seg_period,
        "seg_dim": seg_dim,
        "is_loss": net < 0,
        "nodes": nodes,
        "links": links,
        "totals": {
            "revenue": round(rev, 2),
            "gross": round(G, 2),
            "operating_income": round(op, 2) if op is not None else None,
            "net_income": round(net, 2),
            "invest_other": round(max(non_op, 0.0), 2) if non_op is not None else 0.0,
        },
    }


def build_sankey(fin, base):
    """构建"业务板块 → 利润流向"桑基图数据（值=百万本币）。数据不足返回 None。

    左：各业务板块（按产品/行业拆）→ 营业收入；
    右：营收 → 成本/毛利 → 各项费用/营业利润（+投资收益等外部净流入）→ 净利润。
    每个节点用流量守恒约束 + 残差兜平，保证 Sankey 不漏不溢。
    """
    rev_years = set()
    for k in INCOME_CONCEPTS["revenue"]:
        if k in fin:
            rev_years.update(fin[k].keys())
    if not rev_years:
        return None
    year = max(rev_years)

    def v(group):
        for k in INCOME_CONCEPTS[group]:
            if k in fin and year in fin[k]:
                val = fin[k][year]
                if val is None:
                    continue
                try:
                    if val != val:  # NaN
                        continue
                except TypeError:
                    continue
                return to_millions(val)
        return None

    rev = v("revenue"); net = v("net"); op = v("operating"); cost = v("cost")
    if cost is None:  # 美股常只披露毛利、不单列营业成本 → 用 营收−毛利 反推
        g = v("gross")
        if g is not None and rev is not None:
            cost = rev - g
    if None in (rev, net, cost) or rev <= 0:
        return None
    # 亏损公司也出图：营业利润≤0 或净利润≤0 走 _build_sankey_loss（红色虚线"净亏损"流入、守恒不崩）。
    sell = v("selling"); admin = v("admin"); rnd = v("rnd")
    taxsur = v("taxsur"); finance = v("finance")
    G = rev - cost  # 毛利
    seg_period, seg_dim, segs = _seg_latest_annual(base)

    nodes, links = [], []

    def node(nid, col, label, value, kind, order=0, **extra):
        n = {"id": nid, "col": col, "order": order, "label": label,
             "value": round(value, 2), "kind": kind}
        n.update(extra)
        nodes.append(n)

    def link(s, t, value, kind=None):
        if value and value > 0.01:
            d = {"source": s, "target": t, "value": round(value, 2)}
            if kind is not None:
                d["kind"] = kind
            links.append(d)

    # ===== 分流：营业利润>0 且净利润>0 → 正向利润瀑布（原样）；否则 → 亏损资金流向模型 =====
    if not (op is not None and op > 0 and net > 0):
        return _build_sankey_loss(
            year, rev, net, op, cost, sell, admin, rnd, taxsur, finance, G,
            seg_period, seg_dim, segs, nodes, links, node, link)

    # ---- 营业收入（中枢节点）----
    node("rev", 1, "营业收入", rev, "revenue", order=0)

    # ---- 左：业务板块 ----
    if segs:
        conv = []
        for s in segs:
            srev = to_millions(s.get("revenue")) or 0.0
            scost = to_millions(s.get("cost"))
            sgp = to_millions(s.get("gross_profit"))
            if scost is None and sgp is not None:
                scost = srev - sgp
            if scost is None:
                scost = srev * (cost / rev)
            conv.append({"name": s.get("name"), "rev": srev, "cost": scost,
                         "margin": s.get("margin")})
        conv.sort(key=lambda c: c["rev"], reverse=True)
        sum_rev = sum(c["rev"] for c in conv)
        if rev - sum_rev > rev * 0.005:  # 残差段（占营收>0.5%才单列）
            conv.append({"name": "其他业务", "rev": rev - sum_rev,
                         "cost": max(0.0, cost - sum(c["cost"] for c in conv)),
                         "margin": None})
        for i, c in enumerate(conv):
            mpct = round(c["margin"] * 100, 1) if c.get("margin") is not None else None
            node(f"seg{i}", 0, c["name"], c["rev"], "segment", order=i, margin=mpct)
            link(f"seg{i}", "rev", c["rev"])

    # ---- 营业收入 → 成本 / 毛利 ----
    node("gross", 2, "毛利", G, "gross", order=0)
    node("cost", 2, "营业成本", cost, "cost", order=1)
    link("rev", "gross", G)
    link("rev", "cost", cost)

    # ---- 毛利 → 各项费用 + 主营经营盈余 ----
    expense_sinks = []
    for label, val in [("销售费用", sell), ("管理费用", admin),
                       ("研发费用", rnd), ("税金及附加", taxsur)]:
        if val and val > 0:
            expense_sinks.append((label, val))
    if finance is not None and finance > 0:  # 财务费用为正才作为支出流出毛利
        expense_sinks.append(("财务费用", finance))
    E = sum(val for _, val in expense_sinks)
    core = G - E  # 主营经营盈余
    node("core", 3, "主营经营盈余", core, "flow", order=1)
    link("gross", "core", core)
    for i, (label, val) in enumerate(expense_sinks):
        node(f"exp{i}", 3, label, val, "expense", order=2 + i)
        link("gross", f"exp{i}", val)

    # ---- 营业利润（主营经营盈余 + 投资收益等外部净流入）----
    node("op", 4, "营业利润", op, "op", order=0)
    X = op - core  # 投资收益、公允价值变动、净利息收入等的净额
    if X > 0.5:
        node("invest", 3, "投资收益及其他(净)", X, "external", order=0,
             note="投资收益、公允价值变动、其他收益、净利息收入等非主营项目")
        link("core", "op", core)
        link("invest", "op", X)
    elif X < -0.5:
        link("core", "op", op)
        node("oploss", 4, "其他经营损益(净)", -X, "expense", order=1)
        link("core", "oploss", -X)
    else:
        link("core", "op", core)

    # ---- 营业利润 → 所得税及其他 + 净利润 ----
    tax_like = op - net
    node("net", 5, "净利润", net, "net", order=0)
    link("op", "net", net)
    if tax_like > 0.5:
        node("tax", 5, "所得税及其他", tax_like, "cost", order=1)
        link("op", "tax", tax_like)

    return {
        "year": year,
        "seg_period": seg_period,
        "seg_dim": seg_dim,
        "nodes": nodes,
        "links": links,
        "totals": {
            "revenue": round(rev, 2), "gross": round(G, 2),
            "operating_income": round(op, 2), "net_income": round(net, 2),
            "invest_other": round(max(X, 0.0), 2),
        },
    }


def latest_metric(fin, keys, year=None):
    """获取最新一年的某个指标（百万美元）。"""
    for k in keys:
        if k in fin:
            yrs = sorted(fin[k].keys())
            if not yrs:
                continue
            target = year if year in yrs else yrs[-1]
            return to_millions(fin[k][target])
    return None


def generate_starter_inputs(ticker, fin, history):
    """无 valuation_inputs.json 时，生成一份占位起点。用户需手动调整后再跑。"""
    latest_rev = None
    for h in reversed(history):
        if h["revenue"] is not None:
            latest_rev = h["revenue"]
            break
    if latest_rev is None:
        latest_rev = 100.0

    cash = latest_metric(fin, ["CashAndCashEquivalentsAtCarryingValue"]) or 0
    debt = latest_metric(fin, ["LongTermDebtNoncurrent"]) or 0

    # 启动模板：用相对中性的 3 情景假设，用户需替换为公司专属判断
    # 注意：这里的 market_cap 与 diluted_shares 都是占位，必须由用户填真实值
    inputs = {
        "company_name": ticker.upper(),
        "as_of": str(history[-1]["year"]) + "-12-31" if history else "",
        "facts": {
            "revenue_today": latest_rev,
            "cash": cash,
            "debt": debt,
            "market_cap": round(latest_rev * 10),  # 占位 P/S = 10
            "diluted_shares_today": 100,  # 占位
            "_TODO": "请把 market_cap 改为真实市值，diluted_shares_today 改为真实股数",
        },
        "scenarios": {
            "bear": {
                "story": "增长放缓 + 长期低利润率",
                "revY1": round(latest_rev * 1.05),
                "revY10": round(latest_rev * 1.06 ** 10),
                "mY1": -5,
                "mY10": 8,
                "discount": 14,
                "terminal_growth": 2,
                "future_shares": 130,
            },
            "base": {
                "story": "中等增长 + 中等利润率",
                "revY1": round(latest_rev * 1.15),
                "revY10": round(latest_rev * 1.15 ** 10),
                "mY1": -5,
                "mY10": 14,
                "discount": 12,
                "terminal_growth": 3,
                "future_shares": 115,
            },
            "bull": {
                "story": "高速增长 + 高利润率",
                "revY1": round(latest_rev * 1.25),
                "revY10": round(latest_rev * 1.25 ** 10),
                "mY1": 0,
                "mY10": 22,
                "discount": 11,
                "terminal_growth": 4,
                "future_shares": 105,
            },
        },
        "probabilities": {"bear": 25, "base": 50, "bull": 25},
    }
    return inputs


def render(ticker, starter=False):
    ticker = ticker.upper()
    fin = load_financials_csv(ticker)
    if not fin:
        sys.exit(f"错误：找不到 analyses/{ticker}/financials/financials.csv。先跑 fetch_filings.py。")
    history = build_history(fin)

    inputs_path = Path("analyses") / ticker / "valuation_inputs.json"
    if not inputs_path.exists():
        if not starter:
            sys.exit(
                f"错误：找不到 {inputs_path}\n"
                f"提示：加 --starter 参数生成一份占位起点，然后手动编辑后再跑一次：\n"
                f"  python scripts/render_explorer.py {ticker} --starter"
            )
        # 生成 starter
        starter_inputs = generate_starter_inputs(ticker, fin, history)
        inputs_path.write_text(json.dumps(starter_inputs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已生成 {inputs_path}")
        print("请打开它、按这家公司的情况调整三个情景的假设，然后重新运行不带 --starter 的命令生成 HTML。")
        return None

    with inputs_path.open(encoding="utf-8") as f:
        inputs = json.load(f)

    # 检测货币：valuation_inputs.json 显式指定 > 6 位纯数字代码默认 CNY > 默认 USD
    CURRENCY_SYMBOLS = {"USD": "$", "CNY": "￥", "HKD": "HK$", "EUR": "€", "JPY": "¥", "GBP": "£"}
    currency_code = inputs.get("currency")
    if not currency_code:
        currency_code = "CNY" if ticker.isdigit() and len(ticker) == 6 else "USD"
    currency_symbol = CURRENCY_SYMBOLS.get(currency_code, "$")

    # 检测同目录下的相关文件，供顶部导航链接使用（用 explorer 视角的相对路径）
    # 优先 PDF，fallback 到 MD
    base = Path("analyses") / ticker
    links = {}
    # 正文已嵌进交互器；这里只在真有 PDF 时给一个「下载 PDF」链（PDF 改按需导出，可能不存在）。
    report_pdfs = list(base.glob("*完整报告.pdf"))
    if report_pdfs:
        links["report_pdf"] = report_pdfs[0].name

    # 报告正文按章嵌入 + 第一章判断卡（核心论点抽去喂卡片、不再当章节）
    report_chapters, report_thesis_html = load_report_chapters(ticker)
    ch1_card = build_ch1_card(inputs, base, report_thesis_html)
    # 没有第一章判断卡的公司（尚未写 ch1 块）：核心论点回退成正文首章，避免凭空消失
    if ch1_card is None and report_thesis_html:
        report_chapters = [{"id": "ch-core", "title": "核心论点", "html": report_thesis_html}] + (report_chapters or [])
    ch2_card = build_ch2_card(inputs, fin)     # 第二章历程判断卡（脊梁/四段/行为模式/暗线/总账速览）
    ch3_card = build_ch3_card(inputs, base)    # 第三章行业判断卡（格局脊梁/竞争结构地图/谁掌握价值/价值压力/决胜变量）
    ch4_card = build_ch4_card(inputs, base)    # 第四章盈利引擎判断卡（盈利引擎脊梁/全景/谁真赚钱/利润含金量/健康度开关）
    ch5_card = build_ch5_card(inputs, fin)     # 第五章资本配置记录卡（脊梁/阶段诊断/资金来去/大决策剖检/每股记分牌/为谁配置/最强反方）
    ch6_card = build_ch6_card(inputs)          # 第六章治理判断卡（权力结构/关键人背调/控股股东跨主体记录/诚信记录/分级结论/胜负手/最强反方）
    metrics_obj = load_metrics(ticker)         # 四柱真相源（顶部仪表盘 + 第七章利润表透视复用）
    ch7_card = build_ch7_card(inputs, fin, metrics_obj)  # 第七章财务判断卡（利润表透视/分部盈利/盈利质量+会计可信度/价值阶梯/生存/反向画像）
    ch8_card = build_ch8_card(inputs)          # 第八章投资决策卡（capstone：作为生意值多少/安全边际+市场买了什么/不对称性/催化剂/决策；不重复情景表）
    ch9_card = build_ch9_card(inputs)          # 第九章风险判断卡（风险脊梁/风险矩阵/事前验尸/净风险画像+监控清单）

    # 组装完整数据对象
    data = {
        "ticker": ticker,
        "company_name": inputs.get("company_name", ticker),
        "as_of": inputs.get("as_of", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "facts": {
            k: v for k, v in inputs["facts"].items() if not k.startswith("_")
        },
        "history": history,
        "income_statement": build_income_statement(fin),
        "sankey": build_sankey(fin, base),
        "scenarios": inputs["scenarios"],
        "probabilities": inputs.get("probabilities", {"bear": 25, "base": 50, "bull": 25}),
        "currency": {"code": currency_code, "symbol": currency_symbol},
        "reverse_dcf_commentary": inputs.get("reverse_dcf_commentary"),
        "metrics": metrics_obj,                   # 价值判断四柱真相源（compute_metrics.py 产出）
        "pillars": inputs.get("pillars", {}),      # 我写的判断一句话（资本配置/安全边际等）
        "prices": load_prices(ticker),             # 近 5 年月度收盘价（fetch_prices.py 产出）
        "next_earnings": inputs.get("next_earnings"),  # 下一份财报日期（喂交互器顶部提醒横幅；可空）
        "decision": load_decision(ticker),         # 催化剂/检验时间线（decision.json 的 predictions/review_by/entry_watch）
        "layout": load_layout(ticker),             # 产业布局雷达（layout.json：近期动作 + 指向的产业 → 接力产业链分析）
        "report_chapters": report_chapters,        # 报告正文(按章嵌入交互器主干；已剔除导读/执行摘要/核心论点)
        "ch1_card": ch1_card,                      # 第一章判断卡（生意质量卡 + 业务速览 + 核心论点）
        "ch2_card": ch2_card,                      # 第二章历程判断卡（脊梁 + 四段时间轴 + 行为模式 + 暗线 + 总账速览）
        "ch3_card": ch3_card,                      # 第三章行业判断卡（格局脊梁 + 竞争结构地图 + 谁掌握价值 + 价值/压力 + 决胜变量）
        "ch4_card": ch4_card,                      # 第四章盈利引擎判断卡（盈利引擎脊梁 + 全景 + 谁真赚钱 + 利润含金量 + 健康度开关）
        "ch5_card": ch5_card,                      # 第五章资本配置记录卡（脊梁 + 阶段诊断 + 资金来去 + 大决策剖检 + 每股记分牌 + 为谁配置 + 最强反方）
        "ch6_card": ch6_card,                      # 第六章治理判断卡（权力结构 + 关键人背调 + 控股股东跨主体记录 + 诚信记录 + 分级结论 + 胜负手 + 最强反方）
        "ch7_card": ch7_card,                      # 第七章财务判断卡（利润表透视 + 分部盈利 + 盈利质量与会计可信度 + 价值阶梯 + 生存 + 反向画像 + 交底第八章）
        "ch8_card": ch8_card,                      # 第八章投资决策卡（作为生意值多少 + 安全边际与市场买了什么 + 不对称性 + 催化剂 + 决策）
        "ch9_card": ch9_card,                      # 第九章风险判断卡（风险脊梁 + 风险矩阵 + 事前验尸 + 净风险画像与监控清单）
        "links": links,
    }

    # 免费报价刷新：若有今日收盘，用"今日价×股数"覆盖显示市值（=当前价换成今日），
    # 交互器里安全边际/反向DCF/市场vs我会自动跟着重算；分析时市值另存供对照。判断内核（情景/四柱/概率）不动。
    quote = load_quote(ticker)
    if quote and quote.get("price"):
        data["quote"] = {"price": quote["price"], "as_of": quote.get("as_of"),
                         "analysis_market_cap": data["facts"].get("market_cap")}
        shares = data["facts"].get("diluted_shares_today")
        if shares:
            data["facts"]["market_cap"] = round(quote["price"] * shares, 2)

    # 读模板
    template_path = Path("tools") / "valuation_explorer.html"
    if not template_path.exists():
        sys.exit(f"错误：找不到模板 {template_path}")
    template = template_path.read_text(encoding="utf-8")

    # 替换数据块
    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    # 安全：数据块嵌在 <script type="application/json"> 里，把 </ 转义成 <\/（JSON 里等价、可逆），
    # 防止嵌入的报告 HTML 万一含 </script> 之类把脚本块提前截断。
    data_json = data_json.replace("</", "<\\/")
    new_block = (
        "<!-- RENDER_DATA_START -->\n"
        '<script id="initial-data" type="application/json">\n'
        + data_json
        + "\n</script>\n"
        "<!-- RENDER_DATA_END -->"
    )
    output, n = re.subn(
        r"<!-- RENDER_DATA_START -->.*?<!-- RENDER_DATA_END -->",
        lambda m: new_block,
        template,
        count=1,
        flags=re.DOTALL,
    )
    if n == 0:
        sys.exit("错误：模板里找不到 <!-- RENDER_DATA_START --> ... <!-- RENDER_DATA_END --> 标记")

    out_path = Path("analyses") / ticker / "valuation_explorer.html"
    out_path.write_text(output, encoding="utf-8")
    print(f"已生成 {out_path}")
    print(f"  历史财年：{[h['year'] for h in history]}")
    print(f"  当前营收：${data['facts']['revenue_today']:,.1f}M")
    print(f"  当前市值：${data['facts']['market_cap']:,.0f}M")
    print(f"  当前股价（隐含）：${data['facts']['market_cap'] / data['facts']['diluted_shares_today']:,.2f}")
    chs = data.get("report_chapters")
    if chs:
        print(f"  已嵌入完整报告正文：{len(chs)} 章（{'、'.join(c['title'] for c in chs[:3])}…）")
    else:
        print(f"  （未嵌入报告正文：缺 *完整报告.md 或 pandoc——交互器仍可用）")
    print(f"  浏览器打开即可使用，所有假设可拖动滑块实时调整。")
    # 章节卡完备性提醒（非致命，一行、不刷屏批量重渲）——已定标准的章若没出卡/报告缺脚手架，当场报缺。
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from check_chapters import verify_chapters
        ch_ok, ch_problems = verify_chapters(ticker)
        if not ch_ok:
            print(f"  ⚠ 章节卡未完备：{len(ch_problems)} 项待补"
                  f"（跑 python scripts/check_chapters.py {ticker} 看详情；qc_gate 出 PDF 时会硬拦）")
    except Exception:
        pass
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="为指定股票生成专属的价值分析交互器 HTML。"
    )
    ap.add_argument("ticker", help="股票代码，如 RKLB")
    ap.add_argument("--starter", action="store_true",
                    help="如果 valuation_inputs.json 不存在，生成一份占位起点")
    args = ap.parse_args()
    render(args.ticker, starter=args.starter)
