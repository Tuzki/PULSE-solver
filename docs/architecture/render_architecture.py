#!/usr/bin/env python3
"""Render the PULSE Solver V1.1 architecture diagrams (SVG + PNG).

Source of truth: the current src/, include/ and CMakeLists.txt of this checkout.
Run:  python3 docs/architecture/render_architecture.py
"""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

S = 2  # supersampling factor for the PNG
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = {
    "reg": ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    "bold": ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
    "mono": ("/System/Library/Fonts/Menlo.ttc", 0),
}

# ---------------------------------------------------------------- palette
INK = "#0f172a"
INK2 = "#475569"
INK3 = "#64748b"
LINE = "#cbd5e1"
ARROW = "#94a3b8"
PANEL = "#ffffff"
BG = "#ffffff"

BLUE = "#2563eb"
VIOLET = "#6d28d9"
ORANGE = "#c2410c"
TEAL = "#0f766e"
SLATE = "#334155"

TINT = {
    BLUE: "#eff6ff",
    VIOLET: "#f5f3ff",
    ORANGE: "#fff7ed",
    TEAL: "#f0fdfa",
    SLATE: "#f8fafc",
}
BORDER = {
    BLUE: "#bfdbfe",
    VIOLET: "#ddd6fe",
    ORANGE: "#fed7aa",
    TEAL: "#99f6e4",
    SLATE: "#e2e8f0",
}

CJK_PUNCT = "，。、；：（）【】「」『』—…！？"


def is_cjk(ch: str) -> bool:
    return ord(ch) > 0x2E7F or ch in CJK_PUNCT


