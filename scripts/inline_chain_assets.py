#!/usr/bin/env python3
"""
inline_chain_assets.py —— 把 chains/_shared/ 的共享 CSS/JS 内联进每个产业链页面。

为什么：用户用 Safari 通过 file:// 打开页面，Safari 的 file:// 安全策略会拦掉
从父目录（../_shared/）加载的 CSS/JS，导致整页没样式。第一阶段的交互器页之所以
能在 file:// 下正常，就是因为它们全自包含（CSS/JS 都内联）。所以这里把共享文件
烤进每个页面，让页面自包含、file:// 下必定能开。

工作流：chains/_shared/chain_ui.css + glossary.js 是唯一可编辑的源；改完它们后
重跑本脚本，会把每个页面里带标记的内联块刷新成最新内容（首次运行则把 <link>/
<script src="../_shared/..."> 标签替换成内联块）。

用法：python scripts/inline_chain_assets.py
"""
import re
from pathlib import Path


def main():
    shared = Path("chains/_shared")
    css = (shared / "chain_ui.css").read_text(encoding="utf-8")
    js = (shared / "glossary.js").read_text(encoding="utf-8")

    # 转义掉可能提前闭合标签的串（如注释里写到的 </script>），保证内联安全
    css = css.replace("</style", "<\\/style")
    js = js.replace("</script", "<\\/script")

    css_block = '<style id="chain-ui">\n' + css + '\n</style>'
    js_block = '<script id="glossary">\n' + js + '\n</script>'

    pages = sorted(p for p in Path("chains").glob("*/*.html"))
    changed = 0
    for p in pages:
        html = p.read_text(encoding="utf-8")
        orig = html

        # CSS：已内联则刷新内联块，否则替换 <link ... chain_ui.css ...>
        if '<style id="chain-ui">' in html:
            html = re.sub(r'<style id="chain-ui">.*?</style>', lambda m: css_block, html, flags=re.DOTALL)
        else:
            html = re.sub(r'<link[^>]*chain_ui\.css[^>]*>', lambda m: css_block, html, count=1)

        # JS：已内联则刷新内联块，否则替换 <script src="...glossary.js"></script>
        if '<script id="glossary">' in html:
            html = re.sub(r'<script id="glossary">.*?</script>', lambda m: js_block, html, flags=re.DOTALL)
        else:
            html = re.sub(r'<script src="[^"]*glossary\.js"></script>', lambda m: js_block, html, count=1)

        if html != orig:
            p.write_text(html, encoding="utf-8")
            changed += 1
            print(f"已内联：{p}")

    print(f"\n完成：处理 {len(pages)} 个页面，更新 {changed} 个。页面现已自包含、file:// 下可直接打开。")


if __name__ == "__main__":
    main()
