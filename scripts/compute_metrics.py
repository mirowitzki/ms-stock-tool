#!/usr/bin/env python3
# 花名：莫德里奇 —— 团队花名册见 CLAUDE.md「团队花名册」节
"""
compute_metrics.py —— 算一次、用两处的"价值判断四柱"真相源。

从 financials.csv 用 valuation.py 的纯代码函数算出：
  ① 复利引擎(ROIC/增量ROIC/再投资)  ② 所有者盈余(正常化/SBC调整)
  ③ 资本配置记录卡(每块现金去向)      ④ 生存测试(净债/覆盖/到期墙)
落成 analyses/<TICKER>/financials/metrics.json。

这是单一真相源：交互器仪表盘读它、报告引用它、check_numbers.py 对账回它。
三处咬同一组代码算出来的数字，永不漂移。

用法：python scripts/compute_metrics.py NVDA
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation as V


def main(ticker):
    ticker = ticker.upper()
    base = Path("analyses") / ticker
    fin_path = base / "financials" / "financials.csv"
    if not fin_path.exists():
        sys.exit(f"错误：找不到 {fin_path}。先跑 fetch_filings.py / fetch_a_stocks.py。")

    fin = V.load_financials(ticker)
    # 货币/税率：6 位纯数字代码 = A 股（CNY，默认税率 25%）；否则美股（USD，21%）
    is_cn = ticker.isdigit() and len(ticker) == 6
    default_tax = 0.25 if is_cn else 0.21
    currency = "CNY" if is_cn else "USD"

    metrics = V.compute_value_metrics(fin, n=5, default_tax=default_tax)
    out = {
        "ticker": ticker,
        "currency": currency,
        "default_tax_rate": default_tax,
        "unit": "原始货币单位（与 financials.csv 一致）",
        "metrics": metrics,
        "_note": "纯代码算出的硬数字 + 粗分档；最终判断由报告结合定性证据下，但须引用这些数字。",
    }
    out_path = base / "financials" / "metrics.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {out_path}")

    # 打印一眼可读的摘要
    ce = metrics["compounding_engine"]
    sv = metrics["survival"]
    oe = metrics["owner_earnings"]
    oel = oe["latest"]
    ca = metrics["capital_allocation"]

    def pct(v):
        return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "—"

    def num(v, suffix="", fmt="{:.2f}"):
        return (fmt.format(v) + suffix) if isinstance(v, (int, float)) else "—"

    roic_disp = pct(ce['roic_latest']) + ("(失真)" if ce.get("roic_distorted") else "")
    print(f"  ① 复利引擎：ROIC={roic_disp} ROE={pct(ce.get('roe_latest'))}（{ce['band']}）"
          f" 增量ROIC={pct(ce['incremental_roic'])} 再投资率={pct(ce['reinvestment_rate'])}"
          + ("  [轻资产]" if ce.get("asset_light") else ""))
    print(f"  ② 所有者盈余：{oe.get('band') or '—'}"
          f" FCF利润率={pct(oel.get('fcf_margin'))} SBC占FCF={pct(oel.get('sbc_pct_fcf'))}")
    print(f"  ③ 资本配置(近5年)：再投资占CFO={pct(ca['reinvest_pct_cfo'])}"
          f" 还股东占CFO={pct(ca['shareholder_return_pct_cfo'])}")
    print(f"  ④ 生存：{sv.get('band') or '—'}"
          f" 净债/EBITDA={num(sv.get('net_debt_to_ebitda'))}"
          f" 利息覆盖={num(sv.get('interest_coverage'), 'x', '{:.1f}')}")
    dc = sv.get("debt_components") or {}
    if dc.get("missing"):
        print(f"  · 净债口径覆盖：找到 {len(dc.get('found', {}))} 项、缺 {len(dc['missing'])} 项"
              f"（{'、'.join(dc['missing'])}）——全口径以年报附注为准")
    cdp = sv.get("cash_debt_paradox") or {}
    if cdp.get("flag"):
        legs = []
        if cdp.get("both_high"):
            legs.append(f"存贷双高（现金占总资产{pct(cdp.get('cash_pct_assets'))}、有息负债占{pct(cdp.get('debt_pct_assets'))}）")
        if cdp.get("net_cash_but_paying"):
            legs.append("净现金却付净财务费用")
        print(f"  ⚠ 现金验真：{'；'.join(legs)}——回年报附注抄利息收入、倒算隐含存款收益率"
              f"（fact-check 现金验真查项，康得新/康美式指纹初筛）")
    eq = metrics.get("earnings_quality") or {}
    for fl in eq.get("flags", []):
        print(f"  ⚠ 盈利质量：{fl}")
    if eq.get("coverage_missing"):
        print(f"  · 盈利质量覆盖缺口：{'、'.join(eq['coverage_missing'])}")
    cyc = metrics["cycle_calibration"]
    if cyc.get("peak_suspect"):
        rs = cyc.get("roic") or {}
        print(f"  ⚠ 周期校准：高峰存疑（ROIC 最新 {pct(rs.get('latest'))} vs 基线 {pct(rs.get('baseline'))}）"
              f"——别把当前数字当常态")
    else:
        print(f"  · 周期校准：无明显高峰拉升")
    rt = metrics.get("revenue_trend") or {}
    if rt.get("flag"):
        print(f"  ⚠ 量层剪刀差候选：营收连续 {rt.get('consecutive_down_years')} 个财年下滑"
              f"——护城河结论降级为待证假设、先走周期vs塌方判别（skills/moat-analysis.md）")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：python scripts/compute_metrics.py <TICKER>")
    main(sys.argv[1])
