#!/usr/bin/env python3
"""Render the PULSE event-driven main loop as a system diagram.

Source: ~/Desktop/pulse算法.mindbridge.mmd (MindBridge export), redrawn with
the time-advance / joint-solve / commit steps that the original sketch omitted.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_architecture import (  # noqa: E402
    ARROW,
    BLUE,
    BORDER,
    INK,
    INK2,
    INK3,
    ORANGE,
    SLATE,
    TEAL,
    TINT,
    VIOLET,
    Canvas,
)

W, H = 1280, 1420
CX = 610
BW = 560


def block(c, x, y, w, h, title, sub=None, color=BLUE, badge=None):
    c.rect(x, y, w, h, TINT[color], BORDER[color], 1.2, 12)
    c.text(x + 20, y + 30, title, 15.0, "bold", INK)
    if sub:
        c.text(x + 20, y + 52, sub, 10.8, "reg", INK2)
    if badge:
        c.pill(x + w - 62, y + 12, 48, 19, badge, "#fff7ed", ORANGE, 9.0, "#fdba74")


def diamond(c, cx, cy, w, h, title, sub=None):
    pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    c.poly(pts, TINT[VIOLET], BORDER[VIOLET])
    c.text(cx, cy - 2, title, 13.5, "bold", INK, "ms")
    if sub:
        c.text(cx, cy + 17, sub, 9.6, "reg", INK3, "ms")


def main():
    c = Canvas(W, H)

    c.text(40, 54, "PULSE 事件驱动主循环 · 系统图", 28, "bold", INK)
    c.text(
        40,
        80,
        "按「pulse算法.mindbridge.mmd」重绘：保留原节点，补齐时间推进、联合求解、提交与终止",
        12.0,
        "reg",
        INK2,
    )
    for i, col in enumerate([BLUE, VIOLET, ORANGE, TEAL, SLATE]):
        c.rect(40 + i * 32, 96, 28, 3.4, col, None, 0, 1.7)

    left = CX - BW / 2

    # 1. start
    c.pill(CX - 190, 128, 380, 46, "初始模态 · 初始状态", TINT[TEAL], TEAL, 13.0, BORDER[TEAL], "bold")
    c.arrow(CX, 174, CX, 206)

    # 2-6 main spine
    y = 206
    block(c, left, y, BW, 82, "列出状态方程", "dx/dt = M_σ · x + c_σ     模态 σ 固定，矩阵 M_σ 来自当前模式")
    c.arrow(CX, y + 82, CX, y + 112)

    y = 318
    block(c, left, y, BW, 82, "计算模态器件的下一次事件时间", "连续守卫 g(x)=0 的首次根 · 定时项 deadline（PWM / AT / DELAY）")
    c.arrow(CX, y + 82, CX, y + 112)

    y = 430
    block(c, left, y, BW, 82, "取最近事件时间 t1", "t1 = min(守卫根, 定时项, T_END)")
    c.arrow(CX, y + 82, CX, y + 112)

    y = 542
    block(c, left, y, BW, 96, "候选状态推进到 t1", "x(t1) = exp(M_σ·Δt)·x(t0) + 特解；不修改已提交状态", ORANGE, "补充")
    c.arrow(CX, y + 96, CX, y + 126)

    y = 668
    block(c, left, y, BW, 96, "收集 t1 时刻的事件", "守卫穿越 + 到期定时项；T_atom 窗口内的事件只是候选", ORANGE, "修正")
    c.text(left + 20, y + 82, "T_atom 是工程接受窗口，不等于“精确同时”", 9.4, "reg", ORANGE)
    c.arrow(CX, y + 96, CX, y + 128)

    # 7. decision
    dy = 796
    diamond(c, CX, dy + 55, 300, 110, "有元件改变模态？", "按整体模式判定，不是逐元件")
    c.text(CX + 12, dy + 124, "是", 10.5, "bold", INK3)
    c.text(CX + 158, dy + 46, "否", 10.5, "bold", INK3)
    c.arrow(CX, dy + 110, CX, 930)

    # branch right: unchanged
    rx = 928
    c.rect(rx, dy + 15, 300, 80, "#f8fafc", "#e2e8f0", 1.2, 12)
    c.text(rx + 18, dy + 44, "未改变：保持当前模态", 13.0, "bold", INK)
    c.text(rx + 18, dy + 65, "模式不变，仍需推进时间并提交", 10.2, "reg", INK3)
    c.arrow(CX + 150, dy + 55, rx - 6, dy + 55)

    # 8. joint solve
    y = 930
    block(c, left, y, BW, 100, "联合求解新模态", "唯一稳定 + 代数相容 + 向前有效；多解/无解即 STOPPED_UNRESOLVED", ORANGE, "修正")
    c.arrow(CX, y + 100, CX, y + 130)

    # 9. commit
    y = 1060
    block(c, left, y, BW, 80, "提交候选状态", "RunState.version++ · 追加 segment 与 event_log", ORANGE, "补充")
    # merge unchanged branch into commit
    c.line(rx + 150, dy + 95, rx + 150, y + 40, "#94a3b8", 1.8)
    c.line(rx + 150, y + 40, left + BW + 4, y + 40, "#94a3b8", 1.8)
    c.arrow(left + BW + 22, y + 40, left + BW + 4, y + 40, "#94a3b8", 1.8, 8)

    c.arrow(CX, y + 80, CX, y + 110)

    # 10. end decision
    ey = 1170
    diamond(c, CX, ey + 55, 280, 110, "t1 ≥ T_END？")
    c.text(CX + 158, ey + 46, "是", 10.5, "bold", INK3)
    c.text(CX - 180, ey + 46, "否", 10.5, "bold", INK3)

    # end pill
    c.pill(rx + 10, ey + 29, 280, 52, "结束 · 输出 NPZ / 日志", TINT[TEAL], TEAL, 12.5, BORDER[TEAL], "bold")
    c.arrow(CX + 140, ey + 55, rx + 4, ey + 55)

    # loop back (left rail)
    c.line(CX - 140, ey + 55, 210, ey + 55, "#94a3b8", 1.8)
    c.line(210, ey + 55, 210, 247, "#94a3b8", 1.8)
    c.arrow(210, 247, left - 4, 247, "#94a3b8", 1.8, 8)
    c.pill(150, 640, 120, 26, "t ← t1", "#f8fafc", INK3, 10.5, "#e2e8f0")
    c.text(150, 690, "进入", 9.4, "reg", INK3)
    c.text(150, 704, "下一轮", 9.4, "reg", INK3)

    # side notes
    c.text(975, 1000, "注意", 10.5, "bold", ORANGE)
    c.text(975, 1018, "“不变”不是终点：", 9.6, "reg", INK3)
    c.text(975, 1034, "时间仍前进，", 9.6, "reg", INK3)
    c.text(975, 1050, "只是模态保持不变。", 9.6, "reg", INK3)

    # legend
    ly = 1290
    c.rect(40, ly, W - 80, 72, "#ffffff", "#e2e8f0", 1.2, 12)
    c.rect(58, ly + 18, 26, 18, TINT[BLUE], BORDER[BLUE], 1.0, 4)
    c.text(94, ly + 32, "原图节点", 10.2, "reg", INK2)
    c.rect(190, ly + 18, 26, 18, TINT[ORANGE], BORDER[ORANGE], 1.0, 4)
    c.text(226, ly + 32, "补充 / 修正节点", 10.2, "reg", INK2)
    c.rect(360, ly + 18, 26, 18, TINT[VIOLET], BORDER[VIOLET], 1.0, 4)
    c.text(396, ly + 32, "判定", 10.2, "reg", INK2)
    c.rect(470, ly + 18, 26, 18, TINT[TEAL], BORDER[TEAL], 1.0, 4)
    c.text(506, ly + 32, "起点 / 终点", 10.2, "reg", INK2)
    c.text(58, ly + 56, "关键约束：先取证后传播；候选整体提交或整体回滚；输出只观察已提交状态。", 9.8, "reg", INK3)

    c.save("pulse-algorithm-flow")


if __name__ == "__main__":
    main()
