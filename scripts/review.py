#!/usr/bin/env python3
"""
review.py —— 后台复盘助手：扫描所有决策记录，找出"该复盘了"的公司。

三类触发（见 skills/postmortem.md 动作二）：
  1 新数据：decision.date 之后出现新季报（quarterly.csv）或新公告（announcements_index.json）
  2 到期：review_by 到期，或某条 prediction 的 check_by 到期（待打分）
  3 价格：最新月度收盘进入 entry_watch 观察区（机会复盘——价格到了，论点还成立吗）

也会列出"已分析但还没建决策记录"的公司，提醒补上。

用法：python scripts/review.py
"""

import csv
import json
from datetime import date
from pathlib import Path

TODAY = date.today().isoformat()


def newest_quarter(fin_dir):
    p = fin_dir / "quarterly.csv"
    if not p.exists():
        return None
    periods = set()
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pe = r.get("period_end", "")
            if pe:
                periods.add(pe)
    return max(periods) if periods else None


def anns_after(filings_dir, date):
    p = filings_dir / "announcements_index.json"
    if not p.exists() or not date:
        return []
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠ {p} 解析失败（已跳过，但请修复）：{e}")
        return []
    return [a for a in idx if a.get("date", "") > date]


def last_close(fin_dir):
    """最新月度收盘（来自 fetch_prices.py 的 prices.json）；没有就返回 (None, None)。"""
    p = fin_dir / "prices.json"
    if not p.exists():
        return None, None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        pts = rec.get("prices") or []
        if not pts:
            return None, None
        return pts[-1].get("c"), pts[-1].get("m")
    except Exception as e:
        print(f"⚠ {p} 解析失败（已跳过，但请修复）：{e}")
        return None, None


def chains_due():
    """扫 chains/<slug>/chain_decision.json，列出 review_by 到期、该回来核的链判断。"""
    base = Path("chains")
    if not base.exists():
        return []
    today = date.today().isoformat()
    out = []
    for d in sorted(base.glob("*")):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        dec = d / "chain_decision.json"
        if not dec.exists():
            continue
        try:
            rec = json.loads(dec.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠ {dec} 解析失败——这条链不会被提示复盘，请修复：{e}")
            continue
        due_js = [j for j in rec.get("key_judgments", []) if j.get("review_by") and j["review_by"] <= today]
        out.append((d.name, rec.get("name", d.name), rec.get("as_of", "?"), due_js))
    return out


def main():
    base = Path("analyses")
    if not base.exists():
        print("没有 analyses/ 目录")
        return
    due, no_journal = [], []
    for d in sorted(base.glob("*")):
        if not d.is_dir():
            continue
        code = d.name
        dec = d / "decision.json"
        if not dec.exists():
            has_report = (d / f"{code}_公司完整报告.md").exists() or (d / "memo.md").exists() or (d / "dossier.md").exists()
            if has_report:
                no_journal.append(code)
            continue
        try:
            rec = json.loads(dec.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠ {dec} 解析失败——这家公司不会被提示复盘，请修复：{e}")
            continue
        date = rec.get("date", "")
        today = TODAY
        reasons = []
        nq = newest_quarter(d / "financials")
        if nq and date and nq > date:
            reasons.append(f"新季报 {nq}")
        new_anns = anns_after(d / "filings", date)
        if new_anns:
            top = new_anns[0]
            reasons.append(f"{len(new_anns)} 条新公告（最新 {top.get('date')}：{top.get('title','')[:24]}）")
        rb = rec.get("review_by")
        if rb and rb <= today:
            reasons.append(f"复盘到期（review_by {rb}）")
        due_preds = [p for p in (rec.get("predictions") or [])
                     if p.get("status", "open") == "open" and p.get("check_by", "") and p["check_by"] <= today]
        if due_preds:
            reasons.append(f"{len(due_preds)} 条预测到期待打分（最早 {min(p['check_by'] for p in due_preds)}）")
        ew = rec.get("entry_watch") or {}
        close, month = last_close(d / "financials")
        if close is not None and ew.get("high") is not None and close <= ew["high"]:
            note = ew.get("note", "")
            reasons.append(f"价格进入入场观察区（{month} 收盘 {close} ≤ {ew['high']}）→ 机会复盘"
                           + (f"；注意：{note[:36]}" if note else ""))
        if reasons:
            due.append((code, rec.get("verdict", "?"), date, reasons, rec.get("drivers") or [], due_preds))

    print("=" * 56)
    print("【该复盘的公司】自上次分析后出现了新数据 / 新公告：")
    if not due:
        print("  （暂无——要么没新料，要么这些公司还没建决策记录）")
    for code, verdict, date, reasons, drivers, due_preds in due:
        print(f"  ● {code}  上次判断「{verdict[:60]}」({date})")
        for r in reasons:
            print(f"      → {r}")
        if due_preds:
            print("      到期待打分的预测（复盘时判 hit/miss/unresolved、登进 reviews/CALIBRATION.md）：")
            for p in due_preds:
                print(f"        · {p.get('id','?')} {p.get('claim','')[:30]} ｜阈值：{p.get('threshold','')[:44]}（{p.get('check_by')} 到期）")
        if drivers:
            print("      逐个对账核心 driver：")
            for dv in drivers:
                if isinstance(dv, dict):
                    name = dv.get("driver", "?")
                    watch = dv.get("验证动作", "") or dv.get("watch", "")
                    print(f"        · {name}" + (f" → 盯 {watch}" if watch else ""))
                else:
                    print(f"        · {dv}")
    if no_journal:
        print("\n【已分析但缺决策记录 decision.json】（建议补上，否则无法复盘）：")
        print("  " + ", ".join(no_journal))

    chs = chains_due()
    if chs:
        print("\n" + "=" * 56)
        print("【产业链 · 该复盘的判断】到期该回来核的链判断（chain_decision.json）：")
        for slug, name, asof, due_js in chs:
            head = f" — {len(due_js)} 条判断到期" if due_js else " — 暂无到期判断"
            print(f"  ● {name}（{slug}，分析于 {asof}）{head}")
            for j in due_js:
                print(f"      → {j.get('env', '?')}：当时判「{j.get('call', '')}」 · 盯 {j.get('watch', '')}（{j.get('review_by')} 到期）")

    print("\n下一步：单股复盘见 skills/postmortem.md（盲评先行→打分→误差归类）→ 打分登 reviews/CALIBRATION.md、教训进 reviews/LESSONS.md；")
    print("        产业链复盘见 skills/industry-chain.md『复盘』节 → reviews/CHAIN_LESSONS.md（到期派独立 review agent 对账）。")


if __name__ == "__main__":
    main()
