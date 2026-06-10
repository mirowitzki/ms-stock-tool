#!/usr/bin/env python3
"""
fetch_a_stocks.py —— A 股取数（与 fetch_filings.py 对齐的姊妹脚本）

从 AKShare 拉财务数据，从巨潮资讯网下载年报 PDF + 提取文本。
落到 analyses/<6位代码>/ 下，结构和美股管道一致：
  filings/      年报 PDF + 提取的纯文本（供 Claude 阅读）
  financials/   financials.csv（结构与美股一致，单位 CNY）+ companyfacts.json
  company_info.json  基础信息

用法：
    python scripts/fetch_a_stocks.py 688237 --years 5

不需要 API key——AKShare 是开源数据聚合库。
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

# 静默 akshare 的进度条 + warning
import warnings
warnings.filterwarnings("ignore")


# ============================================================
# 概念映射：把 AKShare/中国财报概念翻译成与美股 XBRL 一致的英文 key
# 这样 valuation.py 和 render_explorer.py 不需要为 A 股做任何改动
# ============================================================

# 从 stock_financial_abstract "常用指标" 里取
ABSTRACT_MAP = {
    "营业总收入": "Revenues",
    "归母净利润": "NetIncomeLoss",
    "净利润": "NetIncomeLossTotal",
    "营业成本": "CostOfRevenue",
    "股东权益合计(净资产)": "StockholdersEquity",
    "经营现金流量净额": "NetCashProvidedByUsedInOperatingActivities",
    "商誉": "Goodwill",
}

# 资产负债表
BALANCE_MAP = {
    "资产总计": "Assets",
    "负债合计": "Liabilities",
    "货币资金": "CashAndCashEquivalentsAtCarryingValue",
    "交易性金融资产": "ShortTermInvestments",            # 理财——"真实净现金"必须算上
    "短期借款": "ShortTermBorrowings",
    "一年内到期的非流动负债": "CurrentPortionLongTermDebt",
    "长期借款": "LongTermDebtNoncurrent",
    "应付债券": "BondsPayableNoncurrent",                # 全口径有息负债的一部分（如可转债）
    "应收账款": "AccountsReceivableNetCurrent",          # 盈利质量取证：应收 vs 营收剪刀差
    "存货": "InventoryNet",                              # 盈利质量取证：存货 vs 营收剪刀差
}

# 利润表（同花顺 stock_financial_benefit_ths 的精确列名 → 英文 concept）
# ⚠ 注意：同花顺列名带"一、/二、/三、/其中：/加：/减："等前缀，必须用完整列名匹配，
#    否则匹配不上（历史 bug：曾写成 "营业利润"，真实列名是 "三、营业利润"，导致从未落库）。
INCOME_MAP = {
    "一、营业总收入": "Revenues",                         # 与 abstract 的"营业总收入"一致（互为兜底）
    "其中：营业成本": "CostOfRevenue",                     # 与 abstract 的"营业成本"一致
    "营业税金及附加": "TaxesAndSurcharges",
    "销售费用": "SellingExpense",
    "管理费用": "GeneralAndAdministrativeExpense",
    "研发费用": "ResearchAndDevelopmentExpense",
    "财务费用": "FinanceExpense",                          # 可为负（净利息收入）
    "资产减值损失": "AssetImpairmentLoss",
    "信用减值损失": "CreditImpairmentLoss",
    "加：公允价值变动收益": "FairValueChangeIncome",
    "投资收益": "InvestmentIncome",
    "资产处置收益": "AssetDisposalIncome",
    "其他收益": "OtherOperatingIncome",
    "三、营业利润": "OperatingIncomeLoss",
    "四、利润总额": "IncomeLossBeforeIncomeTaxes",
    "减：所得税费用": "IncomeTaxExpenseBenefit",
    "五、净利润": "NetIncomeLossTotal",
    "归属于母公司所有者的净利润": "NetIncomeLoss",
    "少数股东损益": "MinorityInterestIncome",
}

# 现金流量表
CASH_MAP = {
    "购建固定资产、无形资产和其他长期资产支付的现金": "PaymentsToAcquirePropertyPlantAndEquipment",
}


# ============================================================
# 交易所识别
# ============================================================

def detect_exchange(code):
    """根据 6 位代码推断交易所。"""
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        return None, None, None
    if code.startswith("6"):
        return "SH", "上海", "sh" + code
    if code.startswith(("0", "3")):
        return "SZ", "深圳", "sz" + code
    if code.startswith(("4", "8")):
        return "BJ", "北京", "bj" + code
    return None, None, None


# ============================================================
# 公司基本信息
# ============================================================

def get_company_info(code, exchange):
    """获取公司名 + 上市日期 + 简介。"""
    import akshare as ak
    info = {"code": code, "exchange": exchange}

    # 优先：交易所代码对照表（最准）
    try:
        if exchange == "SH":
            for board in ("主板", "科创板"):
                try:
                    df = ak.stock_info_sh_name_code(symbol=board)
                    row = df[df["证券代码"] == code]
                    if not row.empty:
                        info["name"] = row.iloc[0]["证券简称"]
                        info["full_name"] = row.iloc[0]["公司全称"]
                        info["listed_date"] = str(row.iloc[0]["上市日期"])
                        info["board"] = board
                        break
                except Exception:
                    pass
        elif exchange == "SZ":
            for board in ("A股列表", "创业板"):
                try:
                    df = ak.stock_info_sz_name_code(symbol=board)
                    code_col = "A股代码" if "A股代码" in df.columns else "证券代码"
                    name_col = "A股简称" if "A股简称" in df.columns else "证券简称"
                    row = df[df[code_col] == code]
                    if not row.empty:
                        info["name"] = row.iloc[0][name_col]
                        info["board"] = board
                        if "公司全称" in df.columns:
                            info["full_name"] = row.iloc[0]["公司全称"]
                        break
                except Exception:
                    pass
    except Exception as e:
        print(f"  ⚠ 交易所对照表查询失败: {e}", file=sys.stderr)

    # 兜底：全 A 股代码名称表
    if "name" not in info:
        try:
            all_codes = ak.stock_info_a_code_name()
            row = all_codes[all_codes["code"] == code]
            if not row.empty:
                info["name"] = row.iloc[0]["name"]
        except Exception:
            pass

    return info


# ============================================================
# 财务数据（拼接 abstract + balance + cash flow + income statement）
# ============================================================

def fetch_financials_rows(code, exchange):
    """返回 [(concept, fy, period_end, value, unit), ...] —— 兼容 fetch_filings 的格式。"""
    import akshare as ak
    rows = []

    # 1. 财务摘要（一行一指标，列是各报告期）
    try:
        abs_df = ak.stock_financial_abstract(symbol=code)
        # 列名形如 "20251231" 这种 8 位数字串
        period_cols = [c for c in abs_df.columns if str(c).isdigit() and len(str(c)) == 8 and str(c).endswith("1231")]
        for _, row in abs_df.iterrows():
            indicator = row["指标"]
            if indicator not in ABSTRACT_MAP:
                continue
            concept = ABSTRACT_MAP[indicator]
            for col in period_cols:
                val = row[col]
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    continue
                if val == 0 and indicator in ("营业总收入",):
                    # 保留 0 营收的记录（说明业务停了——ALBT 教训）
                    pass
                fy = int(col[:4])
                rows.append((concept, fy, col[:4] + "-12-31", val, "CNY"))
    except Exception as e:
        print(f"  ⚠ stock_financial_abstract 失败: {e}", file=sys.stderr)

    # 2. 资产负债表（同花顺，按年度）
    try:
        df = ak.stock_financial_debt_ths(symbol=code, indicator="按年度")
        # 报告期列是 "报告期" 或 "年度"
        period_col = "报告期" if "报告期" in df.columns else "年度"
        for _, row in df.iterrows():
            period = str(row[period_col])
            m = re.match(r"(\d{4})", period)
            if not m:
                continue
            fy = int(m.group(1))
            for cn, en in BALANCE_MAP.items():
                if cn not in row.index:
                    continue
                val = parse_cn_number(row[cn])
                if val is None:
                    continue
                rows.append((en, fy, f"{fy}-12-31", val, "CNY"))
    except Exception as e:
        print(f"  ⚠ stock_financial_debt_ths 失败: {e}", file=sys.stderr)

    # 3. 利润表
    try:
        df = ak.stock_financial_benefit_ths(symbol=code, indicator="按年度")
        period_col = "报告期" if "报告期" in df.columns else "年度"
        for _, row in df.iterrows():
            period = str(row[period_col])
            m = re.match(r"(\d{4})", period)
            if not m:
                continue
            fy = int(m.group(1))
            for cn, en in INCOME_MAP.items():
                if cn not in row.index:
                    continue
                val = parse_cn_number(row[cn])
                if val is None:
                    continue
                rows.append((en, fy, f"{fy}-12-31", val, "CNY"))
    except Exception as e:
        print(f"  ⚠ stock_financial_benefit_ths 失败: {e}", file=sys.stderr)

    # 4. 现金流量表
    try:
        df = ak.stock_financial_cash_ths(symbol=code, indicator="按年度")
        period_col = "报告期" if "报告期" in df.columns else "年度"
        for _, row in df.iterrows():
            period = str(row[period_col])
            m = re.match(r"(\d{4})", period)
            if not m:
                continue
            fy = int(m.group(1))
            for cn, en in CASH_MAP.items():
                if cn not in row.index:
                    continue
                val = parse_cn_number(row[cn])
                if val is None:
                    continue
                rows.append((en, fy, f"{fy}-12-31", val, "CNY"))
    except Exception as e:
        print(f"  ⚠ stock_financial_cash_ths 失败: {e}", file=sys.stderr)

    return rows


def parse_cn_number(v):
    """把中文带单位的数字字符串（如 "1.21亿"）转成 float（元）。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and (v != v)) else float(v)  # NaN check
    s = str(v).strip().replace(",", "")
    if not s or s in ("--", "—", "False", "nan", "NaN"):
        return None
    # 处理 "1.23亿" / "5678万" 等
    m = re.match(r"(-?[\d.]+)\s*([万亿千百])?$", s)
    if m:
        num = float(m.group(1))
        unit = m.group(2)
        scale = {"亿": 1e8, "万": 1e4, "千": 1e3, "百": 1e2}.get(unit, 1)
        return num * scale
    try:
        return float(s)
    except ValueError:
        return None


