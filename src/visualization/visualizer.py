"""传播图谱可视化

基于 Plotly 的交互式传播图、情感演化曲线、源头置信度、跨平台对比。

依赖:
  plotly, networkx, numpy
"""

import os
import numpy as np
import networkx as nx
from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 平台配色
PLATFORM_COLORS = {
    "weibo": "#e60012",
    "sina": "#ff8400",
    "netease": "#c30",
    "zhihu": "#0066ff",
}

EDGE_COLORS = {
    "repost": "#1f77b4",
    "cite": "#ff7f0e",
    "cross_platform": "#2ca02c",
    "image_match": "#d62728",
}


class PropagationVisualizer:
    """交互式传播图谱可视化"""

    def __init__(self, output_dir: str = "data/figures"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def plot_propagation_graph(self, pg, highlight_source: str = None) -> go.Figure:
        """传播力导向图 — 节点=帖子, 边=传播关系"""
        G = pg.graph
        if G.number_of_nodes() == 0:
            return go.Figure()

        pos = nx.spring_layout(G, k=3, iterations=50, seed=42)

        # 按边类型分组绘制
        edge_groups: dict[str, list] = {"repost": [], "cite": [],
                                         "cross_platform": [], "image_match": []}
        for u, v, data in G.edges(data=True):
            etype = data.get("type", "cite")
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            if etype in edge_groups:
                edge_groups[etype].append((x0, x1, y0, y1))

        edge_traces = []
        for etype, coords in edge_groups.items():
            if not coords:
                continue
            ex, ey = [], []
            for x0, x1, y0, y1 in coords:
                ex.extend([x0, x1, None])
                ey.extend([y0, y1, None])
            edge_traces.append(go.Scatter(
                x=ex, y=ey, mode="lines",
                line=dict(width=1, color=EDGE_COLORS.get(etype, "#999")),
                name=etype, hoverinfo="none",
            ))

        # 节点 — 按平台分组
        platform_nodes: dict[str, list] = {}
        for node in G.nodes():
            p = G.nodes[node].get("platform", "unknown")
            platform_nodes.setdefault(p, []).append(node)

        node_traces = []
        for plat, nodes in platform_nodes.items():
            nx_list, ny_list, ntext, nsize = [], [], [], []
            for n in nodes:
                x, y = pos[n]
                nx_list.append(x)
                ny_list.append(y)
                text = (G.nodes[n].get("text") or "")[:60]
                engagement = G.nodes[n].get("engagement", 0) or 0
                is_root = G.in_degree(n) == 0
                ntext.append(f"{text}<br>入度={G.in_degree(n)} 出度={G.out_degree(n)}")
                nsize.append(max(8, min(30, 10 + engagement / 5 + (10 if is_root else 0))))
            node_traces.append(go.Scatter(
                x=nx_list, y=ny_list, mode="markers+text",
                marker=dict(size=nsize, color=PLATFORM_COLORS.get(plat, "#999"),
                           line=dict(width=1, color="#333")),
                text=[G.nodes[n].get("author", "")[:8] for n in nodes],
                textposition="top center",
                name=f"{plat} ({len(nodes)})",
                hovertext=ntext, hoverinfo="text",
            ))

        # 标记源头
        shapes = []
        if highlight_source and highlight_source in pos:
            sx, sy = pos[highlight_source]
            shapes.append(dict(
                type="circle", xref="x", yref="y",
                x0=sx - 0.05, x1=sx + 0.05, y0=sy - 0.05, y1=sy + 0.05,
                line=dict(color="#ff0", width=2),
            ))

        fig = go.Figure(data=edge_traces + node_traces)
        fig.update_layout(
            title=f"新闻事件传播图谱 ({G.number_of_nodes()} 节点, {G.number_of_edges()} 边)",
            showlegend=True, hovermode="closest",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            shapes=shapes,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        return fig

    def plot_sentiment_timeline(self, evolution: list[dict]) -> go.Figure:
        """情感演化双轴曲线 — 极性 + 唤起度 vs 传播层级"""
        levels = [e["level"] for e in evolution]
        polarities = [e["avg_polarity"] for e in evolution]
        arousals = [e["avg_arousal"] for e in evolution]
        counts = [e["node_count"] for e in evolution]

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(
            x=levels, y=polarities, mode="lines+markers",
            name="情感极性", line=dict(color="#e60012", width=2.5),
            marker=dict(size=counts, sizemode="area", sizeref=2, sizemin=8),
            hovertemplate="L%{x}: polarity=%{y:.3f}<extra></extra>",
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=levels, y=arousals, mode="lines+markers",
            name="唤起度", line=dict(color="#0066ff", width=2, dash="dash"),
            hovertemplate="L%{x}: arousal=%{y:.3f}<extra></extra>",
        ), secondary_y=True)

        fig.update_layout(
            title="传播链情感演化（气泡大小=节点数）",
            xaxis=dict(title="传播层级 (BFS depth)", dtick=1),
            hovermode="x unified",
        )
        fig.update_yaxes(title_text="情感极性 (-1~+1)", secondary_y=False, range=[-1, 1])
        fig.update_yaxes(title_text="情感唤起度 (0~1)", secondary_y=True, range=[0, 1])
        return fig

    def plot_source_confidence(self, candidates: list[dict]) -> go.Figure:
        """源头置信度排序柱状图"""
        if not candidates:
            return go.Figure()
        labels = [f"{c['platform'][:4]}:{c['post_id'][:8]}" for c in candidates]
        values = [c["confidence"] for c in candidates]
        colors = ["#e60012" if i == 0 else "#4472C4" for i in range(len(candidates))]

        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color=colors,
            text=[f"{v:.3f}" for v in values], textposition="auto",
            hovertemplate="%{x}<br>confidence=%{y:.3f}<extra></extra>",
        ))
        fig.update_layout(
            title="源头候选置信度排序",
            yaxis=dict(title="溯源置信度", range=[0, 1]),
            showlegend=False,
        )
        return fig

    def plot_cross_platform_comparison(self, comparison: dict) -> go.Figure:
        """跨平台情感对比 — 分组柱状图"""
        platforms = list(comparison.keys())
        polarities = [comparison[p]["avg_polarity"] for p in platforms]
        arousals = [comparison[p]["avg_arousal"] for p in platforms]
        counts = [comparison[p]["count"] for p in platforms]
        pol_std = [comparison[p].get("polarity_std", 0) for p in platforms]

        fig = make_subplots(rows=1, cols=2,
                            subplot_titles=("平均情感极性", "平均唤起度"))

        fig.add_trace(go.Bar(
            x=platforms, y=polarities,
            marker_color=[PLATFORM_COLORS.get(p, "#999") for p in platforms],
            error_y=dict(type="data", array=pol_std, visible=True),
            text=[f"{v:.3f}" for v in polarities], textposition="auto",
            name="极性",
        ), row=1, col=1)

        fig.add_trace(go.Bar(
            x=platforms, y=arousals,
            marker_color=[PLATFORM_COLORS.get(p, "#999") for p in platforms],
            text=[f"n={c}" for c in counts], textposition="auto",
            name="唤起度",
        ), row=1, col=2)

        fig.update_layout(title="跨平台情感对比", showlegend=False)
        fig.update_yaxes(title_text="情感极性", range=[-1, 1], row=1, col=1)
        fig.update_yaxes(title_text="唤起度", range=[0, 1], row=1, col=2)
        return fig

    def save_figure(self, fig: go.Figure, filename: str):
        path = os.path.join(self.output_dir, filename)
        fig.write_html(path)
        print(f"[Viz] 已保存: {path}")

    def generate_all(self, pg, trace_result: list[dict],
                     sentiment_result: dict, save: bool = True) -> dict[str, go.Figure]:
        """一键生成全部图表"""
        figures = {}

        fig1 = self.plot_propagation_graph(
            pg, highlight_source=trace_result[0]["post_id"] if trace_result else None)
        figures["propagation_graph"] = fig1

        evolution = sentiment_result.get("evolution", [])
        if evolution:
            figures["sentiment_timeline"] = self.plot_sentiment_timeline(evolution)

        if trace_result:
            figures["source_confidence"] = self.plot_source_confidence(trace_result)

        comparison = sentiment_result.get("cross_platform", {})
        if comparison:
            figures["cross_platform"] = self.plot_cross_platform_comparison(comparison)

        if save:
            for name, fig in figures.items():
                self.save_figure(fig, f"{name}.html")

        return figures
