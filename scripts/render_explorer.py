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
import sys
from datetime import datetime
from pathlib import Path


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
    report_pdfs = list(base.glob("*完整报告.pdf"))
    report_mds = list(base.glob("*完整报告.md"))
    if report_pdfs:
        links["report_pdf"] = report_pdfs[0].name
    elif report_mds:
        links["report_pdf"] = report_mds[0].name

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
        "metrics": load_metrics(ticker),          # 价值判断四柱真相源（compute_metrics.py 产出）
        "pillars": inputs.get("pillars", {}),      # 我写的判断一句话（资本配置/安全边际等）
        "prices": load_prices(ticker),             # 近 5 年月度收盘价（fetch_prices.py 产出）
        "next_earnings": inputs.get("next_earnings"),  # 下一份财报日期（喂交互器顶部提醒横幅；可空）
        "decision": load_decision(ticker),         # 催化剂/检验时间线（decision.json 的 predictions/review_by/entry_watch）
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
    print(f"  浏览器打开即可使用，所有假设可拖动滑块实时调整。")
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