# ============================================================
# 年报 PDF 下载 + 文本提取
# ============================================================

def fetch_annual_reports(code, years, out_dir):
    """从巨潮资讯网拿年报 PDF + 提取文本。返回已下载的年份列表。"""
    import akshare as ak
    saved = []

    try:
        from datetime import datetime
        end_year = datetime.now().year
        start_year = end_year - years - 1  # 多算一年以防披露延迟
        reports = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code, market="沪深京", category="年报",
            start_date=f"{start_year}0101", end_date=f"{end_year + 1}1231",
        )
    except Exception as e:
        print(f"  ⚠ 拉年报列表失败: {e}", file=sys.stderr)
        return saved

    if reports is None or reports.empty:
        print("  无年报披露记录")
        return saved

    # 过滤"摘要"，只要正文
    full_reports = reports[~reports["公告标题"].str.contains("摘要", na=False)]
    full_reports = full_reports.sort_values("公告时间", ascending=False).head(years)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; ms-stock-tool/0.1)"}
    for _, row in full_reports.iterrows():
        url = row["公告链接"]
        # cninfo HTML 详情页 → 推导 PDF URL
        # URL 形如：...?stockCode=XXX&announcementId=YYY&announcementTime=YYYY-MM-DD
        q = parse_qs(urlparse(url).query)
        ann_id = (q.get("announcementId") or [""])[0]
        ann_time = ((q.get("announcementTime") or [""])[0] or "").strip()[:10]  # 截成纯日期
        if not ann_id or not ann_time:
            continue
        pdf_url = f"http://static.cninfo.com.cn/finalpage/{ann_time}/{ann_id}.PDF"

        # 报告年份从标题提取（如"...2024年年度报告"）
        m = re.search(r"(\d{4})年年度报告", row["公告标题"])
        report_year = m.group(1) if m else ann_time[:4]
        pdf_fname = f"年报_{report_year}.pdf"
        txt_fname = f"年报_{report_year}.txt"
        pdf_path = out_dir / pdf_fname
        txt_path = out_dir / txt_fname

        if pdf_path.exists() and txt_path.exists():
            print(f"  跳过已存在 {pdf_fname}")
            saved.append(report_year)
            continue

        print(f"  正在下载 {pdf_fname} ...", end=" ", flush=True)
        try:
            r = requests.get(pdf_url, headers=headers, timeout=60)
            r.raise_for_status()
            pdf_path.write_bytes(r.content)
            print(f"{len(r.content) // 1024} KB", end=" ")
        except Exception as e:
            print(f"失败: {e}")
            continue

        # 文本提取
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            text_pages = []
            for i, page in enumerate(reader.pages):
                try:
                    text_pages.append(page.extract_text() or "")
                except Exception:
                    text_pages.append("")
            text = "\n\n".join(text_pages)
            txt_path.write_text(text, encoding="utf-8")
            print(f"→ {pdf_fname.replace('.pdf', '.txt')} ({len(text) // 1000}K 字符)")
        except Exception as e:
            print(f"PDF→文本提取失败: {e}")

        saved.append(report_year)
        time.sleep(0.3)

    return saved


