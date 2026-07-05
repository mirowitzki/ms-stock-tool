# 采集 A3：AI 数据中心光互连需求侧对激光器芯片需求的改写（截至 2026-07）

> 角色：数据采集员（只采集、不判断）。每个数字四件套 {value, as_of, source, confidence}。
> 采集日期：2026-07-05。检索渠道：联网公开源（TrendForce/LightCounting 官方稿、行业媒体、厂商公告、博客聚合站）。
> 基线对照：2026-06 旧判断（800G+ 2025 约 2400 万→2026 约 6300 万；1.6T 商用元年；CPO 2026-27 个位数%、大规模 2028 后；NVL72 机柜内走铜）。

---

## 1. 800G / 1.6T 光模块出货量最新预测

### 800G 及以上（合并口径）
- **2025 实际：2,400 万只（800G+）**
  - {value: 24M units, as_of: 2025-12-08（TrendForce 定稿口径）, source: TrendForce 官方稿 "AI Data Centers Ignite a Laser Shortage Wave"（trendforce.com/presscenter/news/20251208-12823.html）, confidence: 高}
  - ✅ 与基线"2025 约 2400 万"一致。
- **2026 预测：约 6,300 万只（800G+，同比 2.6 倍）**
  - {value: ~63M units（2.6×）, as_of: 2025-12/2026-02（TrendForce 两次重申）, source: TrendForce 官方稿 20251208 + 20260210（"Google 高速互连推 800G+ 占比 2026 超 60%"）, confidence: 高}
  - ✅ 与基线"2026 预期 6300 万"一致。
  - 分歧口径：Goldman Sachs 上修后 2026 年 800G（单档）3,350 万只（自 2,500 万上修 58%）{as_of: 2026-04 转引, source: c-light 聚合稿, confidence: 中低}；LightCounting 称 800G 出货 2026"翻倍以上、超 4,000 万只" {as_of: 2026-04, source: c-light 转引 LightCounting, confidence: 中}。
- **2027-2028**：800G+ 出货到 2028 年预计 9,400 万只 {value: 94M by 2028, as_of: 2026 上半年转引, source: c-light/High_Speed_Optical_Transceiver_Market 聚合（原始出处未署名）, confidence: 中低}；Woodside Capital：**1.6T 最快 2027 超越 800G 成为 AI 后端网络主力端口速率** {as_of: 2026, source: Woodside Capital 转引, confidence: 中}。

### 1.6T（2026＝商用元年，已坐实）
- **2026 需求区间：860 万–2,000 万只（口径分歧大）**
  - {value: 8.6M–20M units, as_of: 2026-04-02, source: c-light 聚合（Cignal AI >500 万只；Nomura 2,000 万只；另有"上游芯片短缺压到约 1,500 万只"一说）, confidence: 中（区间可信、点值不可信）}
  - 按终端客户拆：NVIDIA >500 万、Google 约 400 万、Meta 约 100 万 {as_of: 2026-04-02, source: c-light 聚合, confidence: 中低}
- **2025 实际（1.6T）**：约 400-500 万只（乐观 600 万）{as_of: 2024 末预测口径, source: Medium/deep-fundamental 转引, confidence: 低（预测非实绩、未见 2025 实绩定稿数）} → **1.6T 2025 实际出货定稿数：missing**
- 1.6T 芯片组（DSP 等）2026 销售额预计超 $20 亿 {as_of: 2026-04, source: LightCounting 转引, confidence: 中}
- LightCounting：未来五年 1.6T+3.2T 合计出货超 1 亿只 {as_of: 2026-04-02（OFC 2026 后）, source: hengtongglobal 转引 LightCounting, confidence: 中}
- 市场规模：AI 光模块市场 2025 $165 亿 → 2026 $260 亿（+57%）{as_of: 2026-04-20, source: TrendForce 官方稿 20260420-13017, confidence: 高}；其中 800G/1.6T 高速模块 2026 约 $146 亿 {as_of: 2026-03, source: LightCounting 转引（c-light）, confidence: 中}

---

## 2. 硅光渗透率走势（2024→2026）与每模块激光器用量 —— 对 EML 需求结构的直接改写

