#!/usr/bin/env python3
# 花名：哈维 —— 团队花名册见 CLAUDE.md「团队花名册」节
"""
check_numbers.py —— 报告数字对账（代码核查，免费、精确、不会幻觉）

把一份草稿报告里出现的每一个【金额 / 百分比】抽出来，逐个回查
financials.csv / quarterly.csv / segments.json，标出：
  ✓ 有据（注明来源 concept+年份）
  ⚠ 未匹配（可能是写错、也可能是合计/派生/外部数——请人工或 fact-check agent 核对）

这是"防幻觉"的第一道、也是最便宜的一道防线：
**数字级核对先用代码扫，判断级声明和原文引语再交给 fact-check agent。**
（符合工具哲学"代码算数、绝不用大模型做算术"。）

用法：
    python scripts/check_numbers.py 688237 analyses/688237/688237_公司完整报告.md
    python scripts/check_numbers.py 688237      # 不给文件则扫 dossier/memo/完整报告

输出：写到 analyses/<代码>/_check_numbers.txt（UTF-8），并在控制台打一行摘要。
"""

import csv
import json
import re
import sys
from pathlib import Path

YUAN = {"亿元": 1e8, "亿": 1e8, "万元": 1e4, "万": 1e4, "元": 1.0}
USD = {"T": 1e12, "B": 1e9, "M": 1e6, "": 1.0}
NUM = r"(-?\d+(?:[,，]\d{3})*(?:\.\d+)?)"

MONEY_RE = re.compile(NUM + r"\s*(亿元|亿|万元|万|元)")
USD_RE = re.compile(r"[\$＄]\s*" + NUM + r"\s*([MBT])?")
PCT_RE = re.compile(NUM + r"\s*%")


def _f(s):
    return float(str(s).replace(",", "").replace("，", ""))


# ---------- 读数据 ----------

def load_financials(ticker):
    p = Path("analyses") / ticker.upper() / "financials" / "financials.csv"
    data, unit = {}, "CNY"
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    fy, v = int(r["fiscal_year"]), float(r["value"])
                except (ValueError, TypeError):
                    continue
                if v != v:
                    continue
                data.setdefault(r["concept"], {})[fy] = v
                unit = r.get("unit") or unit
    return data, unit


def load_quarterly(ticker):
    p = Path("analyses") / ticker.upper() / "financials" / "quarterly.csv"
    data = {}
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    v = float(r["value"])
                except (ValueError, TypeError):
                    continue
                if v != v:
                    continue
                data.setdefault(r["concept"], {})[r["period_end"]] = v
    return data


def load_segments(ticker):
    p = Path("analyses") / ticker.upper() / "financials" / "segments.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_metrics(ticker):
    """读 metrics.json 的 metrics 块（价值判断四柱真值）。"""
    p = Path("analyses") / ticker.upper() / "financials" / "metrics.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("metrics", {})
        except Exception:
            return {}
    return {}


def add_metrics_to_pools(m, money_pool, pct_pool):
    """把四柱硬数字加进匹配池：报告引用 ROIC/FCF率/SBC占比/净债 等就能对上 metrics.json。"""
    if not m:
        return
    ce = m.get("compounding_engine", {}) or {}
    oe = m.get("owner_earnings", {}) or {}
    ca = m.get("capital_allocation", {}) or {}
    sv = m.get("survival", {}) or {}

    def addp(v, label):
        if isinstance(v, (int, float)) and v == v:
            pct_pool.append((v, label))

    def addm(v, label):
        if isinstance(v, (int, float)) and v == v:
            money_pool.append((v, label))

    addp(ce.get("roic_latest"), "ROIC(最新)")
    addp(ce.get("roe_latest"), "ROE(最新)")
    addp(ce.get("incremental_roic"), "增量ROIC")
    addp(ce.get("reinvestment_rate"), "再投资率")
    for s in ce.get("roic_series", []) or []:
        addp(s.get("roic"), f"ROIC {s.get('fy')}")
    for r in oe.get("series", []) or []:
        addp(r.get("fcf_margin"), f"FCF利润率 {r.get('fy')}")
        addp(r.get("sbc_pct_rev"), f"SBC/营收 {r.get('fy')}")
        addp(r.get("sbc_pct_fcf"), f"SBC/FCF {r.get('fy')}")
        addm(r.get("fcf"), f"FCF {r.get('fy')}")
        addm(r.get("fcf_ex_sbc"), f"FCF扣SBC {r.get('fy')}")
        addm(r.get("sbc"), f"SBC {r.get('fy')}")
    addp(ca.get("shareholder_return_pct_cfo"), "还股东占CFO")
    addp(ca.get("reinvest_pct_cfo"), "再投资占CFO")
    for k, v in (ca.get("pct_of_cfo") or {}).items():
        addp(v, f"{k}占CFO")
    for k, v in (ca.get("cumulative") or {}).items():
        addm(v, f"近5年累计{k}")
    addm(sv.get("net_debt"), "净债")
    addm(sv.get("cash"), "现金类")
    addm(sv.get("debt_due_1yr"), "一年内到期债")


