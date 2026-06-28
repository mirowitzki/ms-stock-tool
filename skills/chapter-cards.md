# 章节卡交付标准（每章在交互器里的呈现 + 防偷懒闸门）

> 用户决定"一章一章过、定每章在交互器里的呈现(display)与交付标准"（2026-06-28 起）。
> 这份文档钉死**已定标准**的章；**ch3–9 用户要一章一章再定，别自作主张提前做**。
>
> 三条铁律：
> 1. **代码供数、我下判断**——卡里的数字（业务速览/总账速览）由代码从 `segments.json` / `financials.csv` 算，判断（脊梁/护城河/暗线/双面判读…）由我写进 `valuation_inputs.json` 的 `chN` 块。
> 2. **卡（执行摘要）在上、正文在下、同一个框**——`render_explorer` 把 `chN` 卡嵌在该章正文顶部；报告 `.md` 里那章的 `### 执行摘要` 小节会被 `_strip_exec_summary` 剥掉（卡承担、正文里不重复），但 `.md` / PDF 源保留。
> 3. **标准进代码闸门、不靠自觉**——`check_chapters.py` 校验已定标准的章"卡填没填全、报告脚手架写没写"；`qc_gate` 出 PDF 前硬拦、`render_explorer` 渲染时报缺。每新定一章，就把它加进 `REQUIRED_CARDS` / `CHAPTER_SCAFFOLDS`。

## 怎么给一章定标准（流程）

定一章 = 定四件事：① 这章的**承重判断**（必须交付的那一个判断）② 用什么**呈现**承载它（卡的形态）③ **卡片字段** ④ **数据分工**（代码算什么、我写什么）。外加一条**正文深度线**（这章正文的硬标准）。定完落地：

- `valuation_inputs.json` 加 `chN` 块（字段＝我写的判断）；
- `render_explorer.py` 加 `build_chN_card()`（代码供数）+ 模板 `chNCardHTML()`（渲染）+ `renderReport` 在 `i===N-1` 那张卡顶部嵌入；
- `check_chapters.py` 的 `REQUIRED_CARDS` 加这张卡的必填字段、`CHAPTER_SCAFFOLDS` 加这章正文必含的表；
- `report-template.md` 对应章注明"必出 X 卡 + Y 脚手架"。

---

## 第一章 业务质量判断卡（已定）

- **承重判断**：这是门什么生意、质量好坏、价值在哪。
- **呈现**：质量光谱（复利机器→有壁垒但受困→稳健低回报→无壁垒苦力活→题材故事，5 档标记+判词）+ 五字段 + 业务速览表。
- **`ch1` 块字段**：`essence` / `thesis`（可选，卡里核心论点优先用它、否则用报告抽出的"核心论点/核心结论"）/ `quality{pos,verdict}` / `moat` / `evidence` / `steelman` / `variant` / `power_center` / `segment_dim`（指定用哪个分部维度）/ `segment_roles{业务名:{role,kind,source}}`（`kind`=eng/good/warn/bad 决定标签配色）。
- **数据分工**：业务速览数字来自 `segments.json`（代码）、判断来自 `ch1` 块（我）、核心论点来自 `ch1.thesis` 或报告抽取。
- **闸门必填**：`essence, quality.verdict, moat, evidence, steelman, variant, power_center, segment_roles`。

## 第二章 历程判断卡（已定）