def units(text: str):
    """Split into wrappable units: CJK chars singly, latin words whole."""
    out, buf = [], ""
    for ch in text:
        if is_cjk(ch):
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        elif ch == " ":
            if buf:
                out.append(buf)
                buf = ""
            out.append(" ")
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), BG)
        self.d = ImageDraw.Draw(self.img)
        self.fonts = {}
        self.svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">',
            '<style>text{font-family:"Hiragino Sans GB","PingFang SC",sans-serif}'
            '.m{font-family:Menlo,monospace}</style>',
            f'<rect width="{w}" height="{h}" fill="{BG}"/>',
        ]
        self.overflow = []

    # ---------------------------------------------------------- text metrics
    def font(self, kind: str, size: float):
        kind = {"n": "reg", "m": "mono"}.get(kind, kind)
        key = (kind, size)
        if key not in self.fonts:
            path, idx = FONTS[kind]
            self.fonts[key] = ImageFont.truetype(path, int(round(size * S)), index=idx)
        return self.fonts[key]

    def measure(self, text: str, size: float, kind: str = "reg") -> float:
        return self.font(kind, size).getlength(text) / S

    def runs(self, s: str, kind: str):
        """Split mono text so CJK glyphs fall back to the CJK face."""
        if kind not in ("mono", "m"):
            return [(s, "reg" if kind == "n" else kind)]
        out, cur, ck = [], "", None
        for ch in s:
            k = "reg" if is_cjk(ch) else "mono"
            if cur and k != ck:
                out.append((cur, ck))
                cur = ""
            ck = k
            cur += ch
        if cur:
            out.append((cur, ck))
        return out or [(s, kind)]

    def measure_mixed(self, s: str, size: float, kind: str) -> float:
        return sum(self.measure(t, size, k) for t, k in self.runs(s, kind))

    def wrap(self, text: str, size: float, kind: str, maxw: float):
        lines, cur = [], ""
        for tok in units(text):
            trial = cur + tok
            if cur and self.measure_mixed(trial, size, kind) > maxw:
                if tok == " ":
                    lines.append(cur)
                    cur = ""
                    continue
                lines.append(cur.rstrip())
                cur = "" if tok == " " else tok
            else:
                cur = trial
        if cur.strip():
            lines.append(cur.rstrip())
        fixed = []
        for ln in lines or [""]:
            while self.measure_mixed(ln, size, kind) > maxw and len(ln) > 1:
                cut = len(ln)
                while cut > 1 and self.measure_mixed(ln[:cut], size, kind) > maxw:
                    cut -= 1
                fixed.append(ln[:cut])
                ln = ln[cut:]
            fixed.append(ln)
        return fixed

    # ------------------------------------------------------------- primitives
    def rect(self, x, y, w, h, fill, stroke=None, sw=1.0, r=0.0, opacity=1.0):
        if r:
            self.d.rounded_rectangle(
                [x * S, y * S, (x + w) * S, (y + h) * S],
                radius=r * S,
                fill=fill,
                outline=stroke,
                width=max(1, int(round(sw * S))) if stroke else 0,
            )
        else:
            self.d.rectangle(
                [x * S, y * S, (x + w) * S, (y + h) * S],
                fill=fill,
                outline=stroke,
                width=max(1, int(round(sw * S))) if stroke else 0,
            )
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"'
            + (f' stroke="{stroke}" stroke-width="{sw}"' if stroke else "")
            + (f' opacity="{opacity}"' if opacity != 1 else "")
            + "/>"
        )

    def _text_one(self, x, y, s, size, kind, color, anchor, opacity):
        if not s:
            return
        self.d.text((x * S, y * S), s, font=self.font(kind, size), fill=color, anchor=anchor)
        amap = {"ls": "start", "lm": "start", "ms": "middle", "mm": "middle", "rs": "end", "rm": "end"}
        self.svg.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'text-anchor="{amap.get(anchor, "start")}"'
            + (' class="m"' if kind == "mono" else "")
            + (f' opacity="{opacity}"' if opacity != 1 else "")
            + f' font-weight="{700 if kind == "bold" else 400}">{escape(s)}</text>'
        )

    def text(self, x, y, s, size=12, kind="reg", color=INK, anchor="ls", opacity=1.0):
        if not s:
            return
        runs = self.runs(s, kind)
        if len(runs) == 1:
            self._text_one(x, y, runs[0][0], size, runs[0][1], color, anchor, opacity)
            return
        total = sum(self.measure(t, size, k) for t, k in runs)
        if anchor in ("ms", "mm"):
            x -= total / 2
        elif anchor in ("rs", "rm"):
            x -= total
        for seg, k in runs:
            self._text_one(x, y, seg, size, k, color, "ls", opacity)
            x += self.measure(seg, size, k)

    def line(self, x1, y1, x2, y2, color=LINE, w=1.0, dash=None):
        if dash:
            import math

            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy)
            if dist:
                ux, uy = dx / dist, dy / dist
                pos = 0.0
                on, off = dash
                while pos < dist:
                    end = min(pos + on, dist)
                    self.d.line(
                        [(x1 + ux * pos) * S, (y1 + uy * pos) * S, (x1 + ux * end) * S, (y1 + uy * end) * S],
                        fill=color,
                        width=max(1, int(round(w * S))),
                    )
                    pos += on + off
            self.svg.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                f'stroke-width="{w}" stroke-dasharray="{dash[0]} {dash[1]}"/>'
            )
        else:
            self.d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=color, width=max(1, int(round(w * S))))
            self.svg.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"/>'
            )

    def poly(self, pts, fill, stroke=None):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill, outline=stroke)
        p = " ".join(f"{x},{y}" for x, y in pts)
        self.svg.append(
            f'<polygon points="{p}" fill="{fill}"' + (f' stroke="{stroke}"' if stroke else "") + "/>"
        )

    def arrow(self, x1, y1, x2, y2, color=ARROW, w=1.6, head=9):
        import math

        ang = math.atan2(y2 - y1, x2 - x1)
        bx, by = x2 - head * 0.9 * math.cos(ang), y2 - head * 0.9 * math.sin(ang)
        self.line(x1, y1, bx, by, color, w)
        pts = [
            (x2, y2),
            (x2 - head * math.cos(ang - 0.42), y2 - head * math.sin(ang - 0.42)),
            (x2 - head * math.cos(ang + 0.42), y2 - head * math.sin(ang + 0.42)),
        ]
        self.poly(pts, color)

    def pill(self, x, y, w, h, label, fill, color, size=10.5, stroke=None, kind="reg"):
        self.rect(x, y, w, h, fill, stroke, 1.0, h / 2)
        self.text(x + w / 2, y + h / 2 + size * 0.36, label, size, kind, color, "ms")

    # -------------------------------------------------------------- composites
    def band(self, x, y, w, h, color, fill=None):
        self.rect(x, y, w, h, fill or PANEL, BORDER[color], 1.2, 14)

    def section_label(self, x, y, num, title, sub, note, color, right=None):
        self.rect(x, y - 15, 21, 21, color, None, 0, 6)
        self.text(x + 10.5, y - 1, str(num), 11, "bold", "#ffffff", "ms")
        self.text(x + 30, y, title, 15, "bold", INK)
        tw = self.measure(title, 15, "bold")
        self.text(x + 30 + tw + 9, y, sub, 10.5, "reg", INK3)
        if note:
            self.text(right or (x + 1150), y, note, 9.6, "mono", INK3, "rs")

    def card(self, x, y, w, h, title, lines, color, title_size=13.0, body=11.0, pad=13.0):
        self.rect(x, y, w, h, TINT[color], BORDER[color], 1.0, 10)
        self.rect(x, y, 3.2, h, color, None, 0, 1.6)
        self.text(x + pad, y + 21, title, title_size, "bold", INK)
        size = body
        while True:
            lh = size * 1.42
            wrapped = []
            for kind, txt in lines:
                fs = size - 0.9 if kind == "m" else size
                for piece in self.wrap(txt, fs, kind, w - pad * 2 - 9):
                    wrapped.append((kind, fs, piece))
            need = 30 + len(wrapped) * lh
            if need <= h - 8 or size <= 8.8:
                break
            size -= 0.25
        yy = y + 40
        for kind, fs, piece in wrapped:
            self.d.ellipse(
                [(x + pad) * S, (yy - fs * 0.42) * S, (x + pad + 2.6) * S, (yy - fs * 0.42 + 2.6) * S],
                fill=color,
            )
            self.svg.append(
                f'<circle cx="{x + pad + 1.3}" cy="{yy - fs * 0.42 + 1.3}" r="1.3" fill="{color}"/>'
            )
            self.text(x + pad + 9, yy, piece, fs, kind, INK2 if kind != "m" else SLATE)
            yy += lh
        if yy > y + h + 1:
            self.overflow.append((title, round(yy - (y + h), 1)))

    def panel_title(self, x, y, w, title, sub, color):
        self.text(x, y, title, 13.0, "bold", color)
        tw = self.measure(title, 13.0, "bold")
        self.text(x + tw + 8, y, sub, 9.8, "mono", INK3)

    def save(self, stem):
        self.svg.append("</svg>")
        with open(os.path.join(HERE, stem + ".svg"), "w", encoding="utf-8") as f:
            f.write("\n".join(self.svg))
        self.img.save(os.path.join(HERE, stem + ".png"), "PNG", optimize=True)
        print(f"{stem}.svg / {stem}.png  {self.w}x{self.h}  overflow={self.overflow}")


