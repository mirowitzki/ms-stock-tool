#!/usr/bin/env python3
"""
valuation.py —— 估值计算（纯代码，精确）

从 fetch_filings.py 产出的 financials.csv 读取结构化财务数据，提供两条 Track 的估值工具：

Track A（成熟公司）：
    - owner_earnings()       近似所有者盈余（CFO − CapEx）
    - two_stage_dcf()        简单两阶段 DCF（基于起始所有者盈余复合增长）

Track B（未盈利成长公司）：
    - scenario_forward_dcf() 情景前瞻 DCF：输入逐年营收路径 + 逐年 FCF 利润率 + 折现率
                              + 终值假设 + 未来稀释股数 → 每股内在价值
    - reverse_dcf()          反向 DCF：给定今天的市值，反解出市场隐含的预期
                              （固定一个变量、反解另一个）

分工：大模型只负责给出"判断性"输入（增长率、折现率、利润率、未来股数），
计算本身全部由代码完成。**算术不交给模型。**
"""

import csv
import sys
from pathlib import Path


# ============================================================
# 公共：读取财务数据
# ============================================================

def load_financials(ticker):
    """读入 analyses/<TICKER>/financials/financials.csv，返回 {concept: {fy: value}}。"""
    path = Path("analyses") / ticker.upper() / "financials" / "financials.csv"
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


def owner_earnings(fin, fy):
    """
    "所有者盈余"的近似：
        优先用 经营现金流 − 资本开支（更稳健的自由现金流口径）；
        退而求其次用 净利润 − 资本开支。

    TODO（判断层）：资本开支需拆分"维持性 vs 扩张性"，这里暂用总资本开支近似。
    """
    capex = fin.get("PaymentsToAcquirePropertyPlantAndEquipment", {}).get(fy)
    cfo = fin.get("NetCashProvidedByUsedInOperatingActivities", {}).get(fy)
    ni = fin.get("NetIncomeLoss", {}).get(fy)
    if cfo is not None and capex is not None:
        return cfo - capex
    if ni is not None and capex is not None:
        return ni - capex
    return None


# ============================================================
# Track A：成熟公司的两阶段 DCF
# ============================================================

def two_stage_dcf(base_oe, growth_high, years_high, growth_terminal, discount):
    """
    简单两阶段 DCF。所有输入都是"判断"，由人/Claude 决定理由；计算由代码精确完成。
      base_oe         起始所有者盈余
      growth_high     高速增长阶段年增速（如 0.12）
      years_high      高速增长年数（如 10）
      growth_terminal 永续增长率（保守，如 0.03）
      discount        折现率（如 0.10；越不确定要求越高）
    """
    if base_oe is None or base_oe <= 0 or discount <= growth_terminal:
        return None
    pv, oe = 0.0, base_oe
    for t in range(1, years_high + 1):
        oe *= (1 + growth_high)
        pv += oe / ((1 + discount) ** t)
    terminal_value = oe * (1 + growth_terminal) / (discount - growth_terminal)
    pv += terminal_value / ((1 + discount) ** years_high)
    return pv


# ============================================================
# Track B：未盈利成长公司的情景前瞻 DCF
# ============================================================

def scenario_forward_dcf(
    revenue_path,
    fcf_margin_path,
    discount_rate,
    terminal_growth,
    terminal_fcf_margin=None,
    cash=0.0,
    debt=0.0,
    future_shares=None,
):
    """
    情景前瞻 DCF：用未来 N 年的"营收 + FCF 利润率"路径来算每股内在价值。

    适用于：起始所有者盈余为负 / 利润率剧烈波动 / 价值押在未来某个里程碑的成长公司。
    标准 DCF（基于起始 OE 复合增长）对这类公司无效；本方法把"叙事路径"显式化。

    参数（所有金额单位必须一致，建议百万美元）：
      revenue_path        长度 N 的 list：未来逐年营收 [Y1, Y2, ..., YN]
      fcf_margin_path     长度 N 的 list：每年的 FCF/Revenue 比例（可为负）
      discount_rate       折现率（如 0.13）
      terminal_growth     永续增长率（如 0.03）；必须 < discount_rate
      terminal_fcf_margin 终值期 FCF 利润率；如果为 None 则用 fcf_margin_path[-1]
      cash                当前现金及等价物（加进权益）
      debt                当前有息债务（从权益扣掉）
      future_shares       未来稀释后的股数；如果为 None 则不算每股值

    返回 dict：
      explicit_fcf        逐年 FCF
      explicit_pv         逐年现值
      explicit_pv_total   明确预测期 PV 合计
      terminal_fcf        终值期年 FCF
      terminal_value      终值期估值（戈登模型）
      terminal_pv         终值贴现到今天
      enterprise_value    企业价值 = 明确 PV + 终值 PV
      equity_value        权益价值 = EV + 现金 − 债务
      per_share_value     每股内在价值（若提供 future_shares）
    """
    if len(revenue_path) != len(fcf_margin_path):
        raise ValueError("revenue_path 和 fcf_margin_path 长度必须相同")
    if discount_rate <= terminal_growth:
        raise ValueError("折现率必须大于永续增长率（否则戈登模型发散）")
    if not revenue_path:
        raise ValueError("revenue_path 不能为空")

    N = len(revenue_path)
    if terminal_fcf_margin is None:
        terminal_fcf_margin = fcf_margin_path[-1]

    explicit_fcf = [r * m for r, m in zip(revenue_path, fcf_margin_path)]
    explicit_pv = [fcf / (1 + discount_rate) ** (t + 1) for t, fcf in enumerate(explicit_fcf)]
    explicit_pv_total = sum(explicit_pv)

    # 戈登模型：终值期第一年 = 最后一年营收 × (1 + g) × terminal_fcf_margin
    revenue_terminal = revenue_path[-1] * (1 + terminal_growth)
    terminal_fcf = revenue_terminal * terminal_fcf_margin
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / (1 + discount_rate) ** N

    enterprise_value = explicit_pv_total + terminal_pv
    equity_value = enterprise_value + cash - debt

    result = {
        "explicit_fcf": explicit_fcf,
        "explicit_pv": explicit_pv,
        "explicit_pv_total": explicit_pv_total,
        "terminal_fcf": terminal_fcf,
        "terminal_value": terminal_value,
        "terminal_pv": terminal_pv,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
    }

    if future_shares is not None and future_shares > 0:
        result["per_share_value"] = equity_value / future_shares
        result["future_shares"] = future_shares

    return result


