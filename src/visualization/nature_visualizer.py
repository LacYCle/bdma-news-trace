"""Nature-Figure 出版物级可视化

基于 matplotlib 的 SCI 期刊风格静态图表，遵循 nature-figure skill 规范：
图合约 → 原型分类 → 面板映射 → SVG/PDF/PNG 导出。

替代原有的 Plotly 交互式可视化，输出可直接用于论文发表。

依赖:
  matplotlib, networkx, numpy
"""

import os
import numpy as np
import networkx as nx
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from collections import Counter

# ═══════════════════════════════════════════════════════════════
# PALETTE — nature-figure 标准色板 (api.md)
# ═══════════════════════════════════════════════════════════════
PALETTE = {
    "blue_main":      "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "red_1":   "#F6CFCB",
    "red_2":   "#E9A6A1",
    "red_strong": "#B64342",
    "neutral_light": "#CFCECE",
    "neutral_mid":   "#767676",
    "neutral_dark":  "#4D4D4D",
    "neutral_black": "#272727",
    "gold":   "#FFD700",
    "teal":   "#42949E",
    "violet": "#9A4D8E",
    "magenta":"#EA84DD",
}

# 平台配色 — 高对比度
PLATFORM_COLORS = {
    "weibo":   "#0F4D92",  # navy blue
    "sina":    "#E28E2C",  # amber
    "netease": "#42949E",  # teal
    "zhihu":   "#9A4D8E",  # violet
}

# 情感配色
POLARITY_COLOR = "#B64342"  # red_strong
AROUSAL_COLOR  = "#0F4D92"  # blue_main

# ═══════════════════════════════════════════════════════════════
# Publication Style — 一次性设置
# ═══════════════════════════════════════════════════════════════
_CJK_FONT = "Microsoft YaHei"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [_CJK_FONT, "SimHei", "Arial", "DejaVu Sans", "Liberation Sans"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 7,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
    "axes.titlesize": 8,
    "axes.labelsize": 7,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6,
})