# ============================================================
# 写出 financials.csv
# ============================================================

def write_financials_csv(rows, fin_dir):
    fin_dir.mkdir(parents=True, exist_ok=True)
    csv_path = fin_dir / "financials.csv"
    # 去重：同一 (concept, fy) 只保留最后一条
    dedup = {}
    for r in rows:
        dedup[(r[0], r[1])] = r
    final = sorted(dedup.values(), key=lambda r: (r[0], r[1]))
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concept", "fiscal_year", "period_end", "value", "unit"])
        for r in final:
            w.writerow(r)
    return len(final), csv_path


# ============================================================
# 主营构成（业务板块拆分）—— 供桑基图左半边使用
# ============================================================

def fetch_segments(code, exchange):
    """从东方财富拉"主营构成"：按产品/行业/地区拆分的收入、成本、毛利。

    返回 {"by_product": {period: [seg...]}, "by_industry": {...}, "by_region": {...}}，
    每个 seg = {name, revenue, cost, gross_profit, margin}（金额单位=元，与 financials 一致）。
    """
    import akshare as ak
    sym = f"{exchange}{code}"  # 东财符号：如 SZ300017 / SH600519
    try:
        df = ak.stock_zygc_em(symbol=sym)
    except Exception as e:
        print(f"  ⚠ 主营构成获取失败: {e}", file=sys.stderr)
        return {}
    if df is None or df.empty:
        return {}

    type_key = {"按产品分类": "by_product", "按行业分类": "by_industry", "按地区分类": "by_region"}
    out = {"by_product": {}, "by_industry": {}, "by_region": {}}

    def num(v):
        try:
            f = float(v)
            return None if f != f else f  # NaN → None
        except (ValueError, TypeError):
            return None

    for _, row in df.iterrows():
        cat = type_key.get(str(row.get("分类类型")))
        if not cat:
            continue
        period = str(row.get("报告日期"))[:10]
        out[cat].setdefault(period, []).append({
            "name": str(row.get("主营构成")),
            "revenue": num(row.get("主营收入")),
            "cost": num(row.get("主营成本")),
            "gross_profit": num(row.get("主营利润")),
            "margin": num(row.get("毛利率")),
        })
    return out