def scenario_value_range(
    revenue_today,
    cagr_range,
    fcf_margin_range,
    discount_range,
    terminal_growth,
    cash=0.0,
    debt=0.0,
    future_shares=None,
    start_fcf_margin=None,
    years=5,
):
    """
    一个情景的【价值区间】：rate 本身是模糊的，所以输出区间而非单点
    （见 valuation 技能"估值哲学"第三条：故事 → rate 区间 → 价值区间）。

    每个 *_range 传 (低, 高) 两端；rate 之间逻辑要自洽（高增长常伴随高投入/高折现）：
      revenue_today       近一年实际营收（金额单位一致，建议百万）
      cagr_range          营收年化 CAGR 的 (低, 高)，如 (0.15, 0.25)
      fcf_margin_range    成熟期 FCF 利润率的 (低, 高)，如 (0.12, 0.16)
      discount_range      折现率的 (低, 高)，如 (0.11, 0.13)
      terminal_growth     永续增长率（单值，2–4%）
      cash, debt          当前现金、债务
      future_shares       未来稀释后的股数（务必用未来值，不是今天的）
      start_fcf_margin    起始 FCF 利润率（可为负）；None 则全程用成熟期利润率
      years               明确预测期年数（默认 5；传 10 可得"延伸至十年"的参考值）
                          注：窗口越短，终值占比越高（5 年常占 ~85%）——纪律来自
                          把第 5 年后的稳态（这里＝成熟 FCF 利润率）显性写出，而非藏进终值

    价值低端 = 保守组合（CAGR 低 + 利润率 低 + 折现率 高）
    价值高端 = 乐观组合（CAGR 高 + 利润率 高 + 折现率 低）

    返回 dict：{"low": 每股价值低端, "high": 每股价值高端}
    """
    cagr_lo, cagr_hi = min(cagr_range), max(cagr_range)
    m_lo, m_hi = min(fcf_margin_range), max(fcf_margin_range)
    d_lo, d_hi = min(discount_range), max(discount_range)

    def _per_share(cagr, mature_margin, discount):
        revenue_path = [revenue_today * (1 + cagr) ** t for t in range(1, years + 1)]
        if start_fcf_margin is None:
            fcf_margin_path = [mature_margin] * years
        else:
            fcf_margin_path = _ramp(start_fcf_margin, mature_margin, years)
        r = scenario_forward_dcf(
            revenue_path=revenue_path,
            fcf_margin_path=fcf_margin_path,
            discount_rate=discount,
            terminal_growth=terminal_growth,
            terminal_fcf_margin=mature_margin,
            cash=cash,
            debt=debt,
            future_shares=future_shares,
        )
        return r.get("per_share_value")

    # 保守组合给价值下端，乐观组合给上端
    low = _per_share(cagr_lo, m_lo, d_hi)
    high = _per_share(cagr_hi, m_hi, d_lo)
    return {"low": low, "high": high}


# ============================================================
# Track B：反向 DCF
# ============================================================

def _ramp(start, end, n):
    """从 start 线性爬到 end，长度 n 的列表。"""
    if n == 1:
        return [end]
    return [start + (end - start) * t / (n - 1) for t in range(n)]