# =====================================================================
# Diagram 1 — system architecture
# =====================================================================
def architecture():
    W, H = 1720, 1460
    c = Canvas(W, H)

    # header ------------------------------------------------------------
    c.text(40, 52, "PULSE Solver V1.1 · 系统架构", 29, "bold", INK)
    c.text(
        40,
        79,
        "C++20 电域/数域联合 PWA 事件驱动仿真器 — 按当前 src/ · include/ · CMakeLists.txt 实读（2026-10-21）",
        12.5,
        "reg",
        INK2,
    )
    c.text(W - 40, 44, "≈8.4k 行 C++ · 26 个源文件", 10.5, "mono", INK3, "rs")
    c.text(W - 40, 64, "ABI v2 · 13 原语 · C++20", 10.5, "mono", INK3, "rs")
    for i, col in enumerate([BLUE, VIOLET, ORANGE, TEAL, SLATE]):
        c.rect(40 + i * 32, 94, 28, 3.4, col, None, 0, 1.7)

    MX, MW = 40, 1150            # main column (bands 1-3)
    FW = W - 80                  # full width (band 4 + contracts)
    RX, RW = 1290, 390           # kernel column
    BW = (MW - 48 - 3 * 18) / 4  # card width in a 4-up row
    BW4 = (FW - 48 - 3 * 18) / 4

    # ---- band 1: interfaces
    y = 118
    c.section_label(MX, y + 14, 1, "接口层", "Interfaces", "apps/cli.cpp · src/abi.cpp · include/pulse/pulse.h", BLUE)
    c.band(MX, y + 26, MW, 148, BLUE)
    by = y + 44
    cards1 = [
        ("CLI pulse-solver", [("m", "apps/cli.cpp · 75 行"), ("n", "MODEL.md [--t-end] [--save-dt]"), ("n", "--channels · --atom-exponent · --ir"), ("n", "退出码 0 成功 / 1 错误 / 2 未决")]),
        ("C ABI · libpulse_solver", [("m", "src/abi.cpp · include/pulse/pulse.h"), ("n", "pulse_compile_markdown / pulse_simulate"), ("n", "ABI v2，保留 ABI1 符号与错误码"), ("n", "句柄持有 model · error · report")]),
        ("进程内 C++ API", [("m", "include/pulse/core.hpp"), ("n", "compile(Netlist) → Model"), ("n", "simulate(Model, Options) → Result"), ("n", "write_result(Model, Result, dir)")]),
        ("独立测试壳", [("m", "tests/*.py · ctypes + NumPy"), ("n", "interface_oracle / npz_oracle"), ("n", "pewave_v1_oracle / regression"), ("n", "仅测试用，不是运行时依赖")]),
    ]
    for i, (t, ls) in enumerate(cards1):
        c.card(MX + 24 + i * (BW + 18), by, BW, 108, t, ls, BLUE)

    # ---- arrow
    ax = MX + MW / 2
    c.arrow(ax, y + 174, ax, y + 208)
    c.pill(ax + 14, y + 176, 196, 19, "*.md 文本 + Options", "#f8fafc", INK3, 9.8, "#e2e8f0")

    # ---- band 2: front-end
    y = 344
    c.section_label(MX, y + 14, 2, "编译层", "Front-end · compile time", "纯函数式 IR 构建，不推进时间", VIOLET)
    c.band(MX, y + 26, MW, 240, VIOLET)
    by = y + 42
    cards2 = [
        ("Markdown 网表 *.md", [("n", "四区块：Parameters / Network"), ("n", "Simulation / Layout"), ("n", ".PARAM 冻结表达式 · 单位后缀"), ("n", ".SUBCKT / X 实例 · .SAVE")]),
        ("词法 · 语法 · 展开", [("m", "src/netlist.cpp · 754 行"), ("n", "最长原语前缀识别（SW ≠ SENSOR）"), ("n", "冻结参数求值 · 续行 · 注释"), ("n", "SUBCKT 展开（禁递归）· SourceMap"), ("n", "canonical Netlist IR")]),
        ("类型 · 语义 · 本构", [("m", "src/semantics.cpp · 789 行"), ("n", "13 原语参数 / 端口结构校验"), ("n", "REAL · BOOL · TRIG 推断与单驱动"), ("n", "仿射折叠 → CONTINUOUS_NONAFFINE"), ("n", "PWA 表 · L_MATRIX · Q-V / Φ-I")]),
        ("Model 编译", [("m", "src/descriptor.cpp · 755 行"), ("n", "Descriptor/MNA 装配 + 秩分解消元"), ("n", "CMP×PWA 枚举 ≤ 4096 → 唯一稳定模式"), ("n", "输出 M、观测/约束映射、Guard 行"), ("n", "settle() / compile_specified()")]),
    ]
    for i, (t, ls) in enumerate(cards2):
        c.card(MX + 24 + i * (BW + 18), by, BW, 158, t, ls, VIOLET)
    for i in range(3):
        x1 = MX + 24 + i * (BW + 18) + BW
        c.arrow(x1 + 3, by + 79, x1 + 16, by + 79, "#a78bfa", 1.4, 6)
    c.text(MX + 24, y + 222, "同一 Netlist 的 canonical 文本与 Model 均以稳定 ID 排序；模式数组顺序不依赖哈希表或 Markdown 书写顺序。", 9.6, "reg", INK3)

    # ---- arrow (Model)
    c.arrow(ax, y + 266, ax, y + 300)
    c.pill(ax + 14, y + 270, 246, 19, "Model：parts · signals · maps · initial", "#f8fafc", INK3, 9.4, "#e2e8f0")

    # ---- band 3: runtime
    y = 648
    c.section_label(MX, y + 14, 3, "运行时", "Runtime · 唯一提交点", "src/runtime.cpp · 1,388 行", ORANGE)
    c.rect(MX, y + 26, MW, 272, "#fffbf7", "#fdba74", 1.2, 14)
    by = y + 42
    cards3 = [
        ("① 选取目标时刻", [("n", "target = min(最近定时项, T_END)"), ("n", "只读已提交 RunState 取证"), ("n", "T_atom = effective_SAVE_DT · 10^-N"), ("n", "根区间不得越过独立 deadline")]),
        ("② 首次根与接受", [("n", "区间证书 [l,u] + 方向 + 首次性"), ("n", "EXACT_REPRESENTABLE_ROOT"), ("n", "ENGINEERING_DELAYED_SWITCH / CLUSTER"), ("n", "validated::switch_bridge 桥接"), ("n", "无法证明 → STOPPED_UNRESOLVED")]),
        ("③ (t,δ) 同刻闭包", [("n", "TRIG 批 → REG 原子写回"), ("n", "EVENT: PERIODIC / AT / EDGE / DELAY"), ("n", "TRANSPORT · REPLACE · CANCEL"), ("n", "settle() 新模式 → δ+1 净边沿"), ("n", "ZERO_TIME_CYCLE / MICROSTEP_BUDGET")]),
        ("④ 原子提交 / 回滚", [("n", "全部检查通过才 ++version 提交"), ("n", "失败丢弃 agenda / 缓存 / 输出暂存"), ("n", "事务预算 TRANSACTION_BUDGET"), ("n", "已提交前缀永不被污染")]),
    ]
    for i, (t, ls) in enumerate(cards3):
        c.card(MX + 24 + i * (BW + 18), by, BW, 176, t, ls, ORANGE, body=10.8)
    for i in range(3):
        x1 = MX + 24 + i * (BW + 18) + BW
        c.arrow(x1 + 3, by + 88, x1 + 16, by + 88, "#fb923c", 1.4, 6)
    c.rect(MX + 24, y + 228, MW - 48, 52, "#ffedd5", "#fdba74", 1.0, 8)
    c.text(MX + 38, y + 250, "RunState", 10.8, "bold", ORANGE)
    c.text(MX + 104, y + 250, "= Time(at, origin) · physical [q_C, φ_L, η_INT] · Mode · regs · agenda · generations · version", 10.6, "reg", INK2)
    c.text(MX + 38, y + 269, "换模只重建局部坐标：reconstruct_old → preserve physical → validate new constraints → reduce_new", 9.4, "reg", INK3)

    # ---- arrow (Result)
    c.arrow(ax, y + 298, ax, y + 332)
    c.pill(ax + 14, y + 302, 288, 19, "Result：segments · events · stats · report", "#f8fafc", INK3, 9.4, "#e2e8f0")

    # ---- band 4: output
    y = 984
    c.section_label(MX, y + 14, 4, "输出与证据", "Output · observe committed state", "只重建已提交前缀", SLATE, MX + FW)
    c.band(MX, y + 26, FW, 158, SLATE)
    by = y + 44
    cards4 = [
        ("轨迹重建", [("m", "runtime.cpp :: reconstruct()"), ("n", "SAVE 网格 + 唯一终点"), ("n", "只写已提交前缀，验证读值可选")]),
        ("观测与元数据", [("m", "src/output.cpp · 170 行"), ("n", "registry → analog f4 / digital u8"), ("n", "单位 · 轴向 · dtype · 事件计数")]),
        ("NPZ 写入", [("m", "src/npz.cpp · 197 行"), ("n", "原生 ZIP32 + NPY v1.0"), ("n", "无 zlib 依赖 · UTF-8 metadata_json")]),
        ("运行产物", [("m", "out/ 目录"), ("n", "out.pewave.npz"), ("n", "event_log.jsonl · simulation_report.json / .md")]),
    ]
    for i, (t, ls) in enumerate(cards4):
        c.card(MX + 24 + i * (BW4 + 18), by, BW4, 118, t, ls, SLATE)

    # ---- kernel column (spans interfaces -> runtime)
    c.panel_title(RX, 132, RW, "数值与证书内核", "runtime 按需调用", TEAL)
    c.rect(RX, 144, RW, 788, "#f8fefd", "#b7e4dd", 1.2, 14)
    kernels = [
        ("首次根隔离 first_root/", [("m", "rfr::detect + fri::find_first_event"), ("n", "outward 区间算术 · Taylor / Bernstein"), ("n", "CA 变换 + 符号变差隔离"), ("n", "→ bracket · 方向 · 首次性证书")]),
        ("无事件证明 cegs.cpp", [("m", "src/cegs.cpp · 470 行"), ("n", "Eigen / Schur / Taylor 分块对角化"), ("n", "缺陷界 + 块指数 → 守卫不穿越"), ("n", "刚性长步的快速通道")]),
        ("验证流 certified_flow.cpp", [("m", "src/certified_flow.cpp · 1,376 行"), ("n", "384-bit 二进制定点区间算术"), ("n", "有理基 · 约束半空间包络"), ("n", "advance · guard · readout · bridge")]),
        ("时间与来源", [("m", "common.cpp · time_origin.cpp"), ("n", "T128：whole + 2^-64 + 2^-128"), ("n", "十进制来源精确加 / 乘 / 比较"), ("n", "AT · PERIOD · DELAY 折叠与顺序检查")]),
        ("模态传播 propagate.cpp", [("m", "src/propagate.cpp · 80 行"), ("n", "exp(M·h) 增广矩阵指数"), ("n", "约束 / 残差预算检查"), ("n", "有界 SVD 投影（仅舍入级）")]),
    ]
    ky = 160
    for t, ls in kernels:
        c.card(RX + 16, ky, RW - 32, 144, t, ls, TEAL, title_size=12.4, body=10.4)
        ky += 156
    # connector runtime <-> kernels
    c.line(MX + MW + 4, 800, RX - 6, 800, "#5eead4", 1.6, (5, 4))
    c.arrow(RX - 6, 800, MX + MW + 6, 800, "#14b8a6", 1.2, 7)
    c.arrow(MX + MW + 6, 812, RX - 6, 812, "#14b8a6", 1.2, 7)

    # ---- cross-cutting strip
    y = 1192
    c.text(MX, y, "横切契约", 13.0, "bold", INK)
    c.text(MX + 64, y, "Cross-cutting contracts", 9.8, "mono", INK3)
    c.rect(MX, y + 14, FW, 208, "#ffffff", "#e2e8f0", 1.2, 14)
    cols = [
        ("运行状态", "COMPLETED / STOPPED_ERROR /\nSTOPPED_UNRESOLVED", "安全停止不得报成完成"),
        ("证据等级", "LOCAL_CERTIFIED / NUMERICAL /\nENGINEERING_APPROXIMATION", "NOT_CERTIFIED 表示未认证"),
        ("时间契约", "Q_repr = 2^-64 s · T128\nT_atom = SAVE_DT · 10^-N", "显示时间不参与事件排序"),
        ("可追溯", "CMake 计算 source_sha256\nmodel_version 逐次写入 report", "无根运行同样可追溯"),
        ("构建与验证", "C++20 · CMake ≥ 3.24 · Eigen 3.4.0\nBoost 1.86 · 10 个 CTest 入口", "Python 仅为独立测试壳"),
    ]
    cw = (FW - 40 - 4 * 16) / 5
    for i, (t, body, note) in enumerate(cols):
        x = MX + 20 + i * (cw + 16)
        c.text(x, y + 44, t, 11.5, "bold", INK)
        c.line(x, y + 54, x + cw - 6, y + 54, "#e2e8f0", 1.0)
        for j, part in enumerate(body.split("\n")):
            c.text(x, y + 74 + j * 15, part, 9.6, "mono", SLATE)
        c.text(x, y + 74 + len(body.split("\n")) * 15 + 6, note, 9.3, "reg", INK3)
    c.text(MX + 20, y + 190, "依赖方向：Parser 不调用 Solver · Compiler 不推进时间 · 根搜索只返回证据 · 矩阵传播不改 EVENT · Runtime 唯一提交 · Recorder 只观察。", 9.8, "reg", INK3)

    c.save("pulse-v1.1-architecture")


