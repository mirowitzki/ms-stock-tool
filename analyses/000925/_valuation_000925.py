# -*- coding: utf-8 -*-
"""000925 众合科技 Track C 估值算账（资产地板 + 正常化分部加总 + 三情景）。
所有倍数/正常化盈利是判断输入（写在注释里），算术由本脚本完成。单位：亿元。"""

SHARES = 6.764          # 总股本约 6.764 亿股（注册资本 676,369,858）
PRICE = 7.81            # 2026-05 现价（元）
MCAP = round(SHARES * PRICE, 1)

# ---- 资产负债面（2025 年报，归母口径）----
book_equity = 32.65     # 归母净资产
net_debt = 11.28        # 有息负债27.75 − (货币15.13+理财1.34=16.47)
# 真实净现金 = -11.28（净负债）

# ---- 1) 资产地板（保守可回收口径，归母）----
# 从归母净资产 32.65 出发，做保守减值：
#  商誉 0.33→0（-0.33）；应收账款12.66+合同资产13.29≈26 的额外回收折让(约8%-12%) -2.1~-3.1；
#  长期股权投资9.45 含亏损参股，折让 -1.0~-1.8；存货3.31 小折让 -0.2~-0.4
floor_hair_low = 0.33 + 3.1 + 1.8 + 0.4     # 较狠
floor_hair_high = 0.33 + 2.1 + 1.0 + 0.2    # 较松
asset_floor_low = round(book_equity - floor_hair_low, 1)
asset_floor_high = round(book_equity - floor_hair_high, 1)

# ---- 2) 正常化分部加总 SOTP（归母，按中周期正常化、不锚低谷）----
# 各分部给“企业价值/股权价值”毛估区间（亿），最后统一减净负债。
# 轨交+AFC：正常化净利 1.6~2.0 亿（2025三家轨交子公司单体净利合计1.27亿、毛利受压的低谷年；
#   中周期+改造放量回升）。倍数：交控科技为科创板自主龙头、高估值；众合前三但份额小、深主板、
#   无主治理折价 → 给 12~20×（base 14~15×、bull 18~20×含改造周期与重估、bear 11~12×）。
# 海纳半导体（众合控约56%）：整体股权 PB 3~5 于净资产5.17 → 15~26 亿（国产替代+开化稳赚+新基地期权+潜在北交所分拆）；
#   bear 给开化盈利打底的保守值。新三板薄市值不作锚。
# 新业务期权（低空/低轨卫星/大健康/算力 参股孵化）：bear 0~2、base 3~6、bull 9~15。
# 其他参股/历史资产（碧橙待剥离等，净值约0）：0.5。
other = 0.5
haina_stake = 0.56

def sotp(rail_l, rail_h, hn_whole_l, hn_whole_h, opt_l, opt_h):
    lo = rail_l + round(hn_whole_l*haina_stake,1) + opt_l + other - net_debt
    hi = rail_h + round(hn_whole_h*haina_stake,1) + opt_h + other - net_debt
    return round(lo, 1), round(hi, 1)

# 三情景：轨交(亿) / 海纳整体(亿) / 新业务(亿)
bear_lo, bear_hi = sotp(18.0, 22.0,  10.0, 14.0,  0.0, 2.0)   # 题材退潮、结构不改善、向资产地板收敛
base_lo, base_hi = sotp(24.0, 30.0,  16.0, 22.0,  3.0, 6.0)   # 正常化+结构小修
bull_lo, bull_hi = sotp(32.0, 40.0,  24.0, 30.0,  9.0, 15.0)  # 分拆北交所高估值+轨交重估+题材兑现

def per_share(v):
    return round(v / SHARES, 2)

def updown(v):
    return round((v / MCAP - 1) * 100)

print(f"总股本 {SHARES} 亿股 | 现价 {PRICE} 元 | 市值 {MCAP} 亿 | 归母净资产 {book_equity} 亿 (PB {round(MCAP/book_equity,2)})")
print(f"真实净现金 = -{net_debt} 亿（净负债）")
print("-"*70)
print(f"资产地板(归母): {asset_floor_low}~{asset_floor_high} 亿 | 每股 {per_share(asset_floor_low)}~{per_share(asset_floor_high)} 元 | 对现价 {updown(asset_floor_low)}%~{updown(asset_floor_high)}%")
print("-"*70)
for name,(lo,hi) in [("Bear",(bear_lo,bear_hi)),("Base",(base_lo,base_hi)),("Bull",(bull_lo,bull_hi))]:
    print(f"{name:5s} SOTP(归母): {lo}~{hi} 亿 | 每股 {per_share(lo)}~{per_share(hi)} 元 | 对现价 {updown(lo)}%~{updown(hi)}%")
print("-"*70)
# 概率加权中枢（Bear 0.35 / Base 0.45 / Bull 0.20），取各情景中点
def mid(lo,hi): return (lo+hi)/2
wbear, wbase, wbull = 0.35, 0.45, 0.20
weighted = wbear*mid(bear_lo,bear_hi) + wbase*mid(base_lo,base_hi) + wbull*mid(bull_lo,bull_hi)
print(f"概率加权中枢(35/45/20): {round(weighted,1)} 亿 | 每股 {per_share(weighted)} 元 | 对现价 {updown(weighted)}%")
print(f"反向：现价 {MCAP} 亿 对应每股 {PRICE} 元，已高于 Bull 中点({per_share(mid(bull_lo,bull_hi))}元)?", PRICE > per_share(mid(bull_lo,bull_hi)))