def reverse_dcf(
    market_cap,
    revenue_today,
    discount_rate,
    terminal_growth,
    cash=0.0,
    debt=0.0,
    future_shares=None,
    years=5,
    solve_for="cagr",
    fixed_fcf_margin=0.15,
    fixed_cagr=0.15,
    start_fcf_margin=0.0,
):
    """
    反向 DCF：给定今天的市值，反解出市场隐含的预期。

    适用：用来判断"当前价格已经在 price-in 什么"，与三情景结果对照。
    默认 years=5（5 年口径，可证伪性强）；传 years=10 得"延伸至十年"的参考口径，
    两者并列能看出市场把多少乐观押在了 6-10 年这段最难证伪的远期上。

    简化假设：
      - 营收以恒定 CAGR 增长 years 年
      - FCF 利润率从 start_fcf_margin 线性爬升到成熟期目标利润率
      - 终值用戈登模型，永续增长率 = terminal_growth

    参数：
      market_cap          今天的市值（百万美元）
      revenue_today       近一年的实际营收
      discount_rate       折现率（如 0.12）
      terminal_growth     永续增长率（如 0.03）
      cash, debt          当前现金、债务
      future_shares       未来股数（用于一致性，不影响反解结果）
      years               明确预测期年数（默认 5；传 10 得"延伸至十年"参考口径）
      solve_for           'cagr' 或 'fcf_margin'
      fixed_fcf_margin    当 solve_for='cagr' 时使用，固定成熟期 FCF 利润率
      fixed_cagr          当 solve_for='fcf_margin' 时使用，固定营收 CAGR
      start_fcf_margin    起始 FCF 利润率（默认 0%，可设为公司当前的实际 FCF margin）

    返回 dict：
      mode                'cagr' 或 'fcf_margin'
      implied_value       反解出的值（CAGR 或成熟期 FCF margin）
      description         文字解释
      verification_ev    用反解值正算一遍的企业价值（应接近目标 EV）
    """
    target_equity = market_cap
    target_ev = target_equity - cash + debt

    if solve_for == "cagr":
        def value_for_cagr(g):
            revenue_path = [revenue_today * (1 + g) ** t for t in range(1, years + 1)]
            fcf_margin_path = _ramp(start_fcf_margin, fixed_fcf_margin, years)
            r = scenario_forward_dcf(
                revenue_path=revenue_path,
                fcf_margin_path=fcf_margin_path,
                discount_rate=discount_rate,
                terminal_growth=terminal_growth,
                terminal_fcf_margin=fixed_fcf_margin,
                cash=0,  # 在反解 EV 时不加现金，避免双计
                debt=0,
                future_shares=None,
            )
            return r["enterprise_value"]

        # 二分查找 CAGR，搜索范围 -20% 到 100%
        lo, hi = -0.20, 1.00
        for _ in range(80):
            mid = (lo + hi) / 2
            v = value_for_cagr(mid)
            if v < target_ev:
                lo = mid
            else:
                hi = mid
        implied = (lo + hi) / 2
        return {
            "mode": "cagr",
            "implied_value": implied,
            "description": (
                f"假设成熟期 FCF 利润率 = {fixed_fcf_margin:.1%}、"
                f"起始 FCF 利润率 = {start_fcf_margin:.1%}、"
                f"折现率 = {discount_rate:.1%}、"
                f"永续增长率 = {terminal_growth:.1%}、"
                f"明确预测期 = {years} 年；"
                f"则要让企业价值 ≈ ${target_ev:,.0f}M，"
                f"营收 CAGR 必须达到 ≈ {implied:.1%}"
            ),
            "verification_ev": value_for_cagr(implied),
            "target_ev": target_ev,
        }

    elif solve_for == "fcf_margin":
        def value_for_margin(m):
            revenue_path = [revenue_today * (1 + fixed_cagr) ** t for t in range(1, years + 1)]
            fcf_margin_path = _ramp(start_fcf_margin, m, years)
            r = scenario_forward_dcf(
                revenue_path=revenue_path,
                fcf_margin_path=fcf_margin_path,
                discount_rate=discount_rate,
                terminal_growth=terminal_growth,
                terminal_fcf_margin=m,
                cash=0,
                debt=0,
                future_shares=None,
            )
            return r["enterprise_value"]

        # 二分查找 FCF margin，搜索范围 -50% 到 80%
        lo, hi = -0.50, 0.80
        for _ in range(80):
            mid = (lo + hi) / 2
            v = value_for_margin(mid)
            if v < target_ev:
                lo = mid
            else:
                hi = mid
        implied = (lo + hi) / 2
        return {
            "mode": "fcf_margin",
            "implied_value": implied,
            "description": (
                f"假设营收 CAGR = {fixed_cagr:.1%}、"
                f"起始 FCF 利润率 = {start_fcf_margin:.1%}、"
                f"折现率 = {discount_rate:.1%}、"
                f"永续增长率 = {terminal_growth:.1%}、"
                f"明确预测期 = {years} 年；"
                f"则要让企业价值 ≈ ${target_ev:,.0f}M，"
                f"成熟期 FCF 利润率必须达到 ≈ {implied:.1%}"
            ),
            "verification_ev": value_for_margin(implied),
            "target_ev": target_ev,
        }
    else:
        raise ValueError(f"solve_for 必须是 'cagr' 或 'fcf_margin'，得到 {solve_for!r}")


# ============================================================
# Track C：资产重 / 现金多 / 低 ROE / 有特殊事件的公司
#   —— 标准 DCF 与情景 DCF 都不合适时，用四把尺子。
#   全部接收"判断性输入"（正常化盈余、分部毛估、调整额由人/Claude 给并说明理由），
#   代码只做加减、排阶梯。一切毛估区间，"模糊的正确 > 精准的错误"。
# ============================================================

def real_net_cash(fin, fy):
    """真实净现金（纠正"只读货币资金一行"的盲点，见反成见铁律第 4 条）：
        货币资金 + 交易性金融资产(理财) + 其他流动金融资产
        − 短期借款 − 一年内到期非流动负债 − 长期借款。
    缺的科目按 0 处理；连货币资金都没有则返回 None。"""
    g = lambda k: fin.get(k, {}).get(fy)
    cash = g("CashAndCashEquivalentsAtCarryingValue")
    if cash is None:
        return None
    wealth = g("ShortTermInvestments") or 0.0          # 交易性金融资产 / 理财
    other_fin = g("OtherCurrentFinancialAssets") or 0.0
    st_debt = g("ShortTermBorrowings") or 0.0
    cur_ltd = g("CurrentPortionLongTermDebt") or 0.0
    lt_debt = g("LongTermDebtNoncurrent") or 0.0
    return cash + wealth + other_fin - st_debt - cur_ltd - lt_debt


def epv(normalized_owner_earnings, required_return, net_cash=0.0):
    """收益能力价值（EPV，假设零增长）= 正常化所有者盈余 / 要求回报率 + 净现金。
    输入都是判断；建议对 OE 与 required_return 取区间、用 epv_range 得价值区间。"""
    if required_return is None or required_return <= 0 or normalized_owner_earnings is None:
        return None
    return normalized_owner_earnings / required_return + net_cash


def epv_range(oe_range, rr_range, net_cash=0.0):
    """EPV 的【区间】：保守端 = 低 OE + 高要求回报；乐观端 = 高 OE + 低要求回报。"""
    oe_lo, oe_hi = min(oe_range), max(oe_range)
    rr_lo, rr_hi = min(rr_range), max(rr_range)
    return {"low": epv(oe_lo, rr_hi, net_cash), "high": epv(oe_hi, rr_lo, net_cash)}


def adjusted_asset_value(book_equity, adjustments=None):
    """调整后资产价值（价值地板）= 账面归母净资产 + 各项谨慎调整（负数=减记）。
        adjustments: {名目: 调整额}，如 {"商誉审慎减记": -80, "应收打折": -30}。"""
    adjustments = dict(adjustments or {})
    return {"value": book_equity + sum(adjustments.values()), "detail": adjustments}