class NatureVisualizer:
    """出版物级可视化 — nature-figure 风格, matplotlib 后端"""

    def __init__(self, output_dir: str = "data/figures"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # ── Public API (matches old PropagationVisualizer) ─────────

    def generate_all(self, pg, trace_result: list[dict],
                     sentiment_result: dict, save: bool = True) -> dict[str, str]:
        """一键生成全部图表 → 返回 {name: filepath} 字典"""
        figures = {}
        event_id = pg.event_id[:16] if pg.event_id else "unknown"

        # Build 2×2 composite figure
        fig = plt.figure(figsize=(7.2, 6.5))
        gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.28,
                              height_ratios=[1.0, 0.85])
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        source_id = trace_result[0]["post_id"] if trace_result else None

        self._draw_propagation_graph(ax_a, pg, highlight_id=source_id)
        self._draw_sentiment_evolution(ax_b,
            sentiment_result.get("evolution", []),
            sentiment_result.get("turning_points", []))
        self._draw_source_confidence(ax_c, trace_result)
        self._draw_cross_platform(ax_d,
            sentiment_result.get("cross_platform", {}))

        # Panel labels
        self._add_label(ax_a, "a")
        self._add_label(ax_b, "b")
        self._add_label(ax_c, "c")
        self._add_label(ax_d, "d")

        # Suptitle
        fig.suptitle(f'Event propagation trace',
                     fontsize=9, fontweight="bold", x=0.02, y=0.99, ha="left")

        if save:
            path = self._save(fig, f"propagation_trace_{event_id}")
            figures["propagation_trace"] = path

        plt.close(fig)
        return figures

    # ── Panel Draw Methods ─────────────────────────────────────

    def _draw_propagation_graph(self, ax, pg, highlight_id=None):
        """Panel a: 力导向传播图"""
        G = pg.graph
        if G.number_of_nodes() == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color=PALETTE["neutral_mid"])
            return

        pos = nx.spring_layout(G, k=2.5, iterations=60, seed=42)

        # Edges by type
        edge_buckets = {"repost": [], "cite": [], "cross_platform": [], "image_match": []}
        for u, v, data in G.edges(data=True):
            etype = data.get("type", "cite")
            if etype in edge_buckets:
                edge_buckets[etype].append((u, v))

        edge_style = {
            "repost":         (PALETTE["blue_main"], 0.75, 0.8, "-"),
            "cite":           (PALETTE["neutral_dark"], 0.65, 0.7, "--"),
            "cross_platform": (PALETTE["red_strong"], 0.75, 1.2, "-"),
            "image_match":    (PALETTE["teal"], 0.6, 0.9, ":"),
        }

        for etype, edges in edge_buckets.items():
            if not edges:
                continue
            color, alpha, lw, ls = edge_style[etype]
            for u, v in edges:
                x0, y0 = pos[u]; x1, y1 = pos[v]
                ax.plot([x0, x1], [y0, y1], color=color, alpha=alpha,
                        linewidth=lw, linestyle=ls, zorder=1)

        # Nodes by platform
        for plat, color in PLATFORM_COLORS.items():
            nodes = [n for n in G.nodes() if G.nodes[n].get("platform") == plat]
            if not nodes:
                continue
            xs = [pos[n][0] for n in nodes]
            ys = [pos[n][1] for n in nodes]
            sizes = []
            for n in nodes:
                eng = G.nodes[n].get("engagement", 0) or 0
                is_root = G.in_degree(n) == 0
                sizes.append(max(15, min(80, 15 + eng * 1.5 + (20 if is_root else 0))))
            ax.scatter(xs, ys, s=sizes, c=color, edgecolors="white",
                       linewidth=0.3, zorder=2, alpha=0.9, label=plat)

        # Highlight source
        if highlight_id and highlight_id in pos:
            sx, sy = pos[highlight_id]
            ax.scatter(sx, sy, s=120, facecolors="none", edgecolors=PALETTE["gold"],
                       linewidth=1.5, zorder=3)
            ax.annotate("Source", (sx, sy), textcoords="offset points",
                        xytext=(0, 12), ha="center", fontsize=5.5,
                        color=PALETTE["gold"], fontweight="bold")

        ax.legend(loc="upper right", fontsize=5, markerscale=0.6,
                  handletextpad=0.5, labelspacing=0.3)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(f"Propagation graph ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)",
                     fontsize=7, fontweight="bold", pad=4)

    def _draw_sentiment_evolution(self, ax, evolution, turning_points):
        """Panel b: 情感演化双轴曲线"""
        if not evolution:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color=PALETTE["neutral_mid"])
            return

        levels = [e["level"] for e in evolution]
        polarities = [e["avg_polarity"] for e in evolution]
        arousals = [e["avg_arousal"] for e in evolution]

        ax2 = ax.twinx()

        l1, = ax.plot(levels, polarities, color=POLARITY_COLOR,
                      linewidth=1.5, marker="o", markersize=5, zorder=3,
                      label="Polarity")
        ax.fill_between(levels, 0, polarities, color=POLARITY_COLOR,
                        alpha=0.08, zorder=1)

        l2, = ax2.plot(levels, arousals, color=AROUSAL_COLOR,
                       linewidth=1.2, marker="s", markersize=4, linestyle="--",
                       zorder=3, label="Arousal")

        # Turning point markers
        for tp in turning_points:
            mid_l = (tp["from_level"] + tp["to_level"]) / 2
            idx = int(mid_l)
            y_pos = polarities[idx] if idx < len(polarities) else polarities[-1]
            color = "#2E9E44" if tp["direction"] == "正向" else "#E53935"
            ax.annotate("", xy=(tp["to_level"], y_pos),
                        xytext=(tp["from_level"], y_pos),
                        arrowprops=dict(arrowstyle="<->", color=color, lw=1.5),
                        zorder=4)

        ax.set_xlabel("Propagation depth (BFS level)")
        ax.set_ylabel("Sentiment polarity", color=POLARITY_COLOR)
        ax2.set_ylabel("Arousal intensity", color=AROUSAL_COLOR)
        ax.set_xticks(levels)
        ax.set_ylim(-0.6, 1.0)
        ax2.set_ylim(0.4, 1.0)
        ax.yaxis.label.set_color(POLARITY_COLOR)
        ax2.yaxis.label.set_color(AROUSAL_COLOR)
        ax.tick_params(axis="y", colors=POLARITY_COLOR)
        ax2.tick_params(axis="y", colors=AROUSAL_COLOR)
        ax.legend([l1, l2], ["Polarity (−1 to +1)", "Arousal (0 to 1)"],
                  loc="upper left", fontsize=5.5)
        ax.set_title("Sentiment evolution along propagation chain",
                     fontsize=7, fontweight="bold", pad=4)

    def _draw_source_confidence(self, ax, candidates):
        """Panel c: 源头置信度水平柱状图"""
        if not candidates:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color=PALETTE["neutral_mid"])
            return

        labels = []
        confidences = []
        platforms = []
        for c in candidates:
            pid_short = c["post_id"][:12]
            labels.append(f"[{c['platform']}] {pid_short}")
            confidences.append(c["confidence"])
            platforms.append(c["platform"])

        y_pos = np.arange(len(labels))[::-1]
        colors = [PLATFORM_COLORS.get(p, PALETTE["neutral_mid"]) for p in platforms]

        bars = ax.barh(y_pos, confidences, height=0.55, color=colors,
                       edgecolor="white", linewidth=0.3)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=5.5)
        ax.set_xlim(0, max(confidences) * 1.15)

        for bar, val in zip(bars, confidences):
            ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{val:.3f}", va="center", fontsize=5.5,
                    color=PALETTE["neutral_dark"])

        if bars:
            bars[0].set_edgecolor(PALETTE["gold"])
            bars[0].set_linewidth(1.2)

        ax.set_xlabel("Confidence score")
        ax.set_title("Source candidate ranking", fontsize=7, fontweight="bold", pad=4)
        ax.axvline(x=0.5, color=PALETTE["neutral_light"], linewidth=0.5,
                   linestyle="--", alpha=0.5)

    def _draw_cross_platform(self, ax, comparison):
        """Panel d: 跨平台情感分组柱状图"""
        if not comparison:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color=PALETTE["neutral_mid"])
            return

        platforms = list(comparison.keys())
        polarities = [comparison[p]["avg_polarity"] for p in platforms]
        arousals = [comparison[p]["avg_arousal"] for p in platforms]
        pol_std = [comparison[p].get("polarity_std", 0) for p in platforms]
        counts = [comparison[p]["count"] for p in platforms]
        colors = [PLATFORM_COLORS.get(p, PALETTE["neutral_mid"]) for p in platforms]

        x = np.arange(len(platforms))
        width = 0.35

        ax.bar(x - width / 2, polarities, width, color=colors,
               edgecolor="white", linewidth=0.3, alpha=0.85)
        ax.bar(x + width / 2, arousals, width, color=colors,
               edgecolor="white", linewidth=0.3, alpha=0.4, hatch="///")

        ax.errorbar(x - width / 2, polarities, yerr=pol_std, fmt="none",
                    ecolor=PALETTE["neutral_dark"], capsize=2, linewidth=0.6)

        for i, (bar, cnt) in enumerate(zip(
            ax.containers[0] if ax.containers else [], counts)):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.04,
                    f"n={cnt}", ha="center", fontsize=5,
                    color=PALETTE["neutral_dark"])

        legend_elements = [
            Patch(facecolor=PALETTE["neutral_dark"], alpha=0.7, label="Polarity"),
            Patch(facecolor=PALETTE["neutral_dark"], alpha=0.3,
                  hatch="///", label="Arousal"),
        ]
        ax.legend(handles=legend_elements, loc="upper right", fontsize=5.5)
        ax.set_xticks(x)
        ax.set_xticklabels(platforms, fontsize=6)
        ax.set_ylabel("Score")
        ax.set_ylim(-0.6, 1.0)
        ax.axhline(y=0, color=PALETTE["neutral_light"], linewidth=0.5)
        ax.set_title("Cross-platform sentiment comparison",
                     fontsize=7, fontweight="bold", pad=4)

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _add_label(ax, label):
        ax.text(-0.08, 1.02, label, transform=ax.transAxes, fontsize=10,
                fontweight="bold", ha="left", va="bottom")

    def _save(self, fig, filename):
        base = os.path.join(self.output_dir, filename)
        for fmt, kw in [(".svg", {}), (".pdf", {}), (".png", {"dpi": 600})]:
            path = base + fmt
            fig.savefig(path, bbox_inches="tight", **kw)
        print(f"[NatureViz] 已保存: {base}.svg / .pdf / .png")
        return base + ".svg"