# ============================================================
# 全量公告 + 高信号公告全文（问询函/控制权/重组/减持等）—— "真故事"常在这里
# ============================================================

# 高信号关键词分两级：TIER1（监管/控制权/重组）必下，TIER2（其余）有余量再下
DISCLOSURE_TIER1 = ["问询函", "关注函", "监管函", "警示函", "立案", "处罚", "整改",
                    "控制权", "控股股东", "实际控制人", "实控人", "表决权", "股权转让",
                    "权益变动", "要约", "易主", "筹划重大事项", "停牌", "复牌",
                    "重大资产重组", "资产重组"]
DISCLOSURE_TIER2 = ["减持", "增持", "回购", "募集资金", "募投", "超募",
                    "收购", "出售", "剥离", "业绩预告", "业绩快报", "商誉", "减值", "计提",
                    "诉讼", "仲裁", "关联交易", "担保", "向特定对象发行", "可转债", "解禁"]


def _cninfo_pdf_text(url, pdf_path, txt_path, headers):
    """从巨潮 HTML 详情页链接推导 PDF、下载、用 pypdf 提取文本。成功返回 True。"""
    q = parse_qs(urlparse(url).query)
    ann_id = (q.get("announcementId") or [""])[0]
    ann_time = ((q.get("announcementTime") or [""])[0] or "").strip()[:10]  # 截成纯日期（有的带 " 00:00:00"）
    if not ann_id or not ann_time:
        return False
    pdf_url = f"http://static.cninfo.com.cn/finalpage/{ann_time}/{ann_id}.PDF"
    try:
        r = requests.get(pdf_url, headers=headers, timeout=60)
        r.raise_for_status()
        pdf_path.write_bytes(r.content)
    except Exception:
        return False
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        txt_path.write_text(text, encoding="utf-8")
    except Exception:
        return False
    return True