def sum_of_parts(segment_values, net_cash=0.0, other_adjustments=None):
    """分部加总（SOTP）= Σ 各板块毛估价值 + 净现金 + 其他调整。
        segment_values: {板块名: (低,高)} 或 {板块名: 单值}（亏损块可给 0 或负）。
    返回价值【区间】。"""
    lo = hi = 0.0
    detail = {}
    for name, v in segment_values.items():
        a, b = (min(v), max(v)) if isinstance(v, (tuple, list)) else (v, v)
        lo += a
        hi += b
        detail[name] = (a, b)
    adj = sum((other_adjustments or {}).values())
    return {"low": lo + net_cash + adj, "high": hi + net_cash + adj, "detail": detail}


def _as_range(x):
    if isinstance(x, dict):
        if "low" in x or "high" in x:
            return (x.get("low"), x.get("high"))
        if "value" in x:                         # adjusted_asset_value 的 {value,...}
            return (x.get("value"), x.get("value"))
    if isinstance(x, (tuple, list)):
        return (min(x), max(x))
    return (x, x)


def value_ladder(asset_floor, epv_value, sotp, market_cap=None):
    """把四层价值排成阶梯（地板 < EPV < 分部加总 < 市值）并自动给"模糊但正确"的诊断。
    入参都可是单值 / (低,高) / {low,high}。"""
    a, e, s = _as_range(asset_floor), _as_range(epv_value), _as_range(sotp)
    notes = []
    if e[1] is not None and a[0] is not None and e[1] < a[0]:
        notes.append("EPV 上限 < 资产价值下限 → 合并层面在毁灭价值：价值释放靠'资本配置变好'、不靠'业务变好'。")
    if market_cap is not None and s[1] is not None and market_cap > s[1]:
        notes.append(f"市值（{market_cap:,.0f}）> 分部加总上限（{s[1]:,.0f}）→ 对基本面投资者无安全边际，溢价买的是预期/期权。")
    if market_cap is not None and a[1] is not None and market_cap <= a[1]:
        notes.append(f"市值（{market_cap:,.0f}）≤ 资产地板上限（{a[1]:,.0f}）→ 接近或低于资产价值，下行保护强。")
    return {"asset_floor": a, "epv": e, "sotp": s, "market_cap": market_cap, "notes": notes}


# ============================================================
# 价值判断四柱指标（纯代码、可对账；喂 metrics.json → 报告 + 交互器仪表盘 + 质检关）
# ============================================================
#
# 设计：代码只算"硬数字 + 一个粗分档"，不下判断结论。细腻的判断（护城河方向、
# 资本配置好坏、生不生存）由 Claude 在报告里结合定性证据下，但必须引用这里算出来的数字。
#
# 四柱：① 复利引擎(ROIC/增量ROIC/再投资)  ② 所有者盈余(正常化/SBC调整)
#       ③ 资本配置记录卡(每块现金去向)      ④ 生存测试(净债/覆盖/到期墙)

_REV_KEYS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]


def _g(fin, concept, fy):
    return fin.get(concept, {}).get(fy)


def _first(fin, concepts, fy):
    for c in concepts:
        v = fin.get(c, {}).get(fy)
        if v is not None and v == v:  # 排除 None / NaN
            return v
    return None


def _fy_list(fin, concepts=None, n=None):
    """有数据的财年并集，升序；n 给定则取最近 n 个。"""
    concepts = concepts or (_REV_KEYS + ["NetIncomeLoss", "OperatingIncomeLoss"])
    ys = set()
    for c in concepts:
        ys.update(fin.get(c, {}).keys())
    ys = sorted(ys)
    return ys[-n:] if n else ys


def revenue(fin, fy):
    return _first(fin, _REV_KEYS, fy)


def _net_income(fin, fy):
    """合并净利/净亏：优先 NetIncomeLoss，回退 NetIncomeLossTotal / ProfitLoss（如 NVTS 近年用 ProfitLoss）。"""
    return _first(fin, ["NetIncomeLoss", "NetIncomeLossTotal", "ProfitLoss"], fy)


def current_debt(fin, fy):
    """一年内有息债 = 一年内到期非流动负债 + 短期借款。
    这两个科目在 A 股并存且互不重叠，必须相加——2026-06 教训：取其一会把短期借款
    整个科目丢掉、系统性低估杠杆（300199 漏 10.33 亿、000925 漏 6.05 亿）。
    美股常只申报其中一个；DebtCurrent（合计口径）仅在前两者都缺时兜底。"""
    cur_ltd = _first(fin, ["LongTermDebtCurrent", "CurrentPortionLongTermDebt"], fy)
    st = _g(fin, "ShortTermBorrowings", fy)
    parts = [p for p in (cur_ltd, st) if p is not None and p == p]
    if parts:
        return sum(parts)
    return _g(fin, "DebtCurrent", fy)


def total_debt(fin, fy):
    """有息负债合计 = 长期债(非流动) + 一年内有息债（短借与一年内到期相加，见 current_debt）。
    注意 LongTermDebt 标签在美股常为含一年内到期的合计口径——只在 Noncurrent 缺失时使用，
    且若同时有一年内到期数则先剔除、避免双计。"""
    lt = _first(fin, ["LongTermDebtNoncurrent"], fy)
    if lt is None:
        lt_total = _g(fin, "LongTermDebt", fy)
        if lt_total is not None:
            cur_ltd = _first(fin, ["LongTermDebtCurrent", "CurrentPortionLongTermDebt"], fy)
            lt = (lt_total - cur_ltd) if (cur_ltd is not None and lt_total >= cur_ltd) else lt_total
    bonds = _g(fin, "BondsPayableNoncurrent", fy)  # A 股应付债券（与长期借款并列，须加；美股管道不取此标签）
    cur = current_debt(fin, fy)
    parts = [p for p in (lt, bonds, cur) if p is not None]
    return sum(parts) if parts else None


