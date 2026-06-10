#!/usr/bin/env python3
"""
refresh_dashboard.py —— 扫描 analyses/ 下所有公司，把清单注入 dashboard.html。

读取：
  - analyses/<TICKER>/ 下各种文件，判断哪一层完成了
  - analyses/<TICKER>/valuation_inputs.json（如有）→ 取公司名 + 基础事实
  - tools/dashboard.html                                通用模板

写入：
  - dashboard.html（项目根目录，方便双击打开）

用法：
  python scripts/refresh_dashboard.py

无参数。每次分析完一家公司或想刷新仪表盘时跑一次。
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path


def scan_company(ticker_dir):
    """扫描一家公司的文件夹，返回这家公司的清单条目。"""
    ticker = ticker_dir.name
    # 检测各文件存在性
    filings_dir = ticker_dir / "filings"
    fin_dir = ticker_dir / "financials"
    dossier_md = ticker_dir / "dossier.md"
    dossier_pdf = ticker_dir / "dossier.pdf"
    memo_md = ticker_dir / "memo.md"
    memo_pdf = ticker_dir / "memo.pdf"
    explorer_html = ticker_dir / "valuation_explorer.html"
    inputs_json = ticker_dir / "valuation_inputs.json"

    report_md_files = list(ticker_dir.glob("*完整报告.md"))
    report_pdf_files = list(ticker_dir.glob("*完整报告.pdf"))

    has_filings = filings_dir.exists() and any(filings_dir.iterdir())
    has_financials = fin_dir.exists() and (fin_dir / "financials.csv").exists()
    has_dossier = dossier_md.exists()
    has_dossier_pdf = dossier_pdf.exists()
    has_report_md = bool(report_md_files)
    has_report_pdf = bool(report_pdf_files)
    has_memo = memo_md.exists()
    has_memo_pdf = memo_pdf.exists()
    has_explorer = explorer_html.exists()

    # 公司名 + 基础事实从 valuation_inputs.json 提取（如果存在）
    company_name = ticker
    as_of = None
    stats = {}
    currency_code = None
    next_earnings = None
    if inputs_json.exists():
        try:
            with inputs_json.open(encoding="utf-8") as f:
                inputs = json.load(f)
            company_name = inputs.get("company_name", ticker)
            as_of = inputs.get("as_of")
            facts = inputs.get("facts", {})
            stats = {
                "revenue_today": facts.get("revenue_today"),
                "market_cap": facts.get("market_cap"),
            }
            currency_code = inputs.get("currency")
            ne = inputs.get("next_earnings") or {}
            if ne.get("date"):
                next_earnings = {"date": ne.get("date"), "period": ne.get("period"),
                                 "estimated": bool(ne.get("estimated"))}
        except Exception as e:
            print(f"⚠ {inputs_json} 解析失败：{e}")

    # 货币：显式 > 6 位代码默认 CNY > USD
    if not currency_code:
        currency_code = "CNY" if ticker.isdigit() and len(ticker) == 6 else "USD"
    CURRENCY_SYMBOLS = {"USD": "$", "CNY": "￥", "HKD": "HK$", "EUR": "€", "JPY": "¥", "GBP": "£"}
    currency = {"code": currency_code, "symbol": CURRENCY_SYMBOLS.get(currency_code, "$")}

    # 兜底：A 股 fetch_a_stocks 产出的 company_info.json
    company_info_json = ticker_dir / "company_info.json"
    if company_name == ticker and company_info_json.exists():
        try:
            with company_info_json.open(encoding="utf-8") as f:
                ci = json.load(f)
            # 优先简称，其次全称
            company_name = ci.get("name") or ci.get("full_name") or ticker
            if not as_of:
                as_of = ci.get("listed_date")
        except Exception:
            pass

    # 否则从 financials.csv 兜底取最新年份
    if not as_of and has_financials:
        try:
            import csv
            with (fin_dir / "financials.csv").open(encoding="utf-8") as f:
                years = set()
                for row in csv.DictReader(f):
                    try:
                        years.add(int(row["fiscal_year"]))
                    except (ValueError, TypeError):
                        pass
            if years:
                as_of = f"{max(years)}-12-31"
        except Exception:
            pass

    # 值班台数据（2026-06-10）：入场观察区距离 + 复盘到期 + 财报倒计时。
    # 日期相关的判断（到期/倒计时）放浏览器 JS 用当天日期算，这里只注入原始数据。
    watch = {}
    dec_path = ticker_dir / "decision.json"
    if dec_path.exists():
        try:
            dec = json.loads(dec_path.read_text(encoding="utf-8"))
            ew = dec.get("entry_watch") or {}
            watch["entry_low"] = ew.get("low")
            watch["entry_high"] = ew.get("high")
            watch["entry_note"] = (ew.get("note") or "")[:80]
            watch["review_by"] = dec.get("review_by")
            watch["pred_dates"] = sorted(p.get("check_by") for p in (dec.get("predictions") or [])
                                         if p.get("status", "open") == "open" and p.get("check_by"))
        except Exception as e:
            print(f"⚠ {dec_path} 解析失败（这家的值班台信息会缺失）：{e}")
    prices_path = fin_dir / "prices.json"
    if prices_path.exists():
        try:
            pj = json.loads(prices_path.read_text(encoding="utf-8"))
            pts = pj.get("prices") or []
            if pts:
                watch["last_close"] = pts[-1].get("c")
                watch["last_close_month"] = pts[-1].get("m")
        except Exception as e:
            print(f"⚠ {prices_path} 解析失败：{e}")
    if next_earnings:
        watch["next_earnings"] = next_earnings

    # 用相对路径（让浏览器 file:// 协议也能加载）
    def rel(p):
        return str(p.relative_to(ticker_dir.parent.parent)).replace("\\", "/")

    # 优先链接 PDF；不存在则 fallback 到 MD（避免老分析卡片打不开）
    files = {}
    if has_report_pdf: files["report_pdf"] = rel(report_pdf_files[0])
    elif has_report_md: files["report_pdf"] = rel(report_md_files[0])
    if has_explorer: files["explorer_html"] = rel(explorer_html)
    if inputs_json.exists(): files["inputs_json"] = rel(inputs_json)

    return {
        "ticker": ticker,
        "company_name": company_name,
        "as_of": as_of,
        "status": {
            "filings": has_filings,
            "financials": has_financials,
            "report_pdf": has_report_pdf or has_report_md,
            "explorer": has_explorer,
        },
        "files": files,
        "stats": stats,
        "currency": currency,
        "watch": watch,
    }


def scan_chains():
    """扫描 chains/ 下所有产业链研究，返回清单（第二阶段·产业链研究板块）。"""
    chains_dir = Path("chains")
    if not chains_dir.exists():
        return []
    out = []
    for d in sorted(c for c in chains_dir.iterdir() if c.is_dir() and not c.name.startswith((".", "_"))):
        meta = {}
        meta_path = d / "chain.json"
        if meta_path.exists():
            try:
                with meta_path.open(encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
        pages = []
        for p in meta.get("pages", []):
            fp = p.get("file")
            if fp and Path(fp).exists():
                pages.append({"title": p.get("title", ""), "icon": p.get("icon", "📄"), "file": fp})
        # 兜底：老字段 map_html / 目录里的 chain_map.html
        if not pages:
            mh = meta.get("map_html") or str(d / "chain_map.html").replace("\\", "/")
            if Path(mh).exists():
                pages.append({"title": "查看产业链图谱", "icon": "🗺️", "file": mh})
        out.append({
            "slug": meta.get("slug", d.name),
            "name": meta.get("name", d.name),
            "as_of": meta.get("as_of"),
            "tagline": meta.get("tagline", ""),
            "gates": meta.get("gates", []),
            "gates_done": meta.get("gates_done", 0),
            "selected": meta.get("selected"),
            "stats": {"subchains": meta.get("subchains")},
            "pages": pages,
        })
    return out


def main():
    analyses_dir = Path("analyses")
    if not analyses_dir.exists():
        print(f"警告：{analyses_dir} 不存在；仪表盘会是空的。")
        companies = []
    else:
        # 只扫描子目录（每个子目录是一家公司）
        company_dirs = sorted(d for d in analyses_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
        companies = [scan_company(d) for d in company_dirs]

    # 按"完成度"排序：所有层都完成的在前
    def completeness(c):
        s = c["status"]
        # 优先级：估值完成 > 报告完成 > 取数完成
        return -(int(s["explorer"]) * 8 + int(s["report_pdf"]) * 4 + int(s["filings"]))
    companies.sort(key=completeness)

    chains = scan_chains()

    payload = {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tool_version": "0.2",
        "companies": companies,
        "chains": chains,
    }

    template_path = Path("tools") / "dashboard.html"
    if not template_path.exists():
        sys.exit(f"错误：找不到 {template_path}")
    template = template_path.read_text(encoding="utf-8")

    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    new_block = (
        "<!-- DASHBOARD_DATA_START -->\n"
        '<script id="dashboard-data" type="application/json">\n'
        + payload_json
        + "\n</script>\n"
        "<!-- DASHBOARD_DATA_END -->"
    )
    output, n = re.subn(
        r"<!-- DASHBOARD_DATA_START -->.*?<!-- DASHBOARD_DATA_END -->",
        lambda m: new_block,
        template,
        count=1,
        flags=re.DOTALL,
    )
    if n == 0:
        sys.exit("错误：模板里找不到 <!-- DASHBOARD_DATA_START --> 标记")

    out_path = Path("dashboard.html")
    out_path.write_text(output, encoding="utf-8")

    print(f"已生成 {out_path.absolute()}")
    print(f"  扫描到 {len(companies)} 家公司")
    for c in companies:
        s = c["status"]
        flags = "".join([
            "F" if s["filings"] else ".",
            "P" if s["report_pdf"] else ".",
            "E" if s["explorer"] else ".",
        ])
        print(f"    [{flags}] {c['ticker']:<6} {c['company_name']}")
    if chains:
        print(f"  扫描到 {len(chains)} 条产业链研究")
        for ch in chains:
            print(f"    [{len(ch.get('pages', []))}页·{ch.get('gates_done', 0)}/{len(ch.get('gates', []))}关] {ch['slug']:<16} {ch['name']}")
    print()
    print("提示：双击项目根目录的 dashboard.html 即可在浏览器打开。")


if __name__ == "__main__":
    main()