def fetch_disclosures(code, years, filings_dir, max_downloads=40):
    """巨潮全量公告：存索引 announcements_index.json + 下载高信号公告全文到 filings/公告/。"""
    import akshare as ak
    from datetime import datetime
    end_year = datetime.now().year
    start_date = f"{end_year - years}0101"
    end_date = f"{end_year + 1}1231"
    df = None
    try:
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code, market="沪深京", category="",
            start_date=start_date, end_date=end_date,
        )
    except Exception as e:
        print(f"  ⚠ 公告列表实时获取失败: {e}", file=sys.stderr)

    idx_path = filings_dir / "announcements_index.json"
    if df is not None and not df.empty:
        index = []
        for _, r in df.iterrows():
            title = str(r.get("公告标题", "")).replace("<em>", "").replace("</em>", "")
            index.append({
                "date": str(r.get("公告时间", ""))[:10],
                "title": title,
                "url": str(r.get("公告链接", "")),
            })
        index.sort(key=lambda x: x["date"], reverse=True)
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    elif idx_path.exists():
        # 回退：实时列表拉不到，就用上次存好的索引
        try:
            index = json.loads(idx_path.read_text(encoding="utf-8"))
            print(f"  （列表实时获取失败，改用已有索引：{len(index)} 条）")
        except Exception:
            print("  无公告记录")
            return
    else:
        print("  无公告记录")
        return

    pat1 = re.compile("|".join(DISCLOSURE_TIER1))
    pat2 = re.compile("|".join(DISCLOSURE_TIER2))
    tier1 = [a for a in index if pat1.search(a["title"]) and "摘要" not in a["title"]]
    tier2 = [a for a in index if (not pat1.search(a["title"])) and pat2.search(a["title"]) and "摘要" not in a["title"]]
    to_get = tier1[:max_downloads]                       # TIER1 优先、最近的先要
    if len(to_get) < max_downloads:
        to_get += tier2[: max_downloads - len(to_get)]

    ann_dir = filings_dir / "公告"
    ann_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ms-stock-tool/0.1)"}
    saved = 0
    for a in to_get:
        safe = re.sub(r'[\\/:*?"<>|\s]', "", a["title"])[:40]
        base = f"{a['date']}_{safe}"
        pdf_path = ann_dir / (base + ".pdf")
        txt_path = ann_dir / (base + ".txt")
        if txt_path.exists():
            saved += 1
            continue
        if _cninfo_pdf_text(a["url"], pdf_path, txt_path, headers):
            saved += 1
            time.sleep(0.25)
    print(f"  公告索引 {len(index)} 条 → announcements_index.json；"
          f"高信号公告（监管{len(tier1)}+其他）下载 {saved} 份 → filings/公告/")


