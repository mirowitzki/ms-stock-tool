# 300996 普联软件 · 进度（2026-07-04）

## 已完成
1. 取数全套（5年年报+80公告+prices+metrics+segments三维度全）；招股书抓错文档（只有确认意见598字节、用2021年报+联网补起源）
2. 一手研究：`_facts_firsthand.md`（带年报行号底稿）+ 三个联网agent存档 `_industry_research.md`、`_gov_narrative_research.md`
3. `_thesis.md` 四步定稿：真卡位、普通生意、故事价格
4. 九章报告写完（约1.7万字、**瘦身纪律第一次实战**：一个事实一个家/收口一次/ch9四块/表格化），章节闸门一次通过
5. `valuation_inputs.json`（ch1-ch9九卡+三情景判断带[熊2.9-3.4/中5.3-6.0/牛11-14]+likelihood+四柱+区间口径commentary）+ `decision.json`（P1-P4预测+premortem+odds区间口径）
6. render_explorer 已渲染（9章嵌入）；check_numbers 已跑（58处未匹配=公告/外部数、交fact-check裁决）

## 进行中：五关质检
- 第一关 check_numbers ✅已跑
- 四个独立agent后台跑：防幻觉(a675…)/防成见(a5ba…)/防写水(a1e2…)/防浅析(a3f6…)
- 收齐后：裁决→改🔴（**记得同步扫 valuation_inputs.json 卡片、grep全部出现处——600327两条教训**）→复核→`qc_gate --record` 五关→重渲→refresh_dashboard→git提交

## 关键估值锚（防丢）
现价11.81×3.958亿股=市值46.7亿（2025年度10转4已于2026-04-22实施、腾讯行情核定）；净现金5.9亿；PE扣非83x；安全边际vs熊-73%/vs中-52%/vs牛+6%；verdict=stretched按牛市定价

## 已知小尾巴
- metrics.json 分红/回购字段为0系管道漏抓（报告用年报口径：五年分红1.64亿）——O系列工程加固时修
- 2024年报员工数2689已核；FY2020分派10转6派3于2021-07实施（上市首月）