def debt_components(fin, fy):
    """净债口径透明化：各负债科目找到了什么、缺了什么（喂 metrics.json，防无声缺口）。
    教训：字段缺失静默当 0，是净债被低估两次的温床——缺口必须被看见。"""
    comps = {
        "long_term_noncurrent": _first(fin, ["LongTermDebtNoncurrent"], fy),
        "long_term_total_tag": _g(fin, "LongTermDebt", fy),
        "bonds_payable": _g(fin, "BondsPayableNoncurrent", fy),
        "current_portion_ltd": _first(fin, ["LongTermDebtCurrent", "CurrentPortionLongTermDebt"], fy),
        "short_term_borrowings": _g(fin, "ShortTermBorrowings", fy),
        "debt_current_fallback": _g(fin, "DebtCurrent", fy),
    }
    found = {k: v for k, v in comps.items() if v is not None and v == v}
    missing = [k for k, v in comps.items() if v is None or v != v]
    return {"fy": fy, "found": found, "missing": missing,
            "note": "应付债券/租赁负债等科目当前取数管道未覆盖；判生存柱前以年报附注的全口径为准"}


def excess_cash(fin, fy):
    """现金及类现金 = 货币资金(+短期投资)。优先用"现金+短投"合并标签，避免重复计。"""
    combo = _g(fin, "CashCashEquivalentsAndShortTermInvestments", fy)
    if combo is not None and combo == combo:
        return combo
    cash = _first(fin, ["CashAndCashEquivalentsAtCarryingValue",
                        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                        "CashAndCashEquivalentsAtCarryingValueIncludingDiscontinuedOperations"], fy)
    sti = _g(fin, "ShortTermInvestments", fy)
    parts = [p for p in (cash, sti) if p is not None]
    return sum(parts) if parts else None


def net_debt(fin, fy):
    """净债 = 有息负债 − 现金类。负值 = 净现金。"""
    d = total_debt(fin, fy)
    c = excess_cash(fin, fy)
    if d is None and c is None:
        return None
    return (d or 0) - (c or 0)


def effective_tax_rate(fin, fy):
    """有效税率 = 所得税 / 税前利润；税前 = 净利 + 所得税。缺则用 None。"""
    tax = _g(fin, "IncomeTaxExpenseBenefit", fy)
    ni = _net_income(fin, fy)
    if tax is None or ni is None:
        return None
    pretax = ni + tax
    if pretax <= 0:
        return None
    r = tax / pretax
    return min(max(r, 0.0), 0.40)  # 钳制到 [0,40%]，挡住一次性税项噪声


def nopat(fin, fy, default_tax=0.21):
    """税后经营利润 = 营业利润 × (1 − 有效税率)。有效税率缺时用 default_tax。"""
    op = _g(fin, "OperatingIncomeLoss", fy)
    if op is None:
        return None
    t = effective_tax_rate(fin, fy)
    if t is None:
        t = default_tax
    return op * (1 - t)


def invested_capital(fin, fy):
    """投入资本 = 有息负债 + 股东权益 − 现金类（剔除多余现金的经营投入资本）。"""
    eq = _g(fin, "StockholdersEquity", fy)
    d = total_debt(fin, fy)
    c = excess_cash(fin, fy)
    if eq is None and d is None:
        return None
    ic = (eq or 0) + (d or 0) - (c or 0)
    return ic


def roic(fin, fy, default_tax=0.21):
    """ROIC = NOPAT / 投入资本（用期末投入资本）。投入资本≤0 时返回 None（口径失真）。"""
    np_ = nopat(fin, fy, default_tax)
    ic = invested_capital(fin, fy)
    if np_ is None or ic is None or ic <= 0:
        return None
    return np_ / ic


def ebitda(fin, fy):
    op = _g(fin, "OperatingIncomeLoss", fy)
    da = _first(fin, ["DepreciationDepletionAndAmortization",
                      "DepreciationAmortizationAndAccretionNet"], fy)
    if op is None:
        return None
    return op + (da or 0)


def fcf(fin, fy):
    cfo = _g(fin, "NetCashProvidedByUsedInOperatingActivities", fy)
    capex = _g(fin, "PaymentsToAcquirePropertyPlantAndEquipment", fy)
    if cfo is None:
        return None
    return cfo - (capex or 0)


