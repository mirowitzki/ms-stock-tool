#!/usr/bin/env python3
"""
fetch_prices.py —— 抓近 ~5 年月度收盘价，喂给交互器画股价走势图。

数据源（都走已装好的 akshare、免费、符合"不碰付费 API"）：
  美股   ak.stock_us_daily(symbol, adjust="qfq")          日线 → 重采样成月末收盘
  A 股   ak.stock_zh_a_daily(symbol=前缀+code, adjust="qfq")  日线（新浪源，沙箱代理可达）→ 重采样成月末收盘
日线 DataFrame 同时供 refresh_quotes.py 取最新一天收盘做免费报价刷新（一次请求两用）。

产物：analyses/<TICKER>/financials/prices.json
  {"ticker","currency","prices":[{"m":"YYYY-MM","c":收盘价}, ...]}  最近 60 个月

用法：python scripts/fetch_prices.py NVDA
"""

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

MONTHS = 60  # 近 5 年


def _monthly_from_daily(df):
    """日线 DataFrame（含 date/close 列）→ 每月最后交易日收盘的月度列表。"""
    import pandas as pd
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df["ym"] = df.index.to_period("M")
    monthly = df.groupby("ym")["close"].last()
    return [{"m": str(ym), "c": round(float(c), 2)} for ym, c in monthly.items()]


def _latest_from_daily(df):
    """日线 DataFrame → 最新一个交易日的 {price, as_of}（喂免费报价刷新）。"""
    import pandas as pd
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date")
    last = d.iloc[-1]
    return {"price": round(float(last["close"]), 2), "as_of": str(pd.to_datetime(last["date"]).date())}


def _cn_prefix(code):
    c0 = code[0]
    if c0 == "6":          # 沪市主板/科创板
        return "sh"
    if c0 in "03":         # 深市主板/中小(0)、创业板(3)
        return "sz"
    if c0 in "48":         # 北交所
        return "bj"
    return "sz"


def fetch_daily_df(ticker):
    """返回日线 DataFrame（含 date/close），美股走 stock_us_daily、A股走 stock_zh_a_daily。
    都是已装好的免费新浪源（沙箱代理可达；eastmoney 的 stock_zh_a_hist 常被掐断）。
    月度走势与最新报价都从这一个 df 派生（一次网络请求两用）。"""
    import akshare as ak
    t = ticker.upper()
    if t.isdigit() and len(t) == 6:
        return ak.stock_zh_a_daily(symbol=_cn_prefix(t) + t, adjust="qfq")
    return ak.stock_us_daily(symbol=t, adjust="qfq")


def fetch_us(ticker):
    return _monthly_from_daily(fetch_daily_df(ticker))


def fetch_cn(code):
    return _monthly_from_daily(fetch_daily_df(code))


def main(ticker):
    ticker = ticker.upper()
    is_cn = ticker.isdigit() and len(ticker) == 6
    currency = "CNY" if is_cn else "USD"
    try:
        prices = fetch_cn(ticker) if is_cn else fetch_us(ticker)
    except Exception as e:
        sys.exit(f"抓股价失败（{ticker}）：{e}")
    prices = prices[-MONTHS:]
    out = {"ticker": ticker, "currency": currency, "prices": prices}
    base = Path("analyses") / ticker / "financials"
    base.mkdir(parents=True, exist_ok=True)
    (base / "prices.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if prices:
        print(f"已生成 {base/'prices.json'}：{len(prices)} 个月（{prices[0]['m']} → {prices[-1]['m']}，"
              f"最新收盘 {prices[-1]['c']}）")
    else:
        print(f"警告：{ticker} 没抓到价格数据")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：python scripts/fetch_prices.py <TICKER>")
    main(sys.argv[1])
