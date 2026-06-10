# 【MS股票价值分析工具】

一个秉持价值投资理念的股票分析工具，在 **Claude Code** 里以中文交互运行。

> **你不需要会编程。** Claude Code 会替你写代码、跑命令；你只需用中文告诉它目标。
> 全程交互运行，吃的是 Max 订阅额度，基本不产生额外费用。

## 核心原则：代码算数，Claude 判断
- **代码负责**：抓数据、算所有者盈余与 DCF、读写文件 —— 免费且精确，**绝不让模型做算术**。
- **Claude 负责**：理解生意、判断护城河、评估管理层与文化、写备忘录 —— 判断密集、价值最高的部分。

## 目录结构
```
ms-stock-tool/
├── CLAUDE.md                      # 工具的“行为说明”，Claude Code 会自动读取
├── README.md
├── requirements.txt               # 依赖清单
├── skills/                        # 方法论（提炼一次，长期复用）
│   ├── business-understanding.md  # 第 1 层：像 CEO 一样理解生意（含组织/管理/文化）
│   ├── moat-analysis.md           # 第 2 层：护城河
│   └── valuation.md               # 第 2 层：估值
├── templates/
│   └── dossier-template.md        # 第 1 层产出的固定结构
├── scripts/
│   ├── fetch_filings.py           # 第 0 层：从 SEC EDGAR 取数（纯代码）
│   └── valuation.py               # 估值计算（纯代码）
└── analyses/                      # 每家公司一个文件夹，逐渐积累成你的“能力圈档案”
```

## 怎么用（不用记命令，直接用中文跟 Claude Code 说）
打开 Claude Code 指向本文件夹后，用中文告诉它，比如：
> “请帮我安装依赖，把我的 SEC 身份设成‘我的名字 我的邮箱’，然后抓取 RKLB 最近 5 年的资料。”

它会自己完成安装、设置和取数，再带你做第 1 层“理解生意”和第 2 层“价值分析”。

## 三层流水线
0. **取数** → `analyses/<代码>/`（10-K、委托书、XBRL 财务数据）
1. **理解生意** → `analyses/<代码>/dossier.md`（最重要的一层）
2. **价值分析** → `analyses/<代码>/memo.md`

> 纪律：**看不懂的生意，不估值。** 这个判断由你来做，工具帮你厘清。