def metrics_snapshot(m):
    """四柱真值快照，供 fact-check / discipline agent 对照。"""
    if not m:
        return ""
    ce = m.get("compounding_engine", {}) or {}
    oel = (m.get("owner_earnings", {}) or {}).get("latest", {}) or {}
    oeb = (m.get("owner_earnings", {}) or {}).get("band")
    ca = m.get("capital_allocation", {}) or {}
    sv = m.get("survival", {}) or {}
    cy = m.get("cycle_calibration", {}) or {}

    def p(v):
        return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "—"

    def n(v, suf="", fmt="{:.2f}"):
        return (fmt.format(v) + suf) if isinstance(v, (int, float)) else "—"

    L = ["", "===== 价值判断四柱真值（来自 metrics.json，报告须引用这些）====="]
    L.append(f"① 复利引擎 [{ce.get('band')}]: ROIC {p(ce.get('roic_latest'))} · ROE {p(ce.get('roe_latest'))} · "
             f"增量ROIC {p(ce.get('incremental_roic'))} · 再投资率 {p(ce.get('reinvestment_rate'))}"
             + ("（轻资产）" if ce.get("asset_light") else "") + ("（ROIC失真）" if ce.get("roic_distorted") else ""))
    L.append(f"② 所有者盈余 [{oeb}]: FCF利润率 {p(oel.get('fcf_margin'))} · SBC占FCF {p(oel.get('sbc_pct_fcf'))}")
    L.append(f"③ 资本配置: 还股东占CFO {p(ca.get('shareholder_return_pct_cfo'))} · 再投资占CFO {p(ca.get('reinvest_pct_cfo'))}")
    L.append(f"④ 生存 [{sv.get('band')}]: 净债/EBITDA {n(sv.get('net_debt_to_ebitda'))} · "
             f"利息覆盖 {n(sv.get('interest_coverage'), 'x', '{:.0f}')} · 现金跑道 {n(sv.get('cash_runway_years'), '年', '{:.1f}')}")
    if cy.get("peak_suspect"):
        r = cy.get("roic") or {}
        L.append(f"⚠ 周期高峰存疑：ROIC 基线 {p(r.get('baseline'))} → 最新 {p(r.get('latest'))}——报告须做中周期归一化")
    return "\n".join(L)


def net_cash_year(fin, fy):
    g = lambda k: fin.get(k, {}).get(fy)
    cash = g("CashAndCashEquivalentsAtCarryingValue")
    if cash is None:
        return None
    return (cash + (g("ShortTermInvestments") or 0) + (g("OtherCurrentFinancialAssets") or 0)
            - (g("ShortTermBorrowings") or 0) - (g("CurrentPortionLongTermDebt") or 0)
            - (g("LongTermDebtNoncurrent") or 0))


# ---------- 建匹配池 ----------