def compounding_engine(fin, n=5, default_tax=0.21):
    """① 复利引擎：ROIC 趋势 + 增量 ROIC + 再投资率 → 隐含可持续增长。"""
    years = _fy_list(fin, ["OperatingIncomeLoss"], n + 1)  # 多取一年算增量
    series = []
    for y in years:
        r = roic(fin, y, default_tax)
        series.append({"fy": y, "roic": r,
                       "nopat": nopat(fin, y, default_tax),
                       "invested_capital": invested_capital(fin, y)})
    vals = [s for s in series if s["roic"] is not None]
    latest = vals[-1] if vals else None
    # 趋势：最近 vs 最早（有效点）
    trend = None
    if len(vals) >= 2:
        trend = vals[-1]["roic"] - vals[0]["roic"]
    # 增量 ROIC：Δ NOPAT / Δ 投入资本（首尾有效点）
    inc_roic = None
    pts = [s for s in series if s["nopat"] is not None and s["invested_capital"] is not None]
    if len(pts) >= 2:
        d_np = pts[-1]["nopat"] - pts[0]["nopat"]
        d_ic = pts[-1]["invested_capital"] - pts[0]["invested_capital"]
        if d_ic and abs(d_ic) > 1:
            inc_roic = d_np / d_ic
    # 再投资率（近一年）：(capex + 并购 − 折旧) / NOPAT
    latest_fy = years[-1] if years else None
    reinvest_rate = None
    if latest_fy is not None:
        capex = _g(fin, "PaymentsToAcquirePropertyPlantAndEquipment", latest_fy) or 0
        acq = _g(fin, "PaymentsToAcquireBusinessesNetOfCashAcquired", latest_fy) or 0
        da = _first(fin, ["DepreciationDepletionAndAmortization",
                          "DepreciationAmortizationAndAccretionNet"], latest_fy) or 0
        np_ = nopat(fin, latest_fy, default_tax)
        if np_ and np_ > 0:
            reinvest_rate = (capex + acq - da) / np_
    # 隐含可持续增长 = 增量ROIC × 再投资率。注意：再投资率用 capex 口径，
    # 对轻资产/重研发公司（capex < 折旧、靠研发和外包产能增长）会失真甚至为负——
    # 这种情况下这条线不适用，置空并加注，改看 ROIC 水平+趋势。
    asset_light = (reinvest_rate is not None and reinvest_rate < 0.05)
    implied_growth = None
    growth_note = None
    if inc_roic is not None and reinvest_rate is not None and not asset_light:
        implied_growth = inc_roic * reinvest_rate
    elif asset_light:
        growth_note = "轻资产/重研发：增长不靠 capex 再投资，隐含增长这条线不适用，看 ROIC 水平+趋势"
    # ROIC 失真检测：投入资本被大量现金冲到很小（分母失真），ROIC 会虚高到离谱。
    # 现金占资产比过高、或 ROIC>100%，多半是小分母假象（如现金/应收主导的贸易公司），
    # 这时 ROIC 数字不可信，改看 ROE/经营资产回报，由报告处理。
    latest_fy2 = years[-1] if years else None
    assets_latest = _g(fin, "Assets", latest_fy2) if latest_fy2 else None
    ic_latest = latest["invested_capital"] if latest else None
    # ROE = 净利 / 股东权益（始终有意义；ROIC 因现金失真时改看它）
    roe_latest = None
    if latest_fy2 is not None:
        ni_l = _net_income(fin, latest_fy2)
        eq_l = _g(fin, "StockholdersEquity", latest_fy2)
        if ni_l is not None and eq_l and eq_l > 0:
            roe_latest = ni_l / eq_l
    roic_distorted = False
    if latest and latest["roic"] is not None:
        if latest["roic"] > 1.0:
            roic_distorted = True
        if ic_latest is not None and assets_latest and assets_latest > 0 and ic_latest < 0.15 * assets_latest:
            roic_distorted = True

    # 粗分档（起点，非定论；Claude 在报告里据护城河证据确认/推翻）
    band = None
    if roic_distorted:
        band = "ROIC 口径失真（现金/小分母占比过高，改看 ROE）"
    elif latest and latest["roic"] is not None:
        r = latest["roic"]
        rising = (trend or 0) >= -0.02
        if r >= 0.20 and rising:
            band = "强复利"
        elif r >= 0.20:
            band = "高回报但走弱"
        elif r >= 0.10:
            band = "中等"
        elif r >= 0:
            band = "弱（接近资金成本）"
        else:
            band = "毁灭价值（ROIC<0）"
    return {
        "roic_latest": latest["roic"] if latest else None,
        "roe_latest": roe_latest,
        "roic_trend_delta": trend,
        "roic_series": [{"fy": s["fy"], "roic": s["roic"]} for s in series],
        "incremental_roic": inc_roic,
        "reinvestment_rate": reinvest_rate,
        "implied_sustainable_growth": implied_growth,
        "asset_light": asset_light,
        "growth_note": growth_note,
        "roic_distorted": roic_distorted,
        "band": band,
    }


def owner_earnings_quality(fin, n=5):
    """② 所有者盈余：报告 FCF、SBC 调整后 FCF、正常化所有者盈余、利润率与 SBC 拖累。"""
    years = _fy_list(fin, ["NetCashProvidedByUsedInOperatingActivities", "NetIncomeLoss"], n)
    rows = []
    for y in years:
        f = fcf(fin, y)
        sbc = _g(fin, "ShareBasedCompensation", y)
        rev = revenue(fin, y)
        ni = _net_income(fin, y)
        da = _first(fin, ["DepreciationDepletionAndAmortization",
                          "DepreciationAmortizationAndAccretionNet"], y)
        capex = _g(fin, "PaymentsToAcquirePropertyPlantAndEquipment", y)
        # 维护性 capex 代理 = min(capex, 折旧)（保守）
        maint_capex = None
        if capex is not None and da is not None:
            maint_capex = min(capex, da)
        elif capex is not None:
            maint_capex = capex
        # 正常化所有者盈余 = 净利 + 折旧 − 维护capex（巴菲特口径近似）
        oe_norm = None
        if ni is not None and da is not None and maint_capex is not None:
            oe_norm = ni + da - maint_capex
        rows.append({
            "fy": y,
            "fcf": f,
            "fcf_ex_sbc": (f - sbc) if (f is not None and sbc is not None) else None,
            "sbc": sbc,
            "owner_earnings_norm": oe_norm,
            "fcf_margin": (f / rev) if (f is not None and rev) else None,
            "sbc_pct_rev": (sbc / rev) if (sbc is not None and rev) else None,
            "sbc_pct_fcf": (sbc / f) if (sbc is not None and f and f > 0) else None,
        })
    latest = rows[-1] if rows else {}
    band = None
    f = latest.get("fcf")
    if f is not None:
        if f <= 0:
            band = "烧钱（FCF<0）"
        else:
            sp = latest.get("sbc_pct_fcf")
            if sp is not None and sp >= 0.5:
                band = "FCF 为正但 SBC 吞掉大半"
            elif latest.get("fcf_margin") and latest["fcf_margin"] >= 0.15:
                band = "强现金生成"
            else:
                band = "现金生成中等"
    return {"series": rows, "latest": latest, "band": band}


