"""Nature-Figure 风格可视化测试

将项目原有的 Plotly 交互式图表替换为 matplotlib 出版物级静态图表。
遵循 nature-figure skill 规范: 图合约 → 原型分类 → 面板映射 → SVG/PDF/PNG 导出。

用法:
  python scripts/nature_viz_test.py
"""

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
import networkx as nx
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from collections import Counter

# ================================================================
# Figure Contract
# ================================================================
# Core conclusion:
#   "人工智能"事件的传播路径以微博为核心源头，跨平台扩散整体呈现
#   情感正向偏移趋势，微博平台情感极性最高，新闻平台更为中性。
#
# Figure archetype: quantitative grid (4-panel evidence grid)
# Target journal/output: Nature Machine Intelligence style
# Backend: Python (matplotlib)
# Final size: 183mm x 180mm (Nature full-page width)
#
# Panel map:
#   a: 传播力导向图 — 节点=帖子, 边=传播关系, 按平台着色
#   b: 情感演化曲线 — BFS层级 vs 极性/唤起度, 双Y轴
#   c: 源头置信度排序 — 水平柱状图, top-5候选
#   d: 跨平台情感对比 — 分组柱状图, 极性+唤起度+标准差
#
# Evidence hierarchy:
#   hero evidence:   传播图 (a) — 展示完整传播结构与源头定位
#   validation:      情感演化 (b) — 验证情感沿传播链的变化
#   controls:        源头置信度 (c) + 跨平台对比 (d) — 稳健性检验
# ================================================================

# ── PALETTE (from nature-figure/api.md) ─────────────────────────
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

# Platform colors — high-contrast across platforms
PLATFORM_COLORS = {
    "weibo":   "#0F4D92",  # navy blue — primary social media
    "sina":    "#E28E2C",  # amber/orange — news portal (distinct from weibo)
    "netease": "#42949E",  # teal — news portal
    "zhihu":   "#9A4D8E",  # violet — Q&A platform
}

SENTIMENT_COLORS = {
    "polarity": "#B64342",  # red_strong — emotional valence
    "arousal":  "#0F4D92",  # blue_main — intensity
}

# ── Publication Style ───────────────────────────────────────────
# Use Microsoft YaHei as primary font — supports both Latin and CJK glyphs
_CJK_FONT = "Microsoft YaHei"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [_CJK_FONT, "SimHei", "Arial", "DejaVu Sans", "Liberation Sans"],
    "svg.fonttype": "none",      # editable text in SVG
    "pdf.fonttype": 42,          # editable TrueType in PDF
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

# Ensure CJK font is properly loaded
from matplotlib.font_manager import FontProperties
_CJK_FP = FontProperties(family=_CJK_FONT)

OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "data", "figures")


# ── Helpers ─────────────────────────────────────────────────────
def add_panel_label(ax, label, x=-0.08, y=1.02, fontsize=10, fontweight="bold"):
    ax.text(x, y, label, transform=ax.transAxes, fontsize=fontsize,
            fontweight=fontweight, ha="left", va="bottom")


def save_pub(fig, filename, dpi=600):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(f"{base}.svg", bbox_inches="tight")
    fig.savefig(f"{base}.pdf", bbox_inches="tight")
    fig.savefig(f"{base}.png", dpi=dpi, bbox_inches="tight")
    print(f"  → {base}.svg / .pdf / .png")


# ── Data Loading ───────────────────────────────────────────────
def load_data():
    import sqlite3
    from src.analysis.graph import PropagationGraphBuilder
    from src.analysis.tracer import SourceTracer
    from src.analysis.sentiment import SentimentEvolutionAnalyzer

    db_path = os.path.join(_PROJECT_ROOT, "data", "news_trace.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    events = conn.execute(
        "SELECT id, name FROM events WHERE post_count > 0 ORDER BY last_updated DESC LIMIT 1"
    ).fetchall()
    conn.close()

    if not events:
        print("[ERROR] 数据库中没有事件数据")
        return None

    event = dict(events[0])
    event_id = event["id"]
    event_name = event["name"]
    print(f"事件: {event_name} ({event_id})")

    builder = PropagationGraphBuilder(db_path=db_path)
    pg = builder.build(event_id)
    print(f"  传播图: {pg.node_count} 节点, {pg.edge_count} 边")

    tracer = SourceTracer()
    candidates = tracer.trace(pg, top_k=5)
    if candidates:
        print(f"  最可能源头: [{candidates[0]['platform']}] {candidates[0]['author']}")

    analyzer = SentimentEvolutionAnalyzer()
    source_id = candidates[0]["post_id"] if candidates else list(pg.graph.nodes())[0]
    path = analyzer.analyze_path(pg, source_id)
    cross = analyzer.cross_platform_sentiment(pg)

    return {
        "event_name": event_name,
        "event_id": event_id,
        "pg": pg,
        "candidates": candidates,
        "evolution": path.get("evolution", []),
        "turning_points": path.get("turning_points", []),
        "overall_trend": path.get("overall_trend", ""),
        "cross_platform": cross,
    }