- **承重判断**：**看行为不看口号**——从历史动作里读出"控股股东/管理层会怎么对待这个平台"的行为模式 + 会重演的暗线（或清晰的期权）。对资本运作平台型标的，历史的预测力比任何财务比率都强。
- **标尺**：超卓航科（688237）深版《发展历程》——执行摘要先立叙事弧、看行为读管理层、植入峰值坐标、剥口号纠外界叙事、一次性 vs 经营分开、控制权/期权单列、总账表双面收束。
- **呈现（卡的 6 槽位）**：
  1. **历程脊梁**（`spine`）——一句话把整段史拉直（如 600327："国资老字号→均瑶资本运作平台→减法/加法/收缩"）。
  2. **分段时间轴**（`phases`）——2–4 段，每段 `{label, period, kind, text, tags[]}`；`kind`=neutral/warn/bad/good/eng 决定配色（中性/要盯/利空已兑现/正面/战略）。
  3. **看行为读出的模式**（`revealed_behavior`）——从动作读管理层/控股股东行为模式（钱用在哪、资本纪律、关联交易倾向）。
  4. **会重演的暗线 / 清晰的期权**（`darkline{label, kind, text}`）——按公司二选一填（暗线如 600327 抽血、期权如超卓控制权题材）；`label` 跟着改。
  5. **峰值坐标**（`peak_anchor`，可选）——历史利润/规模峰值当基准。**口径要对**：如 600327 营收峰值在汽车全并表的 2020（¥79 亿），归母峰值在 2021（含汽车处置一次性收益），别混。
  6. **总账速览 + 双面判读**（`scorecard_read{exposes, hidden_strength}`）——多年营收/归母/经营现金流（代码从 `financials.csv` 算）+ 一句"数字暴露什么"+"没讲完的底气"。
- **数据分工**：总账速览数字＝代码（`build_ch2_card` 复用 `build_history`，取最近 6 年 营收/归母/经营现金流；财务里没有"扣非"概念，扣非放正文手抄全表）；其余判断＝我写进 `ch2` 块；`peak_anchor` 由 block 提供（是判断、口径要核）。
- **闸门必填**：`spine, phases, revealed_behavior, darkline.text, scorecard_read.exposes, scorecard_read.hidden_strength`。
- **正文深度线（7 条必做，写报告第二章时照此、过 depth/insight 关）**：
  ① 执行摘要先立叙事弧（分清晰 N 段），不平铺流水账；
  ② 历史沿革大事记表（时间/类型/大事，从家族/上市前到最近一季、每行带具体数字）；
  ③ 逐段按命名阶段展开（不机械按年）：每段"做了什么动作[剥口号]→为什么→暴露什么"；
  ④ 植入峰值坐标，后续起伏对照它读；
  ⑤ 剥口号 ＋ 纠正外界错误叙事（认知差）＋ 一次性 vs 经营分开；
  ⑥ 看行为不看口号：从资金部署/资本纪律/关联交易倾向读管理层；
  ⑦ 总账表双面收束：多年表 +「暴露的几个问题」+「没讲完的底气」+ thesis 级收束。
- **报告脚手架（闸门校验）**：第二章正文必含 **≥2 张 markdown 表**（大事记表 + 上市以来总账表）。

---

## ch3 – ch9：未定

用户**一章一章再定，别提前做**。定下一章时按上面"怎么给一章定标准"的流程走，定完更新本文件 + `REQUIRED_CARDS` + `CHAPTER_SCAFFOLDS` + `report-template.md`。

## 闸门（防偷懒）实现位置

- `scripts/check_chapters.py`：`verify_chapters(ticker) → (ok, problems)`；`REQUIRED_CARDS`（卡必填字段）+ `CHAPTER_SCAFFOLDS`（报告章必含表数）。CLI：`python scripts/check_chapters.py <代码>`。
- `scripts/qc_gate.py`：`verify_qc` 第 ② 步调 `verify_chapters`（**总是跑、独立于质检登记**）；`do_record` 打印章节状态。出 PDF 前硬拦。
- `scripts/render_explorer.py`：渲染末尾一行报缺（非致命、不刷屏批量重渲）。
- **存量公司**（除 600327）尚无完整 `ch1`/`ch2` 块，会被闸门报缺 / 拦 PDF——**这是有意的**，提示这些报告需按新标准补卡（与 CLAUDE.md 交接备忘"11 份待重做"一致）。