def capital_allocation(fin, n=5):
    """③ 资本配置记录卡：近 n 年每一块经营现金流去了哪。"""
    years = _fy_list(fin, ["NetCashProvidedByUsedInOperatingActivities"], n)
    agg = {"cfo": 0.0, "capex": 0.0, "acquisitions": 0.0, "buybacks": 0.0,
           "dividends": 0.0, "debt_repaid": 0.0, "debt_issued": 0.0}
    per_year = []
    for y in years:
        cfo = _g(fin, "NetCashProvidedByUsedInOperatingActivities", y)
        capex = _g(fin, "PaymentsToAcquirePropertyPlantAndEquipment", y)
        acq = _g(fin, "PaymentsToAcquireBusinessesNetOfCashAcquired", y)
        bb = _g(fin, "PaymentsForRepurchaseOfCommonStock", y)
        div = _first(fin, ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"], y)
        rep = _first(fin, ["RepaymentsOfLongTermDebt"], y)
        iss = _first(fin, ["ProceedsFromIssuanceOfLongTermDebt"], y)
        row = {"fy": y, "cfo": cfo, "capex": capex, "acquisitions": acq,
               "buybacks": bb, "dividends": div, "debt_repaid": rep, "debt_issued": iss}
        per_year.append(row)
        for k, v in [("cfo", cfo), ("capex", capex), ("acquisitions", acq),
                     ("buybacks", bb), ("dividends", div),
                     ("debt_repaid", rep), ("debt_issued", iss)]:
            if v is not None:
                agg[k] += v
    cfo_sum = agg["cfo"] or 0
    # 占累计经营现金流的比例（看钱主要去了哪）
    pct = {}
    if cfo_sum > 0:
        for k in ("capex", "acquisitions", "buybacks", "dividends", "debt_repaid"):
            pct[k] = agg[k] / cfo_sum
    returned = (agg["buybacks"] + agg["dividends"])  # 还给股东
    return {
        "years": years,
        "cumulative": agg,
        "pct_of_cfo": pct,
        "per_year": per_year,
        "shareholder_return_total": returned,
        "shareholder_return_pct_cfo": (returned / cfo_sum) if cfo_sum > 0 else None,
        "reinvest_pct_cfo": ((agg["capex"] + agg["acquisitions"]) / cfo_sum) if cfo_sum > 0 else None,
    }


def survival_test(fin, fy=None):
    """④ 生存测试：净债/EBITDA、利息覆盖、流动比、一年内到期墙 vs 现金。"""
    years = _fy_list(fin, ["StockholdersEquity", "Liabilities"], 1)
    if fy is None:
        fy = years[-1] if years else None
    if fy is None:
        return {}
    nd = net_debt(fin, fy)
    eb = ebitda(fin, fy)
    op = _g(fin, "OperatingIncomeLoss", fy)
    interest = _first(fin, ["InterestExpense", "InterestExpenseNonoperating", "FinanceExpense"], fy)
    ac = _g(fin, "AssetsCurrent", fy)
    lc = _g(fin, "LiabilitiesCurrent", fy)
    due_1yr = current_debt(fin, fy)  # 短借+一年内到期相加（修复取一不求和的低估）
    cash = excess_cash(fin, fy)
    nd_ebitda = (nd / eb) if (nd is not None and eb and eb > 0) else None
    # 利息覆盖仅在营业利润为正时有意义；亏损时为负/无意义，置空
    int_cov = (op / interest) if (op is not None and op > 0 and interest and interest > 0) else None
    current_ratio = (ac / lc) if (ac and lc) else None
    # 现金燃烧跑道：亏损公司"净现金"≠安全，要看烧多久。runway = 现金 / 年烧钱额
    f = fcf(fin, fy)
    burning = (f is not None and f < 0)
    runway_years = None
    if burning and cash is not None and cash > 0:
        runway_years = cash / (-f)
    # 粗分档
    band = None
    if nd is not None:
        net_cash = nd < 0
        if net_cash and burning:
            # 净现金但在烧——按跑道说话，不叫堡垒
            band = (f"净现金但在烧（约 {runway_years:.1f} 年跑道）"
                    if runway_years is not None else "净现金但在烧钱")
        elif net_cash:
            band = "堡垒（净现金）"
        elif nd_ebitda is not None and nd_ebitda <= 2 and (int_cov is None or int_cov >= 5):
            band = "稳健"
        elif nd_ebitda is not None and nd_ebitda <= 4:
            band = "承压"
        elif nd_ebitda is not None:
            band = "脆弱（高杠杆）"
        elif burning:
            # 有净债且在烧钱——最危险
            band = "脆弱（有净债且在烧钱）"
        else:
            # 有净债但 EBITDA≤0、衡量不了杠杆——盈利不足以支撑债务，承压偏脆弱
            band = "承压（有净债、盈利不足以覆盖）"
    return {
        "fy": fy,
        "net_debt": nd,
        "is_net_cash": (nd < 0) if nd is not None else None,
        "net_debt_to_ebitda": nd_ebitda,
        "interest_coverage": int_cov,
        "current_ratio": current_ratio,
        "debt_due_1yr": due_1yr,
        "cash": cash,
        "due_vs_cash_covered": (cash >= due_1yr) if (cash is not None and due_1yr is not None) else None,
        "is_burning_cash": burning,
        "cash_runway_years": runway_years,
        "band": band,
        "debt_components": debt_components(fin, fy),
    }


def earnings_quality(fin, n=5):
    """盈利质量取证（代码初筛，2026-06-10 新增）：
    应计占比 = (净利 − 经营现金流)/|净利|，持续为正且大 = 利润纸面成分高；
    应收增速 vs 营收增速剪刀差、存货增速 vs 营收增速。
    flags 不是定论——一次性项目/季节性/并表变化都可能造成假阳性，逐项回年报核。
    数据缺哪项空哪项并列入 coverage_missing（缺口必须被看见）。"""
    years = _fy_list(fin, ["NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities"], n)
    rows = []
    for y in years:
        ni = _net_income(fin, y)
        cfo = _g(fin, "NetCashProvidedByUsedInOperatingActivities", y)
        rev = revenue(fin, y)
        ar = _first(fin, ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
                          "AccountsNotesAndLoansReceivableNetCurrent"], y)
        inv = _first(fin, ["InventoryNet", "Inventories"], y)
        accrual = ((ni - cfo) / abs(ni)) if (ni not in (None, 0) and cfo is not None) else None
        rows.append({"fy": y, "net_income": ni, "cfo": cfo, "accrual_ratio": accrual,
                     "revenue": rev, "receivables": ar, "inventory": inv})

    def _cagr(key):
        pts = [r[key] for r in rows if r[key] is not None and r[key] > 0]
        if len(pts) >= 2:
            return (pts[-1] / pts[0]) ** (1.0 / (len(pts) - 1)) - 1.0
        return None

    g_rev, g_ar, g_inv = _cagr("revenue"), _cagr("receivables"), _cagr("inventory")
    scissors_ar = (g_ar - g_rev) if (g_ar is not None and g_rev is not None) else None
    scissors_inv = (g_inv - g_rev) if (g_inv is not None and g_rev is not None) else None
    flags = []
    if len([r for r in rows if r["accrual_ratio"] is not None and r["accrual_ratio"] > 0.5]) >= 3:
        flags.append("应计占比连年偏高（净利长期显著高于经营现金流）——利润纸面成分需人工深查")
    if scissors_ar is not None and scissors_ar > 0.10:
        flags.append("应收增速年化快于营收超10pp——收入质量/渠道压货需人工深查")
    if scissors_inv is not None and scissors_inv > 0.10:
        flags.append("存货增速年化快于营收超10pp——跌价/需求需人工深查")
    coverage_missing = []
    if not any(r["receivables"] is not None for r in rows):
        coverage_missing.append("应收账款（原表缺或取数管道未覆盖）")
    if not any(r["inventory"] is not None for r in rows):
        coverage_missing.append("存货（原表缺或取数管道未覆盖）")
    return {"series": rows, "revenue_cagr_approx": g_rev,
            "receivable_scissors": scissors_ar, "inventory_scissors": scissors_inv,
            "flags": flags, "coverage_missing": coverage_missing,
            "note": "代码初筛非定论；flags 逐项回年报附注核，结论由报告第七章会计可信度节下"}