# ── Panel a: Propagation Graph ──────────────────────────────────
def draw_propagation_graph(ax, pg, highlight_id=None):
    """力导向传播图 — 节点按平台着色, 边按类型着色"""
    G = pg.graph
    if G.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color=PALETTE["neutral_mid"])
        return

    pos = nx.spring_layout(G, k=2.5, iterations=60, seed=42)

    # Edges — draw first so they're behind nodes
    edge_types = {"repost": [], "cite": [], "cross_platform": [], "image_match": []}
    for u, v, data in G.edges(data=True):
        etype = data.get("type", "cite")
        if etype in edge_types:
            edge_types[etype].append((u, v))

    edge_style = {
        "repost":         (PALETTE["blue_main"], 0.75, 0.8, "-"),
        "cite":           (PALETTE["neutral_dark"], 0.65, 0.7, "--"),
        "cross_platform": (PALETTE["red_strong"], 0.75, 1.2, "-"),
        "image_match":    (PALETTE["teal"], 0.6, 0.9, ":"),
    }

    for etype, edges in edge_types.items():
        if not edges:
            continue
        color, alpha, lw, ls = edge_style[etype]
        for u, v in edges:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            ax.plot([x0, x1], [y0, y1], color=color, alpha=alpha,
                    linewidth=lw, linestyle=ls, zorder=1)

    # Nodes — by platform
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
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"Propagation graph ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)",
                 fontsize=7, fontweight="bold", pad=4)


# ── Panel b: Sentiment Evolution ───────────────────────────────
def draw_sentiment_evolution(ax, evolution, turning_points):
    """情感演化双轴曲线 — 极性 + 唤起度 vs BFS传播层级"""
    if not evolution:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color=PALETTE["neutral_mid"])
        return

    levels = [e["level"] for e in evolution]
    polarities = [e["avg_polarity"] for e in evolution]
    arousals = [e["avg_arousal"] for e in evolution]
    counts = [e["node_count"] for e in evolution]

    ax2 = ax.twinx()

    # Polarity line (left y)
    line1, = ax.plot(levels, polarities, color=SENTIMENT_COLORS["polarity"],
                     linewidth=1.5, marker="o", markersize=5, zorder=3, label="Polarity")
    ax.fill_between(levels, 0, polarities, color=SENTIMENT_COLORS["polarity"],
                    alpha=0.08, zorder=1)

    # Arousal line (right y)
    line2, = ax2.plot(levels, arousals, color=SENTIMENT_COLORS["arousal"],
                      linewidth=1.2, marker="s", markersize=4, linestyle="--",
                      zorder=3, label="Arousal")

    # Node count as bubble size reference (subtle)
    ax3 = ax.twinx()
    ax3.spines["right"].set_position(("outward", 22))
    ax3.scatter(levels, [0.5] * len(levels), s=[c * 4 for c in counts],
                color=PALETTE["neutral_light"], alpha=0.4, zorder=2)
    ax3.set_ylim(0, 1)
    ax3.set_yticks([])

    # Turning point markers
    for tp in turning_points:
        mid_l = (tp["from_level"] + tp["to_level"]) / 2
        y_pos = polarities[int(mid_l)] if int(mid_l) < len(polarities) else polarities[-1]
        color = "#2E9E44" if tp["direction"] == "正向" else "#E53935"
        ax.annotate("", xy=(tp["to_level"], y_pos),
                    xytext=(tp["from_level"], y_pos),
                    arrowprops=dict(arrowstyle="<->", color=color, lw=1.5),
                    zorder=4)

    # Styling
    ax.set_xlabel("Propagation depth (BFS level)")
    ax.set_ylabel("Sentiment polarity", color=SENTIMENT_COLORS["polarity"])
    ax2.set_ylabel("Arousal intensity", color=SENTIMENT_COLORS["arousal"])
    ax.set_xticks(levels)
    ax.set_ylim(-0.6, 1.0)
    ax2.set_ylim(0.4, 1.0)
    ax.yaxis.label.set_color(SENTIMENT_COLORS["polarity"])
    ax2.yaxis.label.set_color(SENTIMENT_COLORS["arousal"])
    ax.tick_params(axis="y", colors=SENTIMENT_COLORS["polarity"])
    ax2.tick_params(axis="y", colors=SENTIMENT_COLORS["arousal"])

    # Combined legend
    lines = [line1, line2]
    labels = ["Polarity (−1 to +1)", "Arousal (0 to 1)"]
    ax.legend(lines, labels, loc="upper left", fontsize=5.5)

    ax.set_title("Sentiment evolution along propagation chain",
                 fontsize=7, fontweight="bold", pad=4)


