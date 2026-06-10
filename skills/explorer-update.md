# 技能：交互器更新（explorer-update agent）

> 用户 2026-06-08 定：删掉了交互器里试做的"一键刷新按钮"（pywebview 接口在 target=_blank 打开的外部浏览器里拿不到、不稳），改成**按需派一个更新 agent 干活**——用户手动说"刷新 / 更新 <代码>（交互器）"时，主 Claude 用 Agent 工具起一个子代理，按本流程把该公司交互器的"会变的数据"更到最新、重渲。

## 触发
用户说"刷新 CRCL""更新 NVDA 交互器""把 002091 的价格更一下"之类 → 起 explorer-update 子代理（subagent_type 优先用 `explorer-updater`；当前会话若没加载该类型，就用 `general-purpose` 喂本技能流程）。

## 边界（最重要：这是数据刷新，不是重做分析）
- 更新 agent 只刷**会随时间变的数据**：月度股价、当前价 / 市值、下次财报日期，外加扫一眼近期有没有重大新闻。
- **绝不改**估值的判断内核：`scenarios`（三情景假设）、`pillars`（四柱判断）、`reverse_dcf_commentary`、报告正文——这些是某一时点的深度分析，要变得做完整重分析。
- 若发现**基本面已变**（新财报已发、重大并购 / 监管 / 指引、股价较分析时已大幅移动），**不要自己重估**——在结论里**明确建议用户让主 Claude 做一次完整重分析**（重抓 financials → compute_metrics → 重写报告相关章 → 重设情景 → 过质检关）。

## 流程
1. **重抓月度股价**：`python3 scripts/fetch_prices.py <代码>`（这台机器用 `/usr/bin/python3`）→ 更新 `analyses/<代码>/financials/prices.json`（股价图 + 最新收盘）。读回最新收盘价。
2. **更新当前价 / 市值**：联网核实（WebSearch "<代码> stock price market cap"）。股数 `diluted_shares_today` 一般不变（除非回购 / 增发 / 转股使其明显变化——那属基本面变化，见边界）。用最新价 × 现有股数算市值、或采用联网核到的市值，更新 `valuation_inputs.json` 的 `facts.market_cap`（必要时 `diluted_shares_today`）。**只动 facts，别碰 scenarios / pillars / reverse_dcf_commentary。**
3. **更新下次财报日期**：若 `valuation_inputs.json` 的 `next_earnings.date` 已过期或临近，联网查新的下次财报日（WebSearch "<代码> next earnings date"），更新 `next_earnings`（date / period / estimated / basis）。
4. **轻量扫近期新闻**：WebSearch 最近 2–4 周有没有重大动作（财报、并购、监管、指引、管理层变动）。有 → 记下、在结论里提示是否需要完整重分析；没有 → 说明无重大变化。
5. **重渲交互器**：`python3 scripts/render_explorer.py <代码>`（读新的 prices.json + valuation_inputs.json 重生成 HTML）。
6. **校验 + 汇报**：确认 render 无报错、`valuation_inputs.json` 仍是合法 JSON；汇报——旧价→新价、旧市值→新市值、安全边际变化（现价 vs 不变的加权中枢）、下次财报、近期新闻是否需重分析、动了哪些文件。

## 注意
- 改完 facts 后，交互器的安全边际会按新价自动重算（加权中枢不变）——这是对的。但**报告 PDF 仍是分析时点口径**，价格 / 安全边际会和交互器略有出入，这是预期的（交互器是"活"视图、报告是定点深度分析）。
- 若价格变动大到让结论性质改变（如从安全边际 -56% 变成出现安全边际），别在 agent 里偷偷改判断——明确提示需要重做分析与报告。
- 改完 facts 顺手看一眼 `reverse_dcf_commentary` 引用的市值 / 隐含增速是否还大致自洽；大幅偏离就提示重分析。一切数字毛估、看方向。
