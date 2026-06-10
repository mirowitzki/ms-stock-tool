#!/usr/bin/env python3
"""
queue_hook.py —— Claude Code UserPromptSubmit Hook

每次用户发消息时被触发，读取 analyses/_queue.json：
- 若空 → 安静退出，对用户消息无影响
- 若非空 → 输出 additionalContext，告诉 Claude 当前有待办队列

设计原则：
- 始终 exit 0，永远不阻塞用户消息
- 出任何错都安静吞掉（hook 不能让用户对话被卡住）
- 只在队列真有内容时才输出
"""

import json
import os
import sys
from pathlib import Path


def main():
    try:
        project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
        queue_path = project_root / "analyses" / "_queue.json"

        if not queue_path.exists():
            return 0

        try:
            # utf-8-sig 同时兼容有 BOM 和无 BOM（Windows Notepad 默认带 BOM）
            queue = json.loads(queue_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return 0

        if not isinstance(queue, list) or not queue:
            return 0

        # 提取待分析的 ticker 列表
        tickers = []
        for item in queue:
            if isinstance(item, dict) and item.get("ticker"):
                t = item["ticker"]
                kind = item.get("type", "?")
                already = item.get("already_analyzed", False)
                tickers.append(f"{t}({kind}{', 重新分析' if already else ''})")

        if not tickers:
            return 0

        first = queue[0].get("ticker", "")
        head = (
            f"📥 Dashboard 待办队列里有 {len(tickers)} 只股票等待分析：{', '.join(tickers)}\n\n"
            f"行为指引：\n"
            f"1. 如果用户的当前消息明确指向其他任务（修代码、改 UI、问问题等），"
            f"请按用户消息处理，可以在回复末尾简短提醒一句「另外队列里有 N 只待办」。\n"
            f"2. 如果用户的消息是闲聊、确认（如「开干」「继续」「下一只」「好的」「ok」），"
            f"或没有明确其他任务，请按顺序处理队列——**第一只是 {first}**。\n"
            f"3. 每分析完一只，**必须**用 Edit 工具修改 `analyses/_queue.json`，"
            f"把对应条目从数组里移除。这样下次 hook 就不会再重复触发。\n"
            f"4. 队列里 type=CN 用 `分析 <6位代码>` 的流程（A 股管道）；type=US 用美股管道。\n"
            f"5. 严格按 CLAUDE.md 的第 1 层 → 用户确认能力圈 → 第 2 层流水线执行。"
            f"分析完第 1 层就停下来，**不要主动连跑第 2 层**——除非用户后续明确说「估值」或「进入第二层」。"
        )

        # Claude Code UserPromptSubmit hook：JSON 输出格式
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": head,
            }
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception:
        # 任何意外都安静退出，不阻塞用户
        return 0


if __name__ == "__main__":
    sys.exit(main())
