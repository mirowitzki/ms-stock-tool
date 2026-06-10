# -*- coding: utf-8 -*-
# Fit explorer two-stage DCF so each scenario per-share ~ judgment midpoint (Track B, SITM).
# Replicates valuation_explorer.html scenarioForwardDCF. Combined (post-Renesas) pro-forma.
# Units: revenue/cash/debt = million USD, shares = million.
import json

# Post-deal pro-forma balance sheet:
CASH = 500.0    # ~808 pre-deal cash + 1200 convert - ~1500 Renesas cash ~ 500
DEBT = 1200.0   # $1.2B 0% convertible
PRICE = 710.20
PRO_FORMA_MCAP = 21700.0  # 30.5M shares x ~$711 (post-deal)

def dcf(revY1, revY10, mY1, mY10, disc, g, shares, n=10):
    d = disc / 100.0
    gg = g / 100.0
    a = mY1 / 100.0
    b = mY10 / 100.0
    cagr = (revY10 / revY1) ** (1.0 / (n - 1))
    rev = [revY1 * cagr ** t for t in range(n)]
    marg = [a + (b - a) * t / (n - 1) for t in range(n)]
    fcf = [rev[i] * marg[i] for i in range(n)]
    epv = sum(fcf[i] / (1 + d) ** (i + 1) for i in range(n))
    tfcf = rev[-1] * (1 + gg) * b
    tv = tfcf / (d - gg)
    tpv = tv / (1 + d) ** n
    eq = epv + tpv + CASH - DEBT
    return eq / shares, eq

def solve_mY10(target_ps, revY1, revY10, mY1, disc, g, shares):
    lo, hi = 0.0, 60.0
    for _ in range(100):
        mid = (lo + hi) / 2
        ps, _ = dcf(revY1, revY10, mY1, mid, disc, g, shares)
        if ps < target_ps:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)

# revenue_today combined pro-forma ~ $650M (2026-27 run-rate). revY1 = first full combined year.
# Scenarios: target per-share mid, revY1, revY10, mY1(start FCF%), discount, terminal g, future_shares
scen = {
    "bear": {"target": 230, "revY1": 750, "revY10": 1500, "mY1": 8, "disc": 12, "g": 3.0, "shares": 37},
    "base": {"target": 430, "revY1": 850, "revY10": 2600, "mY1": 10, "disc": 11, "g": 3.5, "shares": 35},
    "bull": {"target": 750, "revY1": 950, "revY10": 4300, "mY1": 12, "disc": 10, "g": 4.0, "shares": 34},
}
out = {}
ps_map = {}
for k, s in scen.items():
    mY10 = solve_mY10(s["target"], s["revY1"], s["revY10"], s["mY1"], s["disc"], s["g"], s["shares"])
    ps, eq = dcf(s["revY1"], s["revY10"], s["mY1"], mY10, s["disc"], s["g"], s["shares"])
    ps_map[k] = ps
    cagr = (s["revY10"] / s["revY1"]) ** (1 / 9) - 1
    out[k] = {"revY1": s["revY1"], "revY10": s["revY10"], "mY1": s["mY1"], "mY10": mY10,
              "discount": s["disc"], "terminal_growth": s["g"], "future_shares": s["shares"]}
    print(k, "mY10=", mY10, "% -> per_share $", round(ps, 0), "(target", s["target"], "), equity $", round(eq / 1000, 1), "B, revCAGR", round(cagr * 100), "%")

wavg = 0.30 * ps_map["bear"] + 0.45 * ps_map["base"] + 0.25 * ps_map["bull"]
print("weighted(30/45/25) per_share $", round(wavg, 0), "| price", PRICE, "| margin", round((wavg / PRICE - 1) * 100), "%")
print("EV/sales today (pro-forma 650):", round((PRO_FORMA_MCAP - CASH + DEBT) / 650, 1), "x")
print("PARAMS:", json.dumps(out, ensure_ascii=False))
