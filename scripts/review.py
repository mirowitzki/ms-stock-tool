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
import sys
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
        ckpt = rec.get("next_checkpoint")
        ckpt_due = bool(ckpt and ckpt <= today)
        due_preds = [p for p in (rec.get("predictions") or [])
                     if p.get("status", "open") == "open" and p.get("check_by", "") and p["check_by"] <= today]
        out.append((d.name, rec.get("name", d.name), rec.get("as_of", "?"), due_js, ckpt, ckpt_due, due_preds))
    return out


def cost_of_no_ledger(save=False):
    """错过账本（O12，2026-07-05）：全部已分析公司按判断时点价 vs 最新价对照，
    分「判偏低/观察」「判偏贵/说不」两栏——让"说不"也可证伪（说不的成本没人记账＝永远不可证伪）。
    这是校准工具、不是投资建议；股价短期是噪声，按季度看、攒够样本再下结论。"""
    base = Path("analyses")
    qp = base / "_quotes.json"
    quotes = {}
    if qp.exists():
        try:
            quotes = json.loads(qp.read_text(encoding="utf-8")).get("quotes") or {}
        except Exception as e:
            print(f"⚠ _quotes.json 解析失败：{e}")
    rows = []
    for d in sorted(base.glob("*")):
        dec = d / "decision.json"
        if not d.is_dir() or not dec.exists():
            continue
        try:
            rec = json.loads(dec.read_text(encoding="utf-8"))
        except Exception:
            continue
        p0 = rec.get("current_price")
        q = quotes.get(d.name) or {}
        p1 = q.get("price")
        chg = (p1 / p0 - 1) * 100 if (p0 and p1) else None
        oc = (rec.get("odds") or {}).get("to_center_pct")
        bullish = oc is not None and oc >= 0
        rows.append({"code": d.name, "date": rec.get("date", ""), "bullish": bullish,
                     "p0": p0, "p1": p1, "as_of": q.get("as_of", ""), "chg": chg, "oc": oc})
    lines = []
    lines.append("=" * 72)
    lines.append("【错过账本】判断时点价 vs 最新价——让「说不」也可证伪（校准用、非建议）")
    for title, flag in (("判偏低/进观察（抓住侧）", True), ("判偏贵/说不（放掉侧）", False)):
        grp = [r for r in rows if r["bullish"] == flag]
        lines.append(f"\n  ◆ {title}：{len(grp)} 家")
        for r in sorted(grp, key=lambda x: -(x["chg"] if x["chg"] is not None else -999)):
            chg_s = f"{r['chg']:+.0f}%" if r["chg"] is not None else "无最新价"
            lines.append(f"    {r['code']:<8} {r['date']}  {r['p0'] if r['p0'] is not None else '—':>9} → "
                         f"{r['p1'] if r['p1'] is not None else '—':>9}（{chg_s}）")
        chgs = [r["chg"] for r in grp if r["chg"] is not None]
        if chgs:
            lines.append(f"    组平均涨跌：{sum(chgs)/len(chgs):+.0f}%")
    lines.append("\n  读法：放掉侧大涨≠判断错（可能是题材泡沫更泡了），但连续两个季度放掉侧显著跑赢，")
    lines.append("  就要回答是纪律还是系统性偏空（postmortem 动作三横截面综合）。")
    out = "\n".join(lines)
    print(out)
    if save:
        cal = Path("reviews/CALIBRATION.md")
        stamp = f"\n\n## 错过账本快照 · {TODAY}\n\n```\n" + out + "\n```\n"
        cal.write_text((cal.read_text(encoding="utf-8") if cal.exists() else "") + stamp, encoding="utf-8")
        print(f"\n已存进 {cal}（季度一次即可）")


