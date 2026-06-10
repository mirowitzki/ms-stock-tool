# -*- coding: utf-8 -*-
# Fit explorer two-stage DCF params so each scenario per-share ~ SOTP midpoint.
# Replicates valuation_explorer.html scenarioForwardDCF. Units: rev/cash/debt = million CNY, shares = million.
import json

CASH = 1647.0   # 16.47 yi
DEBT = 2775.0   # 27.75 yi
PRICE = 7.81

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
    lo, hi = -30.0, 60.0
    for _ in range(80):
        mid = (lo + hi) / 2
        ps, _ = dcf(revY1, revY10, mY1, mid, disc, g, shares)
        if ps < target_ps:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)

scen = {
    "bear": {"target": 3.0, "revY1": 2300, "revY10": 3400, "mY1": -3, "disc": 11, "g": 2.5, "shares": 730},
    "base": {"target": 4.6, "revY1": 2400, "revY10": 4600, "mY1": -1, "disc": 10, "g": 2.5, "shares": 700},
    "bull": {"target": 7.7, "revY1": 2500, "revY10": 7000, "mY1": 2, "disc": 10, "g": 3.0, "shares": 685},
}
out = {}
ps_map = {}
for k, s in scen.items():
    mY10 = solve_mY10(s["target"], s["revY1"], s["revY10"], s["mY1"], s["disc"], s["g"], s["shares"])
    ps, eq = dcf(s["revY1"], s["revY10"], s["mY1"], mY10, s["disc"], s["g"], s["shares"])
    ps_map[k] = ps
    out[k] = {"revY1": s["revY1"], "revY10": s["revY10"], "mY1": s["mY1"], "mY10": mY10,
              "discount": s["disc"], "terminal_growth": s["g"], "future_shares": s["shares"]}
    print(k, "mY10=", mY10, "-> per_share", round(ps, 2), "yuan (target", s["target"], "), equity", round(eq / 100, 1), "yi")

wavg = 0.35 * ps_map["bear"] + 0.45 * ps_map["base"] + 0.20 * ps_map["bull"]
print("weighted(35/45/20) per_share", round(wavg, 2), "| price", PRICE, "| margin", round((wavg / PRICE - 1) * 100), "%")
print("PARAMS:", json.dumps(out, ensure_ascii=False))