# ============================================================
# 招股说明书（IPO prospectus）—— 给"起源/底色/历史/原始竞争分析"打底
# 规矩（用户 2026-05-31）：上市 ≤5 年 → 招股书 + 全部年报+披露；
#                        上市 >5 年 → 招股书 + 近 5 年年报+披露（不读 20 年防溢出）。
#   年报/披露的 5 年窗口由 --years 控制；招股书无论上市多久都抓（IPO 文件最深、最完整地讲了原始生意/历史/竞争/风险）。
# ============================================================

def fetch_prospectus(code, filings_dir):
    """从巨潮抓招股说明书全文（落到 filings/招股说明书.txt）。"""
    import akshare as ak
    from datetime import datetime
    end_year = datetime.now().year
    try:
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code, market="沪深京", category="首发",
            start_date="19990101", end_date=f"{end_year}1231",
        )
    except Exception as e:
        print(f"  ⚠ 招股书列表获取失败: {e}", file=sys.stderr)
        return
    if df is None or df.empty:
        print("  （未找到招股类文件——可能接口无早期记录）")
        return

    tcol = "公告标题" if "公告标题" in df.columns else df.columns[0]
    rows = []
    for _, r in df.iterrows():
        title = str(r.get(tcol, "")).replace("<em>", "").replace("</em>", "")
        rows.append((str(r.get("公告时间", ""))[:10], title, str(r.get("公告链接", ""))))

    def rank(t):  # 招股说明书(非摘要) > 招股意向书(非摘要) > 上市公告书 > 其他招股类
        if "招股说明书" in t and "摘要" not in t: return 0
        if "招股意向书" in t and "摘要" not in t: return 1
        if "上市公告书" in t: return 2
        if "招股" in t: return 3
        return 9
    cands = sorted([x for x in rows if rank(x[1]) < 9], key=lambda x: (rank(x[1]), x[0]))
    if not cands:
        print("  （列表里没有招股类文件）")
        return

    txt_path = filings_dir / "招股说明书.txt"
    pdf_path = filings_dir / "招股说明书.pdf"
    if txt_path.exists():
        print("  招股书已存在，跳过")
        return
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ms-stock-tool/0.1)"}
    date, title, url = cands[0]
    if _cninfo_pdf_text(url, pdf_path, txt_path, headers):
        n = len(txt_path.read_text(encoding="utf-8"))
        warn = "（注意：抽出文本很少，可能是扫描版 PDF）" if n < 5000 else ""
        print(f"  已保存 招股说明书.txt（{date}《{title}》，{n // 1000}K 字符）{warn}")
    else:
        print(f"  ⚠ 招股书下载失败：{title}")


# ============================================================
# 季度财务（最近 N 季关键指标）—— 看最新动向，不止年报
# ============================================================

def _q_concept(indicator):
    s = str(indicator).strip()
    if s == "营业总收入":
        return "Revenues"
    if s == "归母净利润":
        return "NetIncomeLoss"
    if "扣非" in s and "净利" in s:        # 排除"每股扣非""扣非ROE"等比率指标
        return "NetIncomeLossExclNonRecurring"
    if s == "经营现金流量净额":             # 精确匹配，排除"每股经营现金流"等
        return "NetCashProvidedByUsedInOperatingActivities"
    return None


def fetch_quarterly(code, fin_dir, n_quarters=8):
    """从 stock_financial_abstract 抽取最近若干季度关键指标 → quarterly.csv。"""
    import akshare as ak
    try:
        a = ak.stock_financial_abstract(symbol=code)
    except Exception as e:
        print(f"  ⚠ 季度数据获取失败: {e}", file=sys.stderr)
        return
    period_cols = sorted(
        [c for c in a.columns if str(c).isdigit() and len(str(c)) == 8],
        reverse=True,
    )[:n_quarters]
    if not period_cols:
        return
    rows = []
    for _, row in a.iterrows():
        concept = _q_concept(row.get("指标"))
        if not concept:
            continue
        for col in period_cols:
            try:
                val = float(row[col])
            except (ValueError, TypeError):
                continue
            if val != val:  # NaN
                continue
            pe = f"{col[:4]}-{col[4:6]}-{col[6:8]}"
            rows.append((concept, pe, val, "CNY"))
    if not rows:
        return
    # 去重：同一 (concept, period) 只留一条（abstract 不同"选项"会重复列同一指标）
    dedup = {(c, pe): (c, pe, v, u) for c, pe, v, u in rows}
    rows = sorted(dedup.values(), key=lambda r: (r[0], r[1]))
    path = fin_dir / "quarterly.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concept", "period_end", "value", "unit"])
        w.writerows(rows)
    print(f"  季度数据 → quarterly.csv（最近 {len(period_cols)} 期）")


