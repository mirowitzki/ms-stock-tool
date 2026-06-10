# 技能：交互器更新（explorer-update agent）

> 用户 2026-06-08 定：删掉了交互器里试做的"一键刷新按钮"（pywebview 接口在 target=_blank 打开的外部浏览器里拿不到、不稳），改成**按需派一个更新 agent 干活**——用户手动说"刷新 / 更新 <代码>（交互器）"时，主 Claude 用 Agent 工具起一个子代理，按本流程把该公司交互器的"会变的数据"更到最新、重渲。

## 触发
用户说"刷新 CRCL""更新 NVDA 交互器""把 002091 的价格更一下"之类 → 起 explorer-update 子代理（subagent_type 优先用 `explorer-updater`；当前会话若没加载该类型，就用 `general-purpose` 喂本技能流程）。

## 边界（最重要：这是数据刷新，不是重做分析——但要分清两层）
- **价格层（必须刷新到处处一致）**：月度股价、当前价 / 市值、下次财报日期、**以及一切引用现价的叙事数字**——安全边际、反向 DCF 隐含增速 / 要求 FCF 率、现价对中枢的倍数。这些是现价的机械函数，价格变了它们必须跟着变，否则交付物自相矛盾（2026-06-10 教训：RKLB 刷了价、`reverse_dcf_commentary` 还写着旧价 $72 / 隐含 60.9% / −91%，被用户逮个正着）。
- **基本面判断内核（绝不改）**：`scenarios` 的假设与 story、`probabilities`、价值区间、`pillars` 四柱判断与 details、报告正文——这些锚在财报与深度分析时点，要变得做完整重分析。
- 若发现**基本面已变**（新财报已发、重大并购 / 监管 / 指引、股价较分析时已大幅移动），**不要自己重估**——在结论里**明确建议用户让主 Claude 做一次完整重分析**（重抓 financials → compute_metrics → 重写报告相关章 → 重设情景 → 过质检关）。

## 流程
1. **重抓月度股价**：`python3 scripts/fetch_prices.py <代码>`（这台机器用 `/usr/bin/python3`）→ 更新 `analyses/<代码>/financials/prices.json`（股价图 + 最新收盘）。读回最新收盘价。
2. **更新当前价 / 市值**：联网核实（WebSearch "<代码> stock price market cap"）。股数 `diluted_shares_today` 一般不变（除非回购 / 增发 / 转股使其明显变化——那属基本面变化，见边界）。用最新价 × 现有股数算市值、或采用联网核到的市值，更新 `valuation_inputs.json` 的 `facts.market_cap`（必要时 `diluted_shares_today`）。
3. **价格层重算重写（必做，2026-06-10 加）**：facts 变了，引用现价的叙事数字全部跟着重写——
   - 用代码重算（绝不心算）：`scripts/valuation.py` 的 `reverse_dcf`（沿用解读卡原参数：折现率 / 终值 FCF 率 / 永续增长，10 年与 5 年口径都算；撞解算器上限就如实写"无解、上限只能解释 X% 市值"）+ 现价 vs 加权中枢 / Bull 的百分比与倍数；
   - 重写 `reverse_dcf_commentary`：market_story 的现价与市值、key_points 的隐含值、summary 的倍数与结论数字——**只换数字与倍数表述、保留故事骨架与判断措辞**；summary 末尾加一句口径说明（现价已按今日刷新、情景假设与概率仍为分析时点）；`pillars.headline` 若引用价格 / 安全边际数字也同步。verdict 颜色一般不动，新数字明显跨档时改档并在汇报里显著说明。
4. **更新下次财报日期**：若 `valuation_inputs.json` 的 `next_earnings.date` 已过期或临近，联网查新的下次财报日（WebSearch "<代码> next earnings date"），更新 `next_earnings`（date / period / estimated / basis）。
5. **轻量扫近期新闻**：WebSearch 最近 2–4 周有没有重大动作（财报、并购、监管、指引、管理层变动）。有 → 记下、在结论里提示是否需要完整重分析；没有 → 说明无重大变化。
6. **重渲交互器**：`python3 scripts/render_explorer.py <代码>`（读新的 prices.json + valuation_inputs.json 重生成 HTML）。
7. **校验 + 汇报**：确认 render 无报错、`valuation_inputs.json` 仍是合法 JSON、**渲染后 HTML 里解读卡数字与新现价一致（grep 新数字抽查）**；汇报——旧价→新价、旧市值→新市值、安全边际变化（现价 vs 不变的加权中枢）、新隐含预期 vs 旧值、下次财报、近期新闻是否需重分析、动了哪些文件。顺手 `python3 scripts/refresh_dashboard.py` 让值班台的月收盘同步。

## 注意
- 改完 facts 后，交互器的安全边际等计算值会按新价自动重算（加权中枢不变）；`reverse_dcf_commentary` 等**叙事数字不会自动变，必须按流程第 3 步用代码重算后改写**——刷价不刷叙事＝交付物自相矛盾。
- **报告 PDF 仍是分析时点口径**，价格 / 安全边际会和交互器略有出入，这是预期的（交互器是"活"视图、报告是定点深度分析）。
- 若价格变动大到让**结论性质**改变（如从安全边际 -56% 变成出现安全边际、verdict 跨档），别在 agent 里偷偷改基本面判断——改价格层数字可以、改结论要明确提示重做分析与报告。一切数字毛估、看方向。