def scenario_irr(current_price, value_per_share, years=5):
    """隐含年化回报 = (价值/现价)^(1/years) − 1。机械标尺、不是预测；
    喂 decision.json 的 expected_irr_5y 与 odds（见 skills/postmortem.md 动作一）。"""
    if not current_price or not value_per_share or current_price <= 0 or value_per_share <= 0:
        return None
    return (value_per_share / current_price) ** (1.0 / years) - 1.0


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def cycle_calibration(fin, default_tax=0.21):
    """周期校准（横切四柱，不是宏观择时）：识别 ROIC/利润率近 1-2 年的垂直拉升，
    给"当前可能是周期高峰、别把它当常态"打一面旗。提醒报告做归一化、别为高峰付全款。"""
    years = _fy_list(fin, ["OperatingIncomeLoss"], 8)
    roic_pts = [(y, roic(fin, y, default_tax)) for y in years]
    # 剔除失真的 ROIC（>100% 多半是现金小分母假象，不是真周期），避免假阳性
    roic_valid = [(y, r) for y, r in roic_pts if r is not None and r <= 1.0]
    op_margin = []
    for y in years:
        op = _g(fin, "OperatingIncomeLoss", y)
        rev = revenue(fin, y)
        if op is not None and rev:
            op_margin.append((y, op / rev))

    def _spike(series):
        # 近 1 年 vs 剔除最近 2 年后的基线中位数。基线>3% 且 最新>1.5×基线 → 高峰存疑
        if len(series) < 4:
            return None
        latest = series[-1][1]
        baseline = _median([v for _, v in series[:-2]])
        if baseline is None or baseline <= 0.03 or latest is None:
            return None
        ratio = latest / baseline
        return {"latest": latest, "baseline": baseline, "ratio": ratio,
                "spike": ratio >= 1.5}

    roic_spike = _spike(roic_valid)
    margin_spike = _spike(op_margin)
    peak_suspect = bool((roic_spike and roic_spike["spike"]) or
                        (margin_spike and margin_spike["spike"]))
    note = None
    if peak_suspect:
        note = ("近 1-2 年 ROIC/利润率较历史基线垂直拉升——当前很可能是周期高峰，"
                "别把它当永久水平资本化；报告需做中周期归一化、并把周期转冷写成核心 Bear。")
    return {
        "peak_suspect": peak_suspect,
        "roic": roic_spike,
        "operating_margin": margin_spike,
        "note": note,
    }


def compute_value_metrics(fin, n=5, default_tax=0.21):
    """汇总四柱 + 周期校准 + 盈利质量取证 → metrics.json 的内容。纯数字 + 粗分档，不下最终判断。"""
    return {
        "compounding_engine": compounding_engine(fin, n, default_tax),
        "owner_earnings": owner_earnings_quality(fin, n),
        "capital_allocation": capital_allocation(fin, n),
        "survival": survival_test(fin),
        "cycle_calibration": cycle_calibration(fin, default_tax),
        "earnings_quality": earnings_quality(fin, n),
    }


# ============================================================
# 命令行入口（测试用）
# ============================================================

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RKLB"
    fin = load_financials(ticker)
    years = sorted(fin.get("NetIncomeLoss", {}).keys())
    print(f"{ticker} 可用财年：{years}")
    if years:
        latest = years[-1]
        oe = owner_earnings(fin, latest)
        if oe is not None:
            sign = "正" if oe > 0 else "负"
            print(f"{latest} 所有者盈余（近似 = CFO - CapEx）：${oe/1e6:,.1f}M（{sign}）")

        # 累计所有者盈余 → 用来判断走 Track A 还是 Track B
        recent5 = years[-5:]
        oe_list = [owner_earnings(fin, y) for y in recent5]
        oe_list = [x for x in oe_list if x is not None]
        if oe_list:
            cum = sum(oe_list)
            pos_years = sum(1 for x in oe_list if x > 0)
            print(f"近 {len(oe_list)} 年所有者盈余：{[f'${x/1e6:,.0f}M' for x in oe_list]}")
            print(f"累计 ${cum/1e6:,.0f}M；其中 {pos_years} 年为正")
            if cum > 0 and pos_years >= 3:
                print("→ 建议走 Track A（标准 DCF）")
            else:
                print("→ 建议走 Track B（情景前瞻 + 反向 DCF）")
