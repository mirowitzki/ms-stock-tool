#!/usr/bin/env python3
# 花名：克洛泽 —— 团队花名册见 CLAUDE.md「团队花名册」节（门前捡漏之王，专找没人要的便宜货）
"""
screen_deep_value.py —— 深价值粗筛器（O17，2026-07-05）：给"破净+好资产+治理催化"
这个已被验证的口袋（000009/600327/000925/300085 模式）装一根进料管道。

两段式（都是免费源、纯代码）：
  第一段 全A快照粗筛（新浪 Market_Center 行情接口，当日缓存）：
    破净（0<市净率<1）× 市值 20-300 亿 × 非ST非退市 × 非金融（银行/保险/证券的净资产是
    估计值、不能套资产折价拆法——BASE_RATES 失败模式库第七节）× 沪深主板/创业板/科创板。
  第二段 现金流验证（新浪年度现金流量表，逐家、带缓存）：
    近三个完整财年经营现金流净额为正的年数——3/3 进主榜、2/3 进备查。
    破净但经营连年失血的，多半是真便宜不了的冰块。

产出：analyses/_screen_results.md（主榜+备查，按市净率升序）+ _screen_results.json。
第三段（治理催化信号：控制权变更/无实控人/增持回购/分拆）不在本脚本——那是判断密集的
联网核查，由主 Claude 派 agent 对主榜逐个扫、给每家一句话理由，用户点头才进分析队列。

用法：python3 scripts/screen_deep_value.py            # 全流程（第二段较慢、约2-5分钟）
      python3 scripts/screen_deep_value.py --stage1   # 只跑粗筛看幸存者
注意：粗筛是漏斗不是结论——榜上公司未经任何分析，禁止直接当买入候选展示给用户 UI。
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

SNAP_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
HEADERS = {"Referer": "https://finance.sina.com.cn",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SNAP_CACHE = Path("analyses/_screen_snapshot.json")
CFO_CACHE = Path("analyses/_screen_cfo_cache.json")
OUT_MD = Path("analyses/_screen_results.md")
OUT_JSON = Path("analyses/_screen_results.json")

# 参数（要改就改这里）
PB_MAX = 1.0
MKTCAP_MIN_WAN = 20 * 10000      # 20 亿（接口单位：万元）
MKTCAP_MAX_WAN = 300 * 10000     # 300 亿
CODE_PREFIX = ("60", "00", "30", "68")   # 沪主板/深主板/创业板/科创板，排北交所
FIN_WORDS = ("银行", "证券", "保险", "人寿", "财险", "信托", "租赁", "期货", "金控", "商行", "农商")
BAD_WORDS = ("ST", "退")


def fetch_snapshot():
    """全A快照（当日缓存）。返回 list[dict]，字段含 code/name/trade/per/pb/mktcap。"""
    today = date.today().isoformat()
    if SNAP_CACHE.exists():
        try:
            c = json.loads(SNAP_CACHE.read_text(encoding="utf-8"))
            if c.get("date") == today and c.get("rows"):
                print(f"用当日缓存快照（{len(c['rows'])} 条，{today}）")
                return c["rows"]
        except Exception:
            pass
    rows, page = [], 1
    while True:
        r = requests.get(SNAP_URL, params={"page": page, "num": 100, "sort": "symbol",
                                           "asc": 1, "node": "hs_a", "symbol": "", "_s_r_a": "page"},
                         headers=HEADERS, timeout=25)
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        page += 1
        time.sleep(0.15)
        if page > 120:   # 安全阀
            break
    SNAP_CACHE.write_text(json.dumps({"date": today, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    print(f"快照抓取完成：{len(rows)} 条（已缓存）")
    return rows


def stage1(rows):
    """粗筛：破净×市值带×非ST非金融×板块。返回按 PB 升序的幸存者。"""
    out = []
    for d in rows:
        code, name = str(d.get("code", "")), d.get("name", "")
        try:
            pb, cap = float(d.get("pb") or 0), float(d.get("mktcap") or 0)
            per = float(d.get("per") or 0)
            price = float(d.get("trade") or 0)
        except (TypeError, ValueError):
            continue
        if not code.startswith(CODE_PREFIX):
            continue
        if any(w in name for w in BAD_WORDS):
            continue
        if any(w in name for w in FIN_WORDS):
            continue
        if not (0 < pb < PB_MAX):
            continue
        if not (MKTCAP_MIN_WAN <= cap <= MKTCAP_MAX_WAN):
            continue
        if price <= 0:
            continue
        out.append({"code": code, "name": name, "price": price, "pb": pb,
                    "pe": per, "mktcap_yi": round(cap / 10000, 1)})
    out.sort(key=lambda x: x["pb"])
    return out


def _sina_prefix(code):
    return ("sh" if code.startswith(("6",)) else "sz") + code


def cfo_positive_years(code, cache):
    """近三个完整财年经营现金流净额为正的年数（0-3）；数据拿不到返回 None。带缓存。"""
    key = code
    if key in cache:
        return cache[key]["pos_years"], cache[key].get("series")
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=_sina_prefix(code), symbol="现金流量表")
        col = next(c for c in df.columns if "经营" in c and "净额" in c)
        annual = df[df["报告日"].astype(str).str.endswith("1231")].head(3)
        vals = []
        for _, r in annual.iterrows():
            try:
                vals.append((str(r["报告日"])[:4], float(r[col])))
            except (TypeError, ValueError):
                pass
        pos = sum(1 for _, v in vals if v > 0)
        result = pos if len(vals) >= 3 else (pos if vals else None)
        cache[key] = {"pos_years": result, "series": [(y, round(v / 1e8, 2)) for y, v in vals]}
        return result, cache[key]["series"]
    except Exception:
        cache[key] = {"pos_years": None, "series": []}
        return None, []


def main():
    stage1_only = "--stage1" in sys.argv
    known = {p.name for p in Path("analyses").glob("*") if p.is_dir() and not p.name.startswith("_")}

    rows = fetch_snapshot()
    survivors = stage1(rows)
    print(f"第一段粗筛：{len(survivors)} 家（破净 × 市值20-300亿 × 非ST非金融）")
    if stage1_only:
        for s in survivors[:30]:
            print(f"  {s['code']} {s['name']:<8} PB={s['pb']:.2f} 市值{s['mktcap_yi']}亿")
        return

    cache = {}
    if CFO_CACHE.exists():
        try:
            cache = json.loads(CFO_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    print(f"第二段现金流验证：逐家拉近三年经营现金流（缓存命中 {sum(1 for s in survivors if s['code'] in cache)}/{len(survivors)}）…")
    for i, s in enumerate(survivors, 1):
        pos, series = cfo_positive_years(s["code"], cache)
        s["cfo_pos_years"], s["cfo_series"] = pos, series
        s["in_house"] = s["code"] in known
        if i % 25 == 0:
            print(f"  …{i}/{len(survivors)}")
            CFO_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if s["code"] not in cache or True:
            time.sleep(0.35)
    CFO_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    main_list = [s for s in survivors if s.get("cfo_pos_years") == 3]
    watch_list = [s for s in survivors if s.get("cfo_pos_years") == 2]
    failed = [s for s in survivors if s.get("cfo_pos_years") is None]

    today = date.today().isoformat()
    lines = [f"# 深价值粗筛结果 · {today}", "",
             f"参数：0<市净率<{PB_MAX} × 总市值 {MKTCAP_MIN_WAN//10000}-{MKTCAP_MAX_WAN//10000} 亿 × 非ST非退 × 非金融 × 沪深主板/创业板/科创板",
             f"第一段幸存 {len(survivors)} 家 → 近三个完整财年经营现金流全为正 {len(main_list)} 家（主榜）、两年为正 {len(watch_list)} 家（备查）、数据缺 {len(failed)} 家",
             "",
             "> 这是漏斗不是结论：榜上公司未经任何分析。下一步＝治理催化信号逐家扫（控制权变更/无实控人/增持回购/分拆/母公司质押），",
             "> 有催化线索的给一句话理由、用户点头才进分析队列。已在册的公司标了出来。",
             "",
             "## 主榜（近三年经营现金流全为正，按市净率升序）", "",
             "| 代码 | 名称 | 现价 | 市净率 | 市盈率TTM | 总市值(亿) | 近三年经营现金流(亿) | 备注 |",
             "|---|---|---|---|---|---|---|---|"]
    for s in main_list:
        cfo = "、".join(f"{y}:{v:+.1f}" for y, v in (s.get("cfo_series") or []))
        pe = f"{s['pe']:.1f}" if s.get("pe") and s["pe"] > 0 else "亏损"
        lines.append(f"| {s['code']} | {s['name']} | {s['price']:.2f} | {s['pb']:.2f} | {pe} | {s['mktcap_yi']} | {cfo} | {'已在册' if s['in_house'] else ''} |")
    lines += ["", "## 备查（三年里两年为正）", "",
              "| 代码 | 名称 | 现价 | 市净率 | 总市值(亿) | 近三年经营现金流(亿) |", "|---|---|---|---|---|---|"]
    for s in watch_list:
        cfo = "、".join(f"{y}:{v:+.1f}" for y, v in (s.get("cfo_series") or []))
        lines.append(f"| {s['code']} | {s['name']} | {s['price']:.2f} | {s['pb']:.2f} | {s['mktcap_yi']} | {cfo} |")
    if failed:
        lines += ["", f"数据缺（现金流拉取失败、重跑可补）：{'、'.join(s['code'] for s in failed)}"]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"date": today, "main": main_list, "watch": watch_list},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n主榜 {len(main_list)} 家、备查 {len(watch_list)} 家 → {OUT_MD}")
    for s in main_list[:20]:
        print(f"  {s['code']} {s['name']:<8} PB={s['pb']:.2f} 市值{s['mktcap_yi']}亿"
              + ("  [已在册]" if s['in_house'] else ""))


if __name__ == "__main__":
    main()