# ── Panel c: Source Confidence ──────────────────────────────────
def draw_source_confidence(ax, candidates):
    """源头置信度水平排序柱状图"""
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

    # Value labels
    for bar, val in zip(bars, confidences):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=5.5, color=PALETTE["neutral_dark"])

    # Highlight top candidate
    if bars:
        bars[0].set_edgecolor(PALETTE["gold"])
        bars[0].set_linewidth(1.2)

    ax.set_xlabel("Confidence score")
    ax.set_title("Source candidate ranking", fontsize=7, fontweight="bold", pad=4)
    ax.axvline(x=0.5, color=PALETTE["neutral_light"], linewidth=0.5,
               linestyle="--", alpha=0.5)


# ── Panel d: Cross-Platform Sentiment Comparison ────────────────
def draw_cross_platform(ax, comparison):
    """跨平台情感分组柱状图 — 极性 + 唤起度"""
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

    bars1 = ax.bar(x - width / 2, polarities, width, color=colors,
                   edgecolor="white", linewidth=0.3, alpha=0.85)
    bars2 = ax.bar(x + width / 2, arousals, width, color=colors,
                   edgecolor="white", linewidth=0.3, alpha=0.4, hatch="///")

    # Error bars
    ax.errorbar(x - width / 2, polarities, yerr=pol_std, fmt="none",
                ecolor=PALETTE["neutral_dark"], capsize=2, linewidth=0.6)

    # Count labels
    for i, (bar, cnt) in enumerate(zip(bars1, counts)):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.04,
                f"n={cnt}", ha="center", fontsize=5, color=PALETTE["neutral_dark"])

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=PALETTE["neutral_dark"], alpha=0.7, label="Polarity"),
        Patch(facecolor=PALETTE["neutral_dark"], alpha=0.3, hatch="///", label="Arousal"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=5.5)

    ax.set_xticks(x)
    ax.set_xticklabels(platforms, fontsize=6)
    ax.set_ylabel("Score")
    ax.set_ylim(-0.6, 1.0)
    ax.axhline(y=0, color=PALETTE["neutral_light"], linewidth=0.5)
    ax.set_title("Cross-platform sentiment comparison", fontsize=7, fontweight="bold", pad=4)


# ── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 56)
    print("Nature-Figure 可视化测试")
    print("=" * 56)

    data = load_data()
    if not data:
        return

    pg = data["pg"]
    candidates = data["candidates"]
    evolution = data["evolution"]
    turning_points = data["turning_points"]
    cross_platform = data["cross_platform"]

    # ── Build 2×2 Figure ────────────────────────────────────────
    fig = plt.figure(figsize=(7.2, 6.5))  # 183mm × 165mm

    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.28,
                          height_ratios=[1.0, 0.85])

    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    # Panel labels
    add_panel_label(ax_a, "a", x=-0.10, y=1.03)
    add_panel_label(ax_b, "b", x=-0.10, y=1.03)
    add_panel_label(ax_c, "c", x=-0.10, y=1.06)
    add_panel_label(ax_d, "d", x=-0.10, y=1.06)

    # Draw panels
    source_id = candidates[0]["post_id"] if candidates else None
    draw_propagation_graph(ax_a, pg, highlight_id=source_id)
    draw_sentiment_evolution(ax_b, evolution, turning_points)
    draw_source_confidence(ax_c, candidates)
    draw_cross_platform(ax_d, cross_platform)

    # Suptitle — figure-level title
    fig.suptitle(f'Event propagation trace: "{data["event_name"]}"',
                 fontsize=9, fontweight="bold", x=0.02, y=0.99, ha="left")

    # Export
    event_id_short = data["event_id"][:16]
    filename = f"nature_test_{event_id_short}"
    save_pub(fig, filename)

    print(f"\n导出完成 → data/figures/{filename}.svg / .pdf / .png")
    print("请打开 SVG 或 PNG 查看效果。")

    plt.close(fig)


if __name__ == "__main__":
    main()