# =====================================================================
# Diagram 2 — one physical transaction
# =====================================================================
def transaction_flow():
    W, H = 1520, 930
    c = Canvas(W, H)

    c.text(40, 54, "单次物理事务：候选 → 验证 → 原子提交", 27, "bold", INK)
    c.text(
        40,
        80,
        "runtime.cpp::simulate() 主循环 —— 时间推进、事件定位与 (t,δ) 闭包在一次事务内完成，失败则整体回滚",
        12.0,
        "reg",
        INK2,
    )
    c.text(W - 40, 46, "S_k ──▶ S_k+1", 11, "mono", ORANGE, "rs")
    c.text(W - 40, 66, "committed prefix only", 9.5, "mono", INK3, "rs")
    for i, col in enumerate([BLUE, VIOLET, ORANGE, TEAL, SLATE]):
        c.rect(40 + i * 32, 94, 28, 3.4, col, None, 0, 1.7)

    CX, CW = 250, 620
    stages = [
        ("① 选取目标时刻", [("n", "t* = min(下一定时项 deadline, T_END)"), ("n", "只读已提交 S_k；不修改任何状态")]),
        ("② 事件取证（三选一）", [("n", "A 已验证链：validated::prepare → first_event"), ("n", "B 大范数长步：cegs::no_event（证明无事件）"), ("n", "C 常规：fri::find_first_event → [l,u] + 证书")]),
        ("③ 构造候选并推进", [("n", "S′ = S_k 深拷贝（时间 / 物理 / mode / regs / agenda）"), ("n", "propagate 或 validated::advance 到 Ta ≤ l + T_atom"), ("n", "应用新模态；q / φ / η 连续保持")]),
        ("④ (t,δ) 同刻闭包", [("n", "δ 批次：TRIG 快照 → REG 原子写回 → 延时入队"), ("n", "settle() 求唯一稳定模式；δ+1 生成净边沿")]),
        ("⑤ 接受义务", [("n", "algebraic_consistent · mode_consistent · forward_admissible"), ("n", "守卫越界 ≤ T_atom · 无第二事件 · 局部误差界")]),
        ("⑥ 原子提交", [("n", "S_k+1 = S′；++version；追加 segment 与 event_log"), ("n", "证据等级随事务写入 simulation_report")]),
    ]
    sy = 120
    for i, (t, ls) in enumerate(stages):
        c.card(CX, sy, CW, 92, t, ls, ORANGE, title_size=13.2, body=10.6, pad=16)
        if i < len(stages) - 1:
            c.arrow(CX + CW / 2, sy + 92, CX + CW / 2, sy + 118, "#fb923c", 1.6, 7)
        sy += 118

    # left gutter state pills
    c.pill(46, 150, 150, 24, "S_k 已提交", "#fff7ed", ORANGE, 10.2, "#fdba74")
    c.pill(46, 380, 150, 24, "候选 S′（可变）", "#f8fafc", SLATE, 10.0, "#e2e8f0")
    c.pill(46, 730, 150, 24, "S_k+1 已提交", "#fff7ed", ORANGE, 10.2, "#fdba74")

    c.text(46, 226, "只读取证", 9.4, "reg", INK3)
    c.text(46, 240, "证据不足即停止", 9.4, "reg", INK3)
    c.text(46, 496, "不触碰已提交", 9.4, "reg", INK3)
    c.text(46, 510, "失败整体丢弃", 9.4, "reg", INK3)

    # right lane
    RX, RW = 940, 540
    c.card(
        RX,
        120,
        RW,
        180,
        "失败出口：整笔事务回滚",
        [
            ("n", "候选整体丢弃：agenda、模式缓存、输出暂存"),
            ("n", "STOPPED_UNRESOLVED：时间 / 根 / 模式证据不足"),
            ("n", "STOPPED_ERROR：模型、数值或输出错误"),
            ("n", "已提交前缀、event_log 与采样保持完整"),
            ("n", "rollbacks += 1，诊断带 SourceMap 定位"),
        ],
        VIOLET,
        title_size=13.0,
        body=10.9,
    )
    c.card(
        RX,
        320,
        RW,
        160,
        "四个不变量",
        [
            ("n", "先取证、后传播：永不先改已提交状态"),
            ("n", "根区间 [l,u] 不等于物理真值，Ta 才是接受时刻"),
            ("n", "δ 不推进物理时间，只表示同刻逻辑微步骤"),
            ("n", "输出只能观察已提交状态，不能读脏候选"),
        ],
        TEAL,
        title_size=13.0,
        body=10.9,
    )
    c.card(
        RX,
        500,
        RW,
        140,
        "每笔事务写入 event_log",
        [
            ("n", "time_canonical（T128）· time_seconds_display · delta"),
            ("n", "root_interval · before/after mode · policy"),
            ("n", "证书范围 · 局部误差界 · transaction_id"),
        ],
        SLATE,
        title_size=12.8,
        body=10.6,
    )
    c.card(
        RX,
        660,
        RW,
        142,
        "证据等级随事务记录",
        [
            ("n", "LOCAL_CERTIFIED：局部根 / 桥接证书"),
            ("n", "NUMERICAL：仅数值，无证书"),
            ("n", "ENGINEERING_APPROXIMATION：T_atom 近似"),
            ("n", "NOT_CERTIFIED：拒绝或未决"),
        ],
        BLUE,
        title_size=12.8,
        body=10.6,
    )

    # bottom stop conditions
    c.rect(40, 810, W - 80, 84, "#f8fafc", "#e2e8f0", 1.2, 12)
    c.text(58, 838, "安全停止条件（全部为显式诊断，不静默修正网表）", 11.0, "bold", INK)
    stops = [
        "TIME_ORDER_UNRESOLVED",
        "ACCEPTANCE_WINDOW_EXCEEDED",
        "NO_FORWARD_ADMISSIBLE_MODE",
        "INCONSISTENT_MODE_TRANSITION",
        "MICROSTEP_BUDGET",
        "ZERO_TIME_CYCLE",
        "EVENT_ROOT_UNRESOLVED",
        "TRANSACTION_BUDGET",
    ]
    x = 58
    for s in stops:
        w = c.measure(s, 9.2, "mono") + 18
        c.pill(x, 854, w, 22, s, "#ffffff", INK2, 9.2, "#e2e8f0", "mono")
        x += w + 8

    c.save("pulse-v1.1-transaction-flow")


if __name__ == "__main__":
    architecture()
    transaction_flow()