### 渗透率
- **硅光占全部光模块销售额：2018 年 10% → 2024 年 33% → 2026 年预计过半（>50%）**
  - {value: 33%（2024）→ >50%（2026E）, as_of: 2025-11, source: LightCounting 官方 newsletter "2026 – The year of Silicon Photonics"（lightcounting.com/newsletter/en/november-2025-...436）, confidence: 高}
- 800G 单档：硅光方案已占约 50%、份额仍在上升；800G/1.6T 合并口径预计到 50-70% {as_of: 2026-04-02, source: c-light 聚合稿, confidence: 中}
- 驱动结构（重要机制，TrendForce 原话）："NVIDIA 激进锁定 EML 产能保障自身供应，**客观上加速了非 NVIDIA 阵营向 CW 激光器＋硅光方案迁移**" {as_of: 2025-12-08, source: TrendForce 官方稿, confidence: 高}
- 代工侧佐证：Tower 硅光产能 2025 底翻倍、2026 年中三倍（$3 亿投资）；AMF 客户超 300 家 {as_of: 2025-11, source: LightCounting, confidence: 中高}

### 每模块激光器用量（换算系数）
- **EML 方案**：800G DR8/2×FR4（100G/lane）＝ **8 颗 100G EML**；1.6T DR8（200G/lane）＝ **8 颗 200G EML**；800G DR4（200G/lane）＝ **4 颗 200G EML**（O 波段 CWDM4 1271/1291/1311/1331nm + LWDM4）
  - {as_of: 2024-09（Source Photonics 产品稿）至今架构未变, source: Source Photonics ECOC'24 公告 + semiconductor-today, confidence: 高}
- **硅光方案**：外置 CW 激光器泵浦、四通道共享一颗——**800G 硅光模块仅需 2 颗 CW（约 70mW）；1.6T 硅光模块 2-4 颗 CW（约 100mW）**
  - {as_of: 2025→2026 通行设计, source: NADDOD 技术博客（naddod.com/blog/silicon-photonics-vs-eml...）+ FiberMall, confidence: 中高}
- **换算含义（纯算术、不判断）**：同一只 800G 模块从 EML 方案换到硅光方案，激光器颗数 8→2（-75%）、且从高价 EML 换成低价 CW；1.6T 从 8 颗 200G EML→2-4 颗大功率 CW。

---

## 3. CPO 最新时间表与外置光源（CW）需求量级

### NVIDIA
- **Quantum-X Photonics（InfiniBand，115.2Tb/s、144×800G）：2026 年初商用出货**（兑现 GTC2025 排期）{as_of: 2026-03 前后多源, source: NVIDIA 官方 + genaitech/tomshardware, confidence: 高}
- **Spectrum-X Photonics（Ethernet，最高 409.6Tb/s）：2026 下半年商用** {as_of: 2026, source: NVIDIA 官方 press release, confidence: 高}
- **外置光源用量**：Quantum-X 单台用 **18 个 ELSFP 外置激光模块**（每个 ELSFP 给 8 个 1.6T 光引擎供光、ELSFP 标准每模块最多 8 通道 CW、1311nm、最高 25dBm/通道）；官方口径"**每单位带宽激光模块数约为可插拔方案的 1/4**"
  - {as_of: 2025→2026, source: MapYourTech CPO 架构综述 + TE/Lumentum ELSFP 产品页 + Quantifi, confidence: 中高}
  - 对照算术（不判断）：等效 144×800G 可插拔若走 EML DR8 需 144×8=1,152 颗 EML；CPO 方案＝18 ELSFP×≤8 通道 ≈ ≤144 颗大功率 CW。
- **NVIDIA $40 亿锁激光器（2026-03-02 官宣）**：Coherent、Lumentum 各 $20 亿，含多年采购承诺+产能优先权（Coherent 披露扩至 5 个 CPO 相关产品族）；另与 Marvell $20 亿光 I/O 合作
  - {value: $2B+$2B（+$2B Marvell）, as_of: 2026-03-02（The Register 2026-04-05 亦证实）, source: genaitech.net + theregister.com, confidence: 高}

### Broadcom / TSMC
- **TH5-Bailly（51.2T CPO）**：已量产出货（第二代）；**TH6-Davisson（102.4T、200G/lane CPO）2025-10-08 官宣出货、当前 early-access 送样、GA 待定** {as_of: 2025-10-08, source: Broadcom 官方 press release + ServeTheHome, confidence: 高}
- **TSMC COUPE**：TH6-Davisson 光引擎基于 COUPE 平台异构集成（衬底级多芯片封装）；NVIDIA Quantum-X 的 24 个光引擎同样 COUPE 工艺 {as_of: 2025-10→2026, source: Broadcom 官方稿 + MapYourTech, confidence: 高}
- OFC 2026 现场口径：CPO"已演示、未到面上量产"——Open CPX MSA 成立推进标准化，但"大规模 CPO/NPO 部署仍取决于封装、散热、测试基础设施的进一步成熟" {as_of: 2026-04-02, source: hengtongglobal OFC2026 综述, confidence: 中}

### 渗透率预测（口径要分清）
- **LightCounting（2025-12 最新）**：scale-up CPO 交换机 2026 年由 Broadcom+NVIDIA 双双推出、**2027 起放量出货**；CPO 端口 2030 年近 1 亿个/年、市场 $100 亿 {as_of: 2025-12, source: LightCounting newsletter 320（"2025 was the year of CPO"）, confidence: 中高}
- 旧口径（沿用注意）："LPO+CPO 合计占 2026-2028 部署的 800G/1.6T 端口 >30%"、"CPO 端口 2023 年 5 万→2027 年 450 万" {as_of: 2023→2024 的 LightCounting 预测（年份较旧）, source: LightCounting 历史 newsletter, confidence: 低（预测口径旧、且 LPO+CPO 合并）}
- ⚠️ 基线"CPO 替代 2026-27 个位数%"：以端口占比论 2026 仍成立（Quantum-X 2026 初才商用），但 **2027 的口径已被上修**——LightCounting 2025-12 把 scale-up CPO 放量点钉在 2027，多源出现"2027 年 CPO 近 30% of 800G/1.6T 端口"的转引 {confidence: 低-中，各源打架}。**"大规模 2028 后"需下修为"2027 起放量"（LightCounting 口径）**。

---

## 4. LPO / LRO 2026 实际采用状态（动 DSP、不动激光器）

- **技术事实（换算中性）**：LPO 去掉 DSP、LRO 只保留发端 DSP（收端线性）——**两者都不改变模块内激光器颗数与类型**（EML 还是 8 颗、硅光还是 2-4 颗 CW），动的是 DSP 数量（LPO -100%、LRO -50%）与功耗（约 -30%~-50%）{as_of: 2026, source: DustPhotonics/Semtech/IEEE EPS 综述, confidence: 高（架构事实）}
- **2026 实际状态**：
  - 1.6T 档 FRO（全 retimed）/LRO/LPO 三线并存产品化：Eoptolink 在 OFC 2026 展出全系列 {as_of: 2026-04, source: hengtongglobal + eoptolink 官网, confidence: 高}
  - 1.6T 功耗 >30W 使 **LRO 被视为近期更可行路线**（保发端 DSP 换取集成与散热）{as_of: 2026-03, source: IEEE EPS LPO 综述 V2（2026-03 更新）+ 多源, confidence: 中高}
  - DSP 侧供给：Broadcom Sian2（1.6T 8:8）、Marvell Nova 2、Credo 首发发端-only 800G DSP（即 LRO 用）{as_of: 2025→2026-03, source: Ethernet Alliance ECOC 2025 + OFC 2026 报道, confidence: 高}
  - 真实部署锚点：**华为在自家 XPU 集群 scale-up 用 LPO、每 XPU 最多 18 只 LPO**（CloudMatrix 类超节点）{as_of: 2025-12, source: LightCounting newsletter 320, confidence: 中高}
  - 聚合站口径"LPO 2026 年约占 15% 市场份额" {as_of: 2026-04-02, source: c-light, confidence: 低}；"2026-27 超三分之一的数据中心内 800G 部署采用 LPO 或混合 LPO-DSP" {source: dataintelo 市场报告, confidence: 低（营销味报告）}
- **北美头部超大规模客户的 800G scale-out LPO 量产采用**：仍未见具名公告级证据 → **missing**（现有证据集中在华为 scale-up + 亚太个别部署）

---

## 5. 铜互连封顶层：机柜内 scale-up 仍是铜的天下、光化时间表首次钉死

- **GB200/GB300 NVL72**：机柜内 NVLink 全铜（背板铜缆 5,000+ 根量级）——基线成立、无变化 {as_of: 2025→2026, source: SemiAnalysis 多篇, confidence: 高}
- **Vera Rubin NVL144（2H26 出货）**：**scale-up 仍全铜**——沿用 Oberon 机架设计、无源铜缆数量约翻倍（NVLink6 带宽翻倍）{as_of: 2026（SemiAnalysis Vera Rubin 拆解）, source: newsletter.semianalysis.com "Vera Rubin – Extreme Co-Design", confidence: 高}
- **Rubin Ultra NVL576 / Kyber 机架（2027）**：**scale-up CPO 首次进场——但只用于 8 个机架之间的互连（两层 all-to-all），机架内部 scale-up 仍走铜背板** {as_of: 2026-04, source: SemiAnalysis + The Register 2026-04-05, confidence: 中高}
- **Feynman 代（2028 年中后段出货）**：NVLink scale-up **铜/CPO 双版本可选**——NVIDIA 首次把光 NVLink 列为正式选项；"2028 年单系统上千 GPU 靠光互连" {as_of: 2026-04-05, source: The Register（NVIDIA GTC 2026 披露）, confidence: 中高}
- 官方姿态：黄仁勋"能用铜就用铜、必须用光才用光"（copper when possible, optics when necessary）未变；但 GTC 2026 首次公开 scale-up 光化路线图 {as_of: 2026-03/04, source: The Register/Tom's Hardware, confidence: 高}
- **对基线的改写**：①"NVL72 机柜内走铜"仍对；②新增：**scale-up 光化最早时点＝2027（NVL576 机架间 CPO）、全面可选＝2028（Feynman）**——铜的封顶从"无期限"变成"有日期的倒计时"，但机柜内（≤72-144 GPU 域）铜至少统治到 2027。

---

## 6. 电信侧基本盘：50G PON 与城域 400G/800G

- **50G PON 节奏**：
  - 中国主导、跳过 25G：运营商从 10G 直上 50G {as_of: 2025→2026, source: Light Reading, confidence: 高}
  - 商用试点已落地：中国移动+中兴 2025-06 江苏落地全球首个 50G PON FMC 社区；中国电信上海 50G-PON 现网覆盖；华为 50G PON 方案获 60+ 运营商商用/验证（含移动/电信/联通）{as_of: 2025-06→2026, source: ZTE 官方稿 + CT Americas + Lightwave, confidence: 高}
  - 规模化：行业共识"2025-26 行业级首批部署、**大规模住宅部署 2027 年后**、2026-2028 进入规模商用窗口" {as_of: 2025→2026, source: Light Reading/Dell'Oro/Adtran 博客, confidence: 中高}
  - **中国移动 50G PON OLT 集采规模（端口数/金额）：missing**（美区检索未见 2026 年专项集采公告）
  - 市场规模（参考）：全球 50G PON 技术市场 2031 年 $15.8 亿、CAGR 38.2% {as_of: 2026, source: openpr 转引（QYResearch 类）, confidence: 低}
- **对激光器的含义（采集口径）**：50G PON 下行 50G 用 25G/50G 级 EML/DML+APD，是国产激光器（源杰等）传统主场的下一代增量，但 2026 年仍处"试点→集采前夜"，**未到放量**；增量数字缺席 → 每年 OLT/ONU 激光器颗数增量：**missing**
- **城域/骨干 400G/800G（相干为主）**：
  - 电信相干带宽 2025 年增长 >40% {as_of: 2026 初, source: c-light 转引, confidence: 中}
  - 相干光模块 2025 年收入近 $60 亿（Cignal AI）；400G+ 单季（2025Q3）出货破 1,000 万只、收入超 $50 亿（含数通）{as_of: 2025→2026, source: Cignal AI 转引, confidence: 中}
  - 2026 电信光模块市场：LightCounting 2026-03 口径全行业（含数通）2026 增速约 60%、2031 年近 $600 亿：其中电信部分增长温和 {as_of: 2026-03, source: c-light 转引 LightCounting, confidence: 中}
  - 城域 400G/800G 对 EML/DFB 颗数需求的拆分数字：**missing**（相干侧用 ITLA 窄线宽激光器、非 EML/DFB 口径；直调直检城域短距是 EML 主场但无公开分速率颗数数据）

---

## 7. 每 GPU 光模块配比（最新各家口径与假设）

- **H100 一代基准**：1 GPU ≈ 2.5 只 800G（sell-side 通行算法：400G CX7 NIC、800G 交换端口、三层胖树摊薄）{as_of: 2024→2025 通行, source: Medium/deep-fundamental + 多家券商, confidence: 高（作为口径基准）}
- **设备级精确口径（FiberMall）**：
  - A100+CX6+QM8700 三层：1:6（全 200G）
  - A100+CX6+QM9700 两层：1:0.75×800G + 1:1×200G
  - H100+CX7+QM9700 两层：1:1.5×800G + 1:1×400G
  - H100+CX8+QM9700 三层：1:6（全 800G）
  - {as_of: 2024→2025（架构未变仍适用）, source: fibermall.com/blog/how-many-optical-transceivers-needed-for-gpu.htm, confidence: 高（口径清晰）}
- **集群规模放大效应**：5-10 万卡、五层以上网络 → 比率可到 **1:5 以上**；纯推理（南北向为主、容忍时延）→ 可压到 **1:0.5** {as_of: 2025, source: Medium/deep-fundamental, confidence: 中}
- **Rubin 代（2H26）**：Vera Rubin NVL72 **每 GPU 两个 800G OSFP 笼＝1.6T scale-out 带宽/GPU**（双 800G 逻辑口便于多平面组网、优于单 1.6T 口）——per-GPU 光模块需求较 Blackwell 代翻倍（NIC 侧 1→2 只 800G，交换侧同步放大）{as_of: 2026, source: SemiAnalysis "Vera Rubin – Extreme Co-Design", confidence: 中高}
- 需求侧总量交叉（McKinsey 口径、注意与 TrendForce 打架）：2029 年光模块总需求 2,800 万只、其中 1.6T 占 41%；800G 2027 年前缺口 40-60%、1.6T 到 2029 缺口 30-40% {as_of: 2026-03（genaitech 转引）, source: McKinsey via genaitech.net, confidence: 低（总量与 TrendForce 6,300 万/2026 严重不一致、疑口径不同[或仅部分场景]，仅取其"缺口方向"）}

---

## 8. 供给侧（顺手采到、与需求改写直接相关）

- **EML 交期"排到 2027 以后"**；全球仅五家供应商：Lumentum、Coherent(Finisar)、三菱、住友、Broadcom；NVIDIA 锁产能造成全球性短缺 {as_of: 2025-12-08, source: TrendForce 官方稿, confidence: 高}
- **CW 激光器同样产能吃紧**（设备交期+人力密集测试），供应商加速扩产 {as_of: 2025-12-08→2026-04-20, source: TrendForce 两稿, confidence: 高}
- TrendForce 2026-04-20：EML 与 CW-LD 双双列为 2026 年 AI 光模块扩产的**头号瓶颈**（其次：光对准等高精制程、功耗散热）{as_of: 2026-04-20, source: TrendForce 官方稿 20260420-13017, confidence: 高}
- 竞对挤出效应：媒体口径"NVIDIA $40 亿锁激光器把其余买家推到 2027 之后" {as_of: 2026-05-27, source: techtimes, confidence: 中}
- 400G/lane 下一代已露头：Broadcom OFC 2026 首发 400G EML+PD（配 Taurus 400G/lane DSP）——3.2T 世代 EML 路线继续存在 {as_of: 2026-04, source: hengtongglobal OFC2026 综述, confidence: 中高}
- AAOI 2026-03 拿下 $2 亿+ 1.6T 大单（三家超大规模客户、2027 年中月收入目标 $3.78 亿/月）{as_of: 2026-03, source: genaitech 转引 AAOI CFO, confidence: 中}

---

## 9. 与 2026-06 基线的逐条对照（只列事实差异、不下判断）

| 基线（2026-06） | 最新采集（2026-07） | 状态 |
|---|---|---|
| 800G+ 2025 约 2,400 万只 | TrendForce 定稿 2,400 万 | ✅ 证实 |
| 2026 预期 6,300 万只 | TrendForce 两次重申约 6,300 万（2.6×）；GS 单 800G 3,350 万、LC 800G >4,000 万 | ✅ 证实（另补 1.6T 拆分 860-2,000 万） |
| 1.6T 商用元年 | OFC 2026 确认量产出货（Eoptolink/FICG 等）、NVIDIA/Google/Meta 三家 2026 需求约 1,000 万级 | ✅ 证实且已兑现 |
| CPO 2026-27 个位数% | 2026 端口占比仍小（Quantum-X 2026 初才商用）✅；但 LightCounting 2025-12 把 **scale-up CPO 放量钉在 2027**、2030 年近 1 亿端口/$100 亿 | ⚠️ 2027 后口径上修 |
| CPO 大规模 2028 后 | LightCounting 新口径：2027 起放量（Broadcom+NVIDIA scale-up CPO 交换机 2026 发布、2027 出货） | 🔄 需更新为"2027 放量" |
| NVL72 机柜内走铜 | 仍走铜；且 Vera Rubin NVL144（2H26）scale-up 仍全铜 | ✅ 证实 |
| （基线无）scale-up 光化时点 | **新增**：NVL576（2027）机架间 CPO 首进 scale-up；Feynman（2028 中后）铜/CPO NVLink 双版本 | ➕ 新增关键日期 |
| （基线无）激光器供给格局 | **新增**：EML 交期超 2027、五家寡头、NVIDIA $40 亿锁 Coherent+Lumentum（2026-03-02）；非 NVIDIA 阵营被推向 CW+硅光 | ➕ 新增结构性事实 |
| （基线无）硅光渗透 | **新增**：硅光占光模块销售额 2024 年 33%→2026 年过半（LC）；800G 内约 50%；每模块激光器 8 EML→2-4 CW 的结构替换 | ➕ 新增（EML 需求结构被直接改写） |

## 10. Missing 清单（查不到、留给下一轮）

1. 1.6T 2025 年实际出货定稿数（只有当年预测 400-600 万）
2. 中国移动/电信 50G PON OLT 集采规模（端口数、金额、中标份额）——美区检索无果，需中文渠道
3. 城域 400G/800G 直调直检口径的 EML/DFB 分速率颗数需求
4. 50G PON 对上游 25G/50G EML/DML 的年颗数增量测算
5. 北美超大规模客户（Google/Meta/AWS/MSFT）800G scale-out LPO 量产采用的具名公告级证据
6. Spectrum-X Photonics 2H26 的实际出货量指引（只有"商用时点"无量）
7. Quantum-X CPO 交换机 2026 年出货台数预测（缺 LightCounting 完整报告数据）
8. McKinsey"2029 年 2,800 万只"的口径定义（与 TrendForce 6,300 万/2026 无法调和）

## 主要来源索引

- TrendForce 官方稿：20251208-12823（激光器短缺）、20260210-12919（800G+ 占比超 60%）、20260420-13017（$260 亿市场+瓶颈）
- LightCounting newsletter：2025-11（硅光之年）、2025-12（CPO 之年，#320）、March 2026 Ethernet Optics（#382，未获全文）
- NVIDIA 官方 press release（Quantum-X/Spectrum-X Photonics）；Broadcom 官方（TH6-Davisson，2025-10-08）
- The Register 2026-04-05（NVIDIA 光 scale-up 路线图）；SemiAnalysis（Vera Rubin 拆解、CPO book、Optical Boogeyman）
- genaitech.net 2026（NVIDIA $4B 拆解+McKinsey 缺口）；c-light 聚合稿 2026-04-02；hengtongglobal OFC 2026 综述（2026-04-02）
- Source Photonics ECOC'24（EML 颗数）；NADDOD/FiberMall（硅光 CW 颗数、GPU 配比）；ZTE/Light Reading/Dell'Oro（50G PON）