# ============================================================
# 主流程
# ============================================================

def main():
    ap = argparse.ArgumentParser(
        description="A 股取数：财务数据 + 年报 PDF。与 fetch_filings.py 输出格式对齐。"
    )
    ap.add_argument("code", help="6 位股票代码，如 688237（科创板）/ 600519（沪主板）/ 000333（深主板）")
    ap.add_argument("--years", type=int, default=5, help="年报最近几年（默认 5）")
    args = ap.parse_args()

    code = args.code.strip()
    exchange, ex_cn, ak_symbol = detect_exchange(code)
    if not exchange:
        sys.exit(f"错误：{code} 不是有效的 6 位 A 股代码")

    print(f"代码 {code} → {ex_cn}交易所")

    info = get_company_info(code, exchange)
    name = info.get("name", "?")
    full = info.get("full_name", name)
    listed = info.get("listed_date", "?")
    board = info.get("board", "?")
    print(f"  公司: {name}（{full}）")
    print(f"  上市: {listed}  板块: {board}")

    base = Path("analyses") / code
    filings_dir = base / "filings"
    fin_dir = base / "financials"
    filings_dir.mkdir(parents=True, exist_ok=True)
    fin_dir.mkdir(parents=True, exist_ok=True)

    # 写公司信息
    (base / "company_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 财务数据
    print("\n正在拉取财务数据（AKShare）...")
    rows = fetch_financials_rows(code, exchange)
    if rows:
        n, csv_path = write_financials_csv(rows, fin_dir)
        years_set = sorted({r[1] for r in rows})
        print(f"  已保存 financials.csv（{n} 个数据点，覆盖年份 {years_set}）")
    else:
        print("  ⚠ 没拉到任何财务数据——可能 AKShare 接口暂时不可用")

    # 主营构成（业务板块拆分）—— 桑基图用
    segments = fetch_segments(code, exchange)
    if segments and any(segments.values()):
        (fin_dir / "segments.json").write_text(
            json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        n_prod = len(segments.get("by_product", {}))
        n_ind = len(segments.get("by_industry", {}))
        print(f"  已保存 segments.json（主营构成：按产品 {n_prod} 期 / 按行业 {n_ind} 期）")
    else:
        print("  ⚠ 没拿到主营构成（桑基图将退化为不带板块拆分的版本）")

    # 季度财务（最近 8 季）
    fetch_quarterly(code, fin_dir)

    # 年报
    print(f"\n正在下载近 {args.years} 年年报（巨潮资讯网）...")
    saved_years = fetch_annual_reports(code, args.years, filings_dir)
    if saved_years:
        print(f"  已保存 {len(saved_years)} 份年报：{sorted(saved_years, reverse=True)}")
    else:
        print("  ⚠ 没下载到任何年报——可能此公司还没披露年报或链接结构变更")

    # 全量公告索引 + 高信号公告全文（问询函/控制权/重组/减持等）
    print(f"\n正在抓取公告（巨潮资讯网，近 {args.years} 年）...")
    fetch_disclosures(code, args.years, filings_dir)

    # 招股说明书（无论上市多久都抓——给起源/历史/原始竞争分析打底）
    print("\n正在抓取招股说明书...")
    fetch_prospectus(code, filings_dir)

    print(f"\n完成。全部内容已保存在 {base}/")


if __name__ == "__main__":
    main()
