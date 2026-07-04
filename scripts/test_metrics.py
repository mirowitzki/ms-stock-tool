#!/usr/bin/env python3
# 花名：加图索 —— 团队花名册见 CLAUDE.md「团队花名册」节
"""
test_metrics.py —— 估值/四柱计算的金标准回归测试。

来历（2026-06-10）：净债计算曾因"几个负债科目取一不求和"系统性低估 A 股杠杆
（300199 算 7.71 亿、实为约 18 亿；000925 算 5.23 亿、实为约 11.28 亿），
且 check_numbers 把 metrics 当地面真值、会替错数背书。本测试把已人工核实过
的真值钉成金标准——以后改 valuation.py / compute_metrics.py / fetch 管道后必须跑一遍：

    python3 scripts/test_metrics.py

全部 PASS 才许重渲交付物。新增公司若人工核过净债，请往 GOLDEN 里加一行。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation as V

# (ticker, 指标, 期望值, 相对容差, 备注)
# A 股金标准 = 年报附注口径人工核实；美股 = 修复时点的无回归锁定值。
GOLDEN = [
    ("000009", "total_debt", 204.31e8, 0.02, "年报口径合并有息负债约204亿（LESSONS 已核）"),
    ("000925", "total_debt", 27.75e8, 0.02, "速查表有息负债27.75亿（年报口径）"),
    ("000925", "net_debt",   11.28e8, 0.03, "速查表净负债约11亿"),
    ("300199", "net_debt",   18.04e8, 0.03, "报告全口径净负债约18亿（含短借10.33亿）"),
    ("300085", "net_debt",   -0.59e8, 0.10, "严口径净现金约0.6亿（LESSONS 已核）"),
    ("002091", "net_debt", -187.42e8, 0.02, "修复后口径（含短借38.77亿的净现金）"),
    # 美股：修复不应改变（通常只申报单一科目）——锁定无回归
    ("NVDA", "net_debt", -2137e6, 0.02, "无回归锁定"),
    ("SWKS", "net_debt", -166e6, 0.05, "无回归锁定"),
    ("NVTS", "net_debt", -237e6, 0.05, "无回归锁定"),
    ("RKLB", "net_debt", -827e6, 0.02, "无回归锁定"),
    ("SITM", "net_debt", -17e6, 0.10, "无回归锁定"),
    ("CRCL", "net_debt", -1526e6, 0.02, "无回归锁定"),
]


def rel_err(got, want):
    if want == 0:
        return abs(got)
    return abs(got - want) / abs(want)


def main():
    failures = []
    fins = {}
    for ticker, metric, want, tol, note in GOLDEN:
        if ticker not in fins:
            try:
                fins[ticker] = V.load_financials(ticker)
            except Exception as e:
                failures.append(f"✗ {ticker} 数据加载失败：{e}")
                fins[ticker] = None
                continue
        fin = fins[ticker]
        if fin is None:
            continue
        sv = V.survival_test(fin)
        fy = sv.get("fy")
        got = V.total_debt(fin, fy) if metric == "total_debt" else sv.get("net_debt")
        if got is None:
            failures.append(f"✗ {ticker} {metric} 算出 None（期望 {want:,.0f}）—— {note}")
            continue
        err = rel_err(got, want)
        status = "✓" if err <= tol else "✗"
        line = f"{status} {ticker:<7}{metric:<11} got={got:>18,.0f} want={want:>18,.0f} err={err*100:.1f}% ｜{note}"
        print(line)
        if err > tol:
            failures.append(line)

    # 纯函数自检
    irr = V.scenario_irr(100, 200, 5)
    if irr is None or abs(irr - 0.1487) > 0.002:
        failures.append(f"✗ scenario_irr(100,200,5) = {irr}（期望约 0.1487）")
    else:
        print(f"✓ scenario_irr 自检 {irr:.4f} ≈ 14.87%/yr")
    # earnings_quality 对全部公司可运行（不抛异常、结构齐全）
    for t in set(g[0] for g in GOLDEN):
        if fins.get(t) is None:
            continue
        eq = V.earnings_quality(fins[t])
        if not isinstance(eq, dict) or "series" not in eq:
            failures.append(f"✗ {t} earnings_quality 结构异常")
    print("✓ earnings_quality 全部可运行" if not any("earnings_quality" in f for f in failures) else "")

    print("=" * 60)
    if failures:
        print(f"测试未通过：{len(failures)} 项")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("全部 PASS。改了 valuation/compute_metrics/fetch 之后才放心重渲交付物。")


if __name__ == "__main__":
    main()