def build_money_pool(fin, q, seg):
    """返回 [(value_in_base, label)]，base 单位 = 元(CNY) 或 美元(USD)，与 financials 一致。"""
    pool = []

    def add(v, label):
        try:
            v = float(v)
        except (ValueError, TypeError):
            return
        if v == v:
            pool.append((v, label))

    for concept, yrs in fin.items():
        for fy, v in yrs.items():
            add(v, f"{concept} {fy}")
    # 派生：毛利、净现金
    for fy in sorted(fin.get("Revenues", {})):
        rev = fin.get("Revenues", {}).get(fy)
        cost = fin.get("CostOfRevenue", {}).get(fy)
        if rev is not None and cost is not None:
            add(rev - cost, f"毛利=营收-成本 {fy}")
        nc = net_cash_year(fin, fy)
        if nc is not None:
            add(nc, f"真实净现金 {fy}")
    for concept, per in q.items():
        for pe, v in per.items():
            add(v, f"{concept} {pe}(季)")
    bp = seg.get("by_product") or {}
    annual = sorted([p for p in bp if str(p).endswith("12-31")], reverse=True)
    if annual:
        for s in bp[annual[0]]:
            nm = s.get("name")
            add(s.get("revenue"), f"分部营收·{nm} {annual[0]}")
            add(s.get("cost"), f"分部成本·{nm}")
            add(s.get("gross_profit"), f"分部毛利·{nm}")
    return pool


def build_pct_pool(fin, seg):
    """返回 [(fraction, label)]：毛利率、净利率、各指标 YoY、分部毛利率。"""
    pool = []
    for concept, zh in [("Revenues", "营收"), ("NetIncomeLoss", "归母净利"),
                        ("NetIncomeLossExclNonRecurring", "扣非净利")]:
        yrs = sorted(fin.get(concept, {}))
        for i in range(1, len(yrs)):
            a, b = fin[concept][yrs[i - 1]], fin[concept][yrs[i]]
            if a:
                pool.append((b / a - 1, f"{zh} {yrs[i]} 同比"))
    for fy in sorted(fin.get("Revenues", {})):
        rev = fin["Revenues"][fy]
        if not rev:
            continue
        cost = fin.get("CostOfRevenue", {}).get(fy)
        if cost is not None:
            pool.append((1 - cost / rev, f"毛利率 {fy}"))
        ni = fin.get("NetIncomeLoss", {}).get(fy)
        if ni is not None:
            pool.append((ni / rev, f"净利率 {fy}"))
    bp = seg.get("by_product") or {}
    annual = sorted([p for p in bp if str(p).endswith("12-31")], reverse=True)
    if annual:
        for s in bp[annual[0]]:
            if s.get("margin") is not None:
                pool.append((s["margin"], f"分部毛利率·{s.get('name')}"))
    return pool


def match(value, pool, tol=0.02, abs_floor=1.0):
    for v, label in pool:
        if abs(value - v) <= max(abs(v) * tol, abs_floor):
            return label, v
    return None, None


# ---------- 主流程 ----------

def find_drafts(ticker):
    base = Path("analyses") / ticker.upper()
    cands = list(base.glob("*完整报告.md")) + [base / "dossier.md", base / "memo.md"]
    return [p for p in cands if p.exists()]


def check_file(path, money_pool, pct_pool, currency):
    money_ok, money_bad, pct_ok, pct_bad = 0, [], 0, []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        ctx = line.strip()[:70]
        if currency == "CNY":
            for m in MONEY_RE.finditer(line):
                base = _f(m.group(1)) * YUAN[m.group(2)]
                label, _ = match(base, money_pool, abs_floor=5e3)
                if label:
                    money_ok += 1
                else:
                    money_bad.append((ln, m.group(0), ctx))
        else:
            for m in USD_RE.finditer(line):
                base = _f(m.group(1)) * USD[m.group(2) or ""]
                label, _ = match(base, money_pool, abs_floor=5e3)
                if label:
                    money_ok += 1
                else:
                    money_bad.append((ln, m.group(0), ctx))
        for m in PCT_RE.finditer(line):
            frac = _f(m.group(1)) / 100.0
            label, _ = match(frac, pct_pool, tol=0.0, abs_floor=0.006)
            if label:
                pct_ok += 1
            else:
                pct_bad.append((ln, m.group(0), ctx))
    return money_ok, money_bad, pct_ok, pct_bad


