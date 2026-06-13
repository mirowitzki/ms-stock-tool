#!/usr/bin/env python3
"""refresh_quotes.py —— 免费刷新所有已分析公司的最新收盘价（纯代码，零 Max / 零 API 费）。

为什么能免费：每天变的只有"价格层"（现价 / 市值 / 安全边际 / 梯队排名 / 反向DCF隐含），
判断内核（情景 / 概率 / 四柱 / 加权中枢）只在出新财报时才动。刷价是纯计算、不需要判断，
所以走纯代码、复用 fetch_prices 的免费新浪日线源（一次请求拿月度走势 + 最新收盘）。

干什么：
  1. 扫 analyses/ 下每家公司，抓最新交易日收盘；
  2. 刷各家 financials/prices.json（股价走势图末点跟着新）；
  3. 写 analyses/_quotes.json（一份、含所有公司 + refreshed_at，喂仪表盘梯队/卡片与交互器）；
  4. 重渲各家交互器（现价一换，安全边际 / 反向DCF / 市场vs我全部自动重算）。
  judgment 内核（valuation_inputs 的 scenarios/pillars/probabilities）一律不碰，只叠加"今日"这一层。

注意：免费源给的是收盘价（EOD），不是盘中实时——对价值工具这是对的。

用法：
  python scripts/refresh_quotes.py              刷全部已分析公司
  python scripts/refresh_quotes.py NVDA 000009  只刷指定几只
  python scripts/refresh_quotes.py --no-render   只刷价、不重渲交互器（更快）
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_prices import fetch_daily_df, _monthly_from_daily, _latest_from_daily, MONTHS


def refresh(tickers=None, render_explorers=True):
    """刷新报价。返回 {"refreshed_at", "quotes": {ticker: {price, as_of, currency}}, "ok": [...], "fail": [...]}。"""
    analyses = Path("analyses")
    if tickers:
        codes = [t.upper() for t in tickers]
    else:
        codes = sorted(d.name for d in analyses.iterdir()
                       if d.is_dir() and not d.name.startswith((".", "_")))

    quotes_path = analyses / "_quotes.json"
    quotes = {}
    if quotes_path.exists():
        try:
            quotes = json.loads(quotes_path.read_text(encoding="utf-8")).get("quotes", {})
        except Exception:
            quotes = {}

    ok, fail = [], []
    for code in codes:
        is_cn = code.isdigit() and len(code) == 6
        currency = "CNY" if is_cn else "USD"
        try:
            df = fetch_daily_df(code)
            latest = _latest_from_daily(df)
            quotes[code] = {"price": latest["price"], "as_of": latest["as_of"], "currency": currency}
            # 顺手刷月度走势（图末点跟着新）
            fin = analyses / code / "financials"
            if fin.exists():
                monthly = _monthly_from_daily(df)[-MONTHS:]
                (fin / "prices.json").write_text(
                    json.dumps({"ticker": code, "currency": currency, "prices": monthly},
                               ensure_ascii=False, indent=2), encoding="utf-8")
            ok.append(code)
            sym = "￥" if is_cn else "$"
            print(f"✓ {code:<7} {sym}{latest['price']}  ({latest['as_of']})")
        except Exception as e:
            fail.append(code)
            old = quotes.get(code, {}).get("price")
            print(f"✗ {code:<7} 抓取失败、沿用旧值（{old}）：{e}")

    out = {"refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quotes": quotes}
    quotes_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写 {quotes_path}：成功 {len(ok)}、失败 {len(fail)}")

    # 重渲交互器：现价（=市值÷股数）换成今日价后，交互器里所有价格层数字自动重算
    if render_explorers and ok:
        try:
            from render_explorer import render as render_explorer
        except Exception as e:
            print(f"（跳过重渲交互器：{e}）")
            render_explorer = None
        if render_explorer:
            n = 0
            for code in ok:
                if not (analyses / code / "valuation_inputs.json").exists():
                    continue
                try:
                    render_explorer(code)
                    n += 1
                except BaseException as e:  # render 内部用 sys.exit、要一并兜住
                    print(f"（{code} 交互器重渲失败、跳过：{e}）")
            print(f"已重渲 {n} 家交互器")

    out["ok"] = ok
    out["fail"] = fail
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_render = "--no-render" in sys.argv
    refresh(args or None, render_explorers=not no_render)
    # CLI 跑完顺手刷新 dashboard.html（把最新价灌进梯队/卡片）
    try:
        from refresh_dashboard import main as refresh_dashboard
        refresh_dashboard()
    except Exception as e:
        print(f"（刷新 dashboard 失败：{e}）")