def main():
    base = Path("analyses")
    if not base.exists():
        print("没有 analyses/ 目录")
        return
    due, no_journal = [], []
    extras = {}  # code → {stage, paper_entry}（打印头行用）
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
            reasons.append(f"新季报 {nq} → 先跑论点保鲜巡检（skills/thesis-refresh.md：重跑 metrics、承重判断逐条标 站得住/动摇/翻了）")
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
        # 价格带作废条件（2026-07-04，摊平预承诺——Miller 2008/Ackman Valeant 教训）：
        # 任一条件触发＝带作废，价格再进带提示"这是刀不是折扣、须完整重分析"，不做机会复盘。
        inval = [iv for iv in (ew.get("invalidation") or []) if isinstance(iv, dict)]
        preds_by_id = {p.get("id"): p for p in (rec.get("predictions") or []) if isinstance(p, dict)}
        triggered = []
        for iv in inval:
            if iv.get("prediction_id"):
                p = preds_by_id.get(iv["prediction_id"])
                if p and p.get("status") == iv.get("triggers_when", "hit"):
                    triggered.append(iv.get("event") or f"预测 {iv['prediction_id']} 已{p.get('status')}")
            elif iv.get("status") == "triggered":
                triggered.append(iv.get("event", "作废事件"))
        close, month = last_close(d / "financials")
        if close is not None and ew.get("high") is not None and close <= ew["high"]:
            if triggered:
                reasons.append(f"价格进入观察区（{month} 收盘 {close} ≤ {ew['high']}）但价格带已作废："
                               f"{('；'.join(triggered))[:60]} → 这是刀不是折扣、须按今天事实完整重分析（不做机会复盘）")
            else:
                note = ew.get("note", "")
                reasons.append(f"价格进入入场观察区（{month} 收盘 {close} ≤ {ew['high']}）→ 机会复盘，"
                               f"复盘时必过红队关（skills/red-team.md 触发条件2）"
                               + (f"；注意：{note[:36]}" if note else ""))
                if inval:
                    evts = "；".join(iv.get("event", "")[:24] for iv in inval)
                    reasons.append(f"进带前先核作废条件（任一被公告级证据证实即带作废）：{evts[:90]}")
        elif triggered:
            reasons.append(f"入场观察带已作废（{('；'.join(triggered))[:50]}）——旧价格带失效、须完整重分析后重设")
        if reasons:
            extras[code] = {"stage": rec.get("stage", "观察"), "paper_entry": rec.get("paper_entry")}
            due.append((code, rec.get("verdict", "?"), date, reasons, rec.get("drivers") or [], due_preds,
                        d / "_thesis.md" if ((rb and rb <= today) or due_preds) else None))

    print("=" * 56)
    print("【该复盘的公司】自上次分析后出现了新数据 / 新公告：")
    if not due:
        print("  （暂无——要么没新料，要么这些公司还没建决策记录）")
    for code, verdict, date, reasons, drivers, due_preds, thesis_path in due:
        ex = extras.get(code) or {}
        print(f"  ● {code}  阶段「{ex.get('stage', '观察')}」 上次判断「{verdict[:60]}」({date})")
        pe = ex.get("paper_entry")
        if pe:
            print(f"      纸面入场（校准用非建议）：{pe.get('date','?')} @ {pe.get('price','?')}"
                  + (f" · {pe.get('note','')[:30]}" if pe.get('note') else ""))
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
        # 论点漂移对照底稿（2026-07-04）：复盘到期/预测到期时打印旧 _thesis.md，
        # 复盘按 postmortem 动作二把四步逐项判 存活/已死/被替换——理由换血而结论不变＝漂移、须完整重分析。
        if thesis_path is not None and thesis_path.exists():
            txt = thesis_path.read_text(encoding="utf-8").strip()
            print("      论点漂移对照底稿（旧 _thesis.md 四步，逐项判 存活/已死/被替换）：")
            for ln in txt.splitlines()[:14]:
                if ln.strip():
                    print(f"        ｜{ln.strip()[:64]}")
    if no_journal:
        print("\n【已分析但缺决策记录 decision.json】（建议补上，否则无法复盘）：")
        print("  " + ", ".join(no_journal))

    # 判例库查缺（2026-07-05）：结案归档是流水线固定一步——已交付的公司必须归进
    # reviews/ARCHETYPES.md 的某个原型，否则这个案子的经验没进机构记忆、下个同类案子用不上。
    arch_path = Path("reviews/ARCHETYPES.md")
    if arch_path.exists():
        arch_text = arch_path.read_text(encoding="utf-8")
        not_archived = []
        for d in sorted(base.glob("*")):
            if not d.is_dir():
                continue
            code = d.name
            delivered = (d / f"{code}_公司完整报告.md").exists() or (d / "valuation_explorer.html").exists()
            if delivered and code not in arch_text:
                not_archived.append(code)
        if not_archived:
            print("\n【已交付但判例未入库】（结案归档欠账——把案子的经验归进 reviews/ARCHETYPES.md 对应原型）：")
            print("  " + ", ".join(not_archived))

    chs = chains_due()
    if chs:
        print("\n" + "=" * 56)
        print("【产业链 · 该复盘/该检查的】（chain_decision.json）：")
        for slug, name, asof, due_js, ckpt, ckpt_due, due_preds in chs:
            bits = []
            if ckpt_due:
                bits.append(f"季度检查点到期（{ckpt}）→ 派 agent 拉 indicators.json 指标判读")
            elif ckpt:
                bits.append(f"下次检查点 {ckpt}")
            if due_js:
                bits.append(f"{len(due_js)} 条判断到期")
            if due_preds:
                bits.append(f"{len(due_preds)} 条预测到期待打分")
            print(f"  ● {name}（{slug}，分析于 {asof}） — " + ("；".join(bits) if bits else "暂无到期"))
            for j in due_js:
                print(f"      → {j.get('env', '?')}：当时判「{j.get('call', '')}」 · 盯 {j.get('watch', '')}（{j.get('review_by')} 到期）")
            for p in due_preds:
                print(f"      → 预测 {p.get('id','?')} {p.get('claim','')[:30]} ｜阈值：{p.get('threshold','')[:44]}（{p.get('check_by')} 到期）")

    print("\n下一步：单股复盘见 skills/postmortem.md（盲评先行→打分→误差归类）→ 打分登 reviews/CALIBRATION.md、教训进 reviews/LESSONS.md；")
    print("        产业链复盘见 skills/industry-chain.md『复盘』节 → reviews/CHAIN_LESSONS.md（到期派独立 review agent 对账）。")


if __name__ == "__main__":
    if "--ledger" in sys.argv:
        cost_of_no_ledger(save="--save" in sys.argv)
    else:
        main()