def snapshot(fin, q, seg):
    out = ["===== 数据快照（地面真值，单位：亿元）====="]
    E = 1e8
    rows = ["Revenues", "CostOfRevenue", "OperatingIncomeLoss", "NetIncomeLoss",
            "NetIncomeLossExclNonRecurring", "NetCashProvidedByUsedInOperatingActivities",
            "CashAndCashEquivalentsAtCarryingValue", "ShortTermInvestments", "StockholdersEquity"]
    yrs = sorted(fin.get("Revenues", {}))[-5:]
    out.append("年份: " + "  ".join(str(y) for y in yrs))
    for c in rows:
        if c in fin:
            out.append(f"  {c:42s} " + "  ".join(
                (f"{fin[c].get(y)/E:.2f}" if fin[c].get(y) is not None else "—") for y in yrs))
    out.append("  真实净现金(含理财) " + "  ".join(
        (f"{net_cash_year(fin, y)/E:.2f}" if net_cash_year(fin, y) is not None else "—") for y in yrs))
    if q:
        out.append("\n季度(亿元): " + ", ".join(sorted({pe for per in q.values() for pe in per}))[:200])
        for c, per in q.items():
            out.append(f"  {c:42s} " + "  ".join(f"{pe[2:7]}:{v/E:.3f}" for pe, v in sorted(per.items())))
    bp = seg.get("by_product") or {}
    annual = sorted([p for p in bp if str(p).endswith("12-31")], reverse=True)
    if annual:
        out.append(f"\n分部(按产品 {annual[0]}, 亿元):")
        for s in bp[annual[0]]:
            r = (s.get("revenue") or 0) / E
            mg = s.get("margin")
            out.append(f"  {str(s.get('name')):20s} 营收{r:.2f}  毛利率{mg*100:.1f}%" if mg is not None else f"  {s.get('name')} 营收{r:.2f}")
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python scripts/check_numbers.py <代码> [草稿.md]")
    ticker = sys.argv[1]
    fin, currency = load_financials(ticker)
    if not fin:
        sys.exit(f"找不到 analyses/{ticker.upper()}/financials/financials.csv")
    q = load_quarterly(ticker)
    seg = load_segments(ticker)
    metrics = load_metrics(ticker)
    money_pool = build_money_pool(fin, q, seg)
    pct_pool = build_pct_pool(fin, seg)
    add_metrics_to_pools(metrics, money_pool, pct_pool)   # 四柱数字进池

    drafts = [Path(sys.argv[2])] if len(sys.argv) > 2 else find_drafts(ticker)
    drafts = [p for p in drafts if p.exists()]
    if not drafts:
        sys.exit("没有可核对的草稿（dossier.md / memo.md / *完整报告.md 都不存在，或路径错误）")

    report = [f"# 数字对账报告 · {ticker.upper()} · 币种 {currency}", ""]
    total_bad = 0
    for d in drafts:
        mok, mbad, pok, pbad = check_file(d, money_pool, pct_pool, currency)
        total_bad += len(mbad)
        report.append(f"## {d.name}")
        report.append(f"金额: ✓{mok} 有据 / ⚠{len(mbad)} 未匹配；百分比: ✓{pok} / ⚠{len(pbad)}")
        if mbad:
            report.append("\n⚠ 未匹配金额（请逐个核对——可能写错，也可能是合计/派生/外部数）：")
            for ln, tok, ctx in mbad[:60]:
                report.append(f"  L{ln}: 「{tok}」  ……{ctx}")
        if pbad:
            report.append("\n⚠ 未自动匹配的百分比（参考，多为占比/ROE/外部数，重点看增速与毛利率）：")
            for ln, tok, ctx in pbad[:40]:
                report.append(f"  L{ln}: 「{tok}」  ……{ctx}")
        report.append("")

    report.append(snapshot(fin, q, seg))
    report.append(metrics_snapshot(metrics))
    out_path = Path("analyses") / ticker.upper() / "_check_numbers.txt"
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"已写出 {out_path}（金额未匹配共 {total_bad} 处，需核对）")


if __name__ == "__main__":
    main()
