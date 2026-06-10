#!/usr/bin/env python3
"""make_icon.py —— 用 macOS 自带 Core Graphics 绘制应用图标（背景真透明）。

为什么不用 qlmanage 渲 SVG：qlmanage 会把 SVG 的透明区域刷成白色，
导致图标四角是白底、很难看。这里直接用 Quartz 画，alpha 完全可控。

产物（写到 assets/）：
  icon.png   1024×1024 透明背景
  icon.icns  多尺寸 macOS 图标

设计：金色圆角方块（macOS 大圆角 squircle 比例）+ 三根深色 K 线柱 + 淡上行趋势线，无文字。
"""

import math
from pathlib import Path

import Quartz
from Quartz import (
    CGColorSpaceCreateDeviceRGB,
    CGBitmapContextCreate,
    CGContextSetRGBFillColor,
    CGContextSetRGBStrokeColor,
    CGContextSetLineWidth,
    CGContextSetLineCap,
    CGContextMoveToPoint,
    CGContextAddLineToPoint,
    CGContextStrokePath,
    CGContextSetAlpha,
    CGBitmapContextCreateImage,
    kCGImageAlphaPremultipliedLast,
    kCGLineCapRound,
    CGContextDrawLinearGradient,
    CGGradientCreateWithColorComponents,
    CGContextSaveGState,
    CGContextRestoreGState,
    CGContextClip,
    CGContextAddPath,
    CGContextBeginPath,
    CGPathCreateMutable,
    CGPathAddRoundedRect,
    CGContextFillPath,
    kCGGradientDrawsBeforeStartLocation,
    kCGGradientDrawsAfterEndLocation,
    CGRectMake,
)
from AppKit import (
    NSBitmapImageRep,
    NSPNGFileType,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
N = 1024  # 画布边长


def rounded_rect_path(x, y, w, h, r):
    p = CGPathCreateMutable()
    CGPathAddRoundedRect(p, None, CGRectMake(x, y, w, h), r, r)
    return p


def make_png():
    cs = CGColorSpaceCreateDeviceRGB()
    ctx = CGBitmapContextCreate(None, N, N, 8, 0, cs, kCGImageAlphaPremultipliedLast)
    # 背景透明：什么都不画即可（context 初始全透明）

    # —— 金色圆角方块底座（留 ~9% 透明边距，macOS 风格） ——
    margin = int(N * 0.092)            # ~94
    side = N - 2 * margin              # ~836
    radius = side * 0.2237             # Big Sur squircle 比例
    base = rounded_rect_path(margin, margin, side, side, radius)

    CGContextSaveGState(ctx)
    CGContextAddPath(ctx, base)
    CGContextClip(ctx)
    # 金色对角渐变：#F0C04A（左上） → #D89A2E（右下），用 NSGradient 避免 components 数组歧义
    from AppKit import NSGradient, NSColor, NSGraphicsContext
    nsctx = NSGraphicsContext.graphicsContextWithCGContext_flipped_(ctx, False)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(nsctx)
    top = NSColor.colorWithSRGBRed_green_blue_alpha_(0xF0/255, 0xC0/255, 0x4A/255, 1.0)
    bot = NSColor.colorWithSRGBRed_green_blue_alpha_(0xD8/255, 0x9A/255, 0x2E/255, 1.0)
    grad = NSGradient.alloc().initWithStartingColor_endingColor_(top, bot)
    # 角度 -45°：左上 → 右下
    grad.drawInRect_angle_(CGRectMake(margin, margin, side, side), -45.0)
    NSGraphicsContext.restoreGraphicsState()
    CGContextRestoreGState(ctx)

    # —— 坐标换算：设计基于内部方块（margin..N-margin） ——
    def fx(fr):  # 水平方向，fr 是相对内部方块的比例
        return margin + fr * side

    def fy_top(fr):  # 注意 Core Graphics 原点在左下，设计里 y 从上往下
        return (N - margin) - fr * side

    DARK = (0x1A / 255, 0x12 / 255, 0x05 / 255)

    # 三根 K 线中心（相对内部方块的水平比例）
    centers = [0.2857, 0.5, 0.7143]
    wick_w = side * 0.058
    # 影线上下端（相对比例，0=顶 1=底）
    wick = [(0.196, 0.804), (0.196, 0.804), (0.196, 0.804)]
    # 实体 (顶比例, 底比例, 宽比例)
    bodies = [(0.531, 0.745, 0.152),
              (0.353, 0.617, 0.152),
              (0.241, 0.473, 0.152)]

    # 影线
    CGContextSetRGBStrokeColor(ctx, DARK[0], DARK[1], DARK[2], 1.0)
    CGContextSetLineWidth(ctx, wick_w)
    CGContextSetLineCap(ctx, kCGLineCapRound)
    for c, (t, b) in zip(centers, wick):
        CGContextMoveToPoint(ctx, fx(c), fy_top(t))
        CGContextAddLineToPoint(ctx, fx(c), fy_top(b))
        CGContextStrokePath(ctx)

    # 实体（深色圆角矩形）
    CGContextSetRGBFillColor(ctx, DARK[0], DARK[1], DARK[2], 1.0)
    for c, (t, b, wfr) in zip(centers, bodies):
        bw = side * wfr
        top = fy_top(t)
        bot = fy_top(b)
        h = top - bot
        path = rounded_rect_path(fx(c) - bw / 2, bot, bw, h, bw * 0.32)
        CGContextBeginPath(ctx)
        CGContextAddPath(ctx, path)
        CGContextFillPath(ctx)

    # 淡上行趋势线
    pts = [(0.10, 0.66), (0.357, 0.535), (0.61, 0.40), (0.88, 0.27)]
    CGContextSaveGState(ctx)
    CGContextSetAlpha(ctx, 0.34)
    CGContextSetRGBStrokeColor(ctx, DARK[0], DARK[1], DARK[2], 1.0)
    CGContextSetLineWidth(ctx, side * 0.062)
    CGContextSetLineCap(ctx, kCGLineCapRound)
    CGContextMoveToPoint(ctx, fx(pts[0][0]), fy_top(pts[0][1]))
    for px, py in pts[1:]:
        CGContextAddLineToPoint(ctx, fx(px), fy_top(py))
    CGContextStrokePath(ctx)
    CGContextRestoreGState(ctx)

    img = CGBitmapContextCreateImage(ctx)
    rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
    data = rep.representationUsingType_properties_(NSPNGFileType, None)
    out = ASSETS / "icon.png"
    data.writeToFile_atomically_(str(out), True)
    print("wrote", out)
    return out


if __name__ == "__main__":
    make_png()
