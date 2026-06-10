#!/usr/bin/env python3
"""
fetch_filings.py —— 第 0 层：从 SEC EDGAR 抓取某只股票的申报文件与结构化财务数据。

这是整条流水线的入口。它把公司的披露沿着工具依赖的那条“缝”切开：

  - 叙述性文本（10-K / 委托书） -> 第 1 层“理解生意”（Claude 来读）
  - 结构化财务数据（XBRL）       -> 估值计算（代码用精确数字来算）

这里没有任何大模型调用，是纯粹的“管道”，运行起来不花一分钱。

用法：
    export SEC_USER_AGENT="你的名字 your.email@example.com"   # SEC 强制要求真实标识
    python fetch_filings.py RKLB --years 5

产出（落在 ./analyses/<TICKER>/ 下）：
    filings/     每份 10-K 的清洗后正文 + 最新一份委托书（DEF 14A）
                  + 招股 / 上市文件（S-1、S-4、424B 等，每种取最早一份）
    financials/  companyfacts.json（原始 XBRL）+ financials.csv（整理后的年度序列）
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

REQUEST_PAUSE = 0.2  # 每次请求间隔（秒）；SEC 公平访问限制约为 10 次/秒

# 价值分析关心的 us-gaap 概念清单。公司没有用这些标签申报的，直接跳过，不会报错。
# 招股书 / 上市文件相关表单。对 SPAC 合并上市的公司，关键文件是 S-4 + 424B3。
# 对各类表单，下面取“最早的一份”——也就是最接近 IPO / 合并事件那一版。
PROSPECTUS_FORMS = ["S-1", "S-1/A", "S-4", "S-4/A", "424B3", "424B4"]


KEY_CONCEPTS = [
    # —— 利润表 ——
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",        # 部分申报人用这个记营业成本（如 NVTS），非 CostOfRevenue
    "CostOfGoodsSold",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "ProfitLoss",                        # 部分申报人近年合并净利/净亏用 ProfitLoss（如 NVTS FY2025）
    "ResearchAndDevelopmentExpense",
    "IncomeTaxExpenseBenefit",          # 所得税 → 有效税率（算 NOPAT/ROIC）
    "InterestExpense",                  # 利息费用（算利息覆盖/生存）
    "InterestExpenseNonoperating",
    # —— 资产负债表（投入资本 / 生存）——
    "Assets",
    "AssetsCurrent",
    "Liabilities",
    "LiabilitiesCurrent",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",   # 部分申报人用的现金+短投合并标签（如 SITM）
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashAndCashEquivalentsAtCarryingValueIncludingDiscontinuedOperations",
    "ShortTermInvestments",             # 现金等价的短投（净现金口径）
    "LongTermDebtNoncurrent",
    "LongTermDebt",                     # 部分申报人用单一总额标签
    "LongTermDebtCurrent",              # 长期债当期到期部分（到期墙）
    "DebtCurrent",
    "ShortTermBorrowings",
    "Goodwill",                          # 并购溢价沉淀（资本配置质量）
    "AccountsReceivableNetCurrent",      # 盈利质量取证：应收 vs 营收剪刀差
    "ReceivablesNetCurrent",
    "InventoryNet",                      # 盈利质量取证：存货 vs 营收剪刀差
    # —— 现金流量表（所有者盈余 + 资本配置记录卡）——
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",   # 资本开支
    "DepreciationDepletionAndAmortization",         # 折旧摊销（EBITDA/维护capex代理）
    "DepreciationAmortizationAndAccretionNet",
    "ShareBasedCompensation",                       # 股权激励（所有者盈余调整，科技股关键）
    "PaymentsForRepurchaseOfCommonStock",           # 回购
    "PaymentsOfDividendsCommonStock",               # 分红
    "PaymentsOfDividends",
    "PaymentsToAcquireBusinessesNetOfCashAcquired", # 并购
    "ProceedsFromIssuanceOfLongTermDebt",           # 举债
    "RepaymentsOfLongTermDebt",                     # 还债
]


def user_agent():
    # SEC 要求每个请求带上能识别身份的 User-Agent，否则会被封。
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "example.com" in ua:
        sys.exit(
            "错误：请先设置真实的 SEC_USER_AGENT，例如：\n"
            '  export SEC_USER_AGENT="Jane Doe jane@gmail.com"\n'
            "SEC 会拦截缺少真实标识的请求。"
        )
    return ua


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    return s


def get(session, url, as_json=False):
    """有礼貌的 GET：限速 + 出错抛异常。"""
    time.sleep(REQUEST_PAUSE)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json() if as_json else r.text


def resolve_cik(session, ticker):
    # 用 SEC 的 ticker->CIK 映射表，把股票代码解析成中央索引号（CIK）。
    data = get(session, SEC_TICKERS_URL, as_json=True)
    ticker = ticker.upper()
    for row in data.values():
        if row.get("ticker", "").upper() == ticker:
            return int(row["cik_str"]), row.get("title", ticker)
    sys.exit(f"错误：在 SEC 公司列表里找不到代码 {ticker}。")


def pick_filings(submissions, years):
    """返回（近 years 年内的 10-K 列表，最新一份委托书，招股 / 上市文件列表）。"""
    recent = submissions["filings"]["recent"]
    cutoff = datetime.now(timezone.utc).year - years
    tenks, proxies = [], []
    prospectus_by_form = {}
    for form, acc, doc, fdate, rdate in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["filingDate"],
        recent["reportDate"],
    ):
        if not doc:  # 有些条目没有主文档
            continue
        item = {"accession": acc, "doc": doc, "filed": fdate, "report": rdate, "form": form}
        if form == "10-K" and int(fdate[:4]) >= cutoff:
            tenks.append(item)
        elif form == "DEF 14A":
            proxies.append(item)
        elif form in PROSPECTUS_FORMS:
            prospectus_by_form.setdefault(form, []).append(item)
    # recent 列表是“最新在前”，所以 [:1] 就是最新一份委托书
    # 招股书：每种表单取“最早的一份”，因为最接近 IPO / 合并事件的就是最关键的那一版
    prospectus = []
    for form in PROSPECTUS_FORMS:
        items = prospectus_by_form.get(form, [])
        if items:
            prospectus.append(sorted(items, key=lambda x: x["filed"])[0])
    return tenks, proxies[:1], prospectus


def html_to_text(html):
    # 把 10-K 的 HTML 清洗成纯文本，交给 Claude 阅读（不在代码里硬切章节，交给判断层去找）。
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def download_filing(session, cik, item, out_dir, label):
    acc_nodash = item["accession"].replace("-", "")
    url = ARCHIVE_DOC_URL.format(cik=cik, acc=acc_nodash, doc=item["doc"])
    text = html_to_text(get(session, url))
    # 招股书等表单没有“报告期”，退回到“申报日”作为文件名的时间标签
    date_for_name = item.get("report") or item["filed"]
    fname = f"{label}_{date_for_name}.txt"
    (out_dir / fname).write_text(text, encoding="utf-8")
    print(f"  已保存 {fname}  （{len(text):,} 字符）")


def fetch_financials(session, cik, out_dir):
    facts = get(session, COMPANYFACTS_URL.format(cik=cik), as_json=True)
    (out_dir / "companyfacts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False))
    gaap = facts.get("facts", {}).get("us-gaap", {})

    # 每个“概念 + 财年”只保留一个年度值（来自 10-K 的全年数据）。
    best = {}
    for concept in KEY_CONCEPTS:
        for unit, entries in gaap.get(concept, {}).get("units", {}).items():
            for e in entries:
                if e.get("form") == "10-K" and e.get("fp") == "FY":
                    key = (concept, e.get("fy"))
                    if key not in best or e.get("end", "") > best[key][2]:
                        best[key] = (concept, e.get("fy"), e.get("end"), e.get("val"), unit)

    with (out_dir / "financials.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concept", "fiscal_year", "period_end", "value", "unit"])
        for r in sorted(best.values(), key=lambda x: (x[0], x[1] or 0)):
            w.writerow(r)
    print(f"  已保存 companyfacts.json + financials.csv（{len(best)} 个数据点）")


def main():
    ap = argparse.ArgumentParser(description="从 SEC EDGAR 抓取某只股票的申报文件与财务数据。")
    ap.add_argument("ticker")
    ap.add_argument("--years", type=int, default=5, help="抓取近几年的 10-K（默认 5 年）")
    args = ap.parse_args()

    session = make_session()
    cik, name = resolve_cik(session, args.ticker)
    print(f"{args.ticker.upper()} = {name}（CIK {cik}）")

    base = Path("analyses") / args.ticker.upper()
    filings_dir, fin_dir = base / "filings", base / "financials"
    filings_dir.mkdir(parents=True, exist_ok=True)
    fin_dir.mkdir(parents=True, exist_ok=True)

    submissions = get(session, SUBMISSIONS_URL.format(cik=cik), as_json=True)
    tenks, proxies, prospectus = pick_filings(submissions, args.years)
    print(
        f"近 {args.years} 年找到 {len(tenks)} 份 10-K，"
        f"{len(proxies)} 份委托书，{len(prospectus)} 份招股 / 上市文件"
    )

    print("正在下载 10-K：")
    for item in tenks:
        download_filing(session, cik, item, filings_dir, "10-K")
    if proxies:
        print("正在下载委托书：")
        for item in proxies:
            download_filing(session, cik, item, filings_dir, "DEF14A")
    if prospectus:
        print("正在下载招股 / 上市文件：")
        for item in prospectus:
            # 文件名里不能有斜杠，"S-4/A" 写成 "S-4-A"
            label = item["form"].replace("/", "-").replace(" ", "")
            download_filing(session, cik, item, filings_dir, label)

    print("正在抓取财务数据（XBRL）：")
    fetch_financials(session, cik, fin_dir)

    print(f"\n完成。全部内容已保存在 {base}/")


if __name__ == "__main__":
    main()
