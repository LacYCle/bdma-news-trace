"""分析报告生成器

从传播图 / 溯源结果 / 情感演化结果自动生成 Markdown 分析报告。

依赖:
  无外部依赖（纯文本模板）
"""

import os
from datetime import datetime
from typing import Optional


class ReportGenerator:
    """新闻溯源分析报告自动生成"""

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, event_name: str, event_id: str,
                 pg, trace_result: list[dict],
                 sentiment_result: dict,
                 figures: Optional[dict] = None) -> str:
        """生成完整 Markdown 分析报告"""
        G = pg.graph
        top_source = trace_result[0] if trace_result else None

        # 统计信息
        platforms = set(G.nodes[n].get("platform", "?") for n in G.nodes())
        edge_types = {}
        for _, _, d in G.edges(data=True):
            et = d.get("type", "?")
            edge_types[et] = edge_types.get(et, 0) + 1
        posts_per_platform = {}
        for n in G.nodes():
            p = G.nodes[n].get("platform", "?")
            posts_per_platform[p] = posts_per_platform.get(p, 0) + 1

        lines = []
        self._section(lines, 1, f"新闻事件溯源分析报告 — {event_name}")
        lines.append(f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        lines.append(f"> 事件 ID: `{event_id}`\n")

        # 1. 事件概要
        self._section(lines, 2, "事件概要")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 事件名称 | {event_name} |")
        lines.append(f"| 传播节点总数 | {G.number_of_nodes()} |")
        lines.append(f"| 传播边总数 | {G.number_of_edges()} |")
        lines.append(f"| 涉及平台数 | {len(platforms)} |")
        lines.append(f"| 平台分布 | {', '.join(f'{k}({v})' for k, v in sorted(posts_per_platform.items(), key=lambda x: -x[1]))} |")
        lines.append(f"| 边类型分布 | {', '.join(f'{k}({v})' for k, v in edge_types.items())} |")
        lines.append("")

        # 2. 源头溯源
        self._section(lines, 2, "源头溯源结果")
        if top_source:
            self._section(lines, 3, "最可能源头")
            lines.append(f"- **平台**: {top_source['platform']}")
            lines.append(f"- **发布者**: {top_source['author']}")
            lines.append(f"- **发布时间**: {top_source.get('timestamp', '未知')}")
            lines.append(f"- **置信度**: {top_source['confidence']:.2%}")
            lines.append(f"- **内容预览**: {top_source.get('text_preview', '')}")
            lines.append("")

            ev = top_source.get("evidence", {})
            self._section(lines, 3, "证据链")
            lines.append(f"- 直接转发数: {ev.get('direct_reposts', 0)}")
            lines.append(f"- 跨平台传播数: {ev.get('cross_platform_spread', 0)}")
            lines.append(f"- 总出度: {ev.get('total_out_degree', 0)}")
            lines.append(f"- 首批传播平台: {', '.join(ev.get('first_level_platforms', ['无']))}")
            lines.append("")

        # 完整候选列表
        if len(trace_result) > 1:
            self._section(lines, 3, "候选源头列表")
            lines.append("| 排名 | 平台 | 发布者 | 置信度 |")
            lines.append("|------|------|--------|--------|")
            for i, c in enumerate(trace_result):
                lines.append(f"| {i+1} | {c['platform']} | {c['author']} | {c['confidence']:.3f} |")
            lines.append("")

        # 3. 情感演化
        self._section(lines, 2, "情感演化分析")
        evolution = sentiment_result.get("evolution", [])
        trend = sentiment_result.get("overall_trend", "")
        lines.append(f"**整体趋势**: {trend}\n")

        if evolution:
            self._section(lines, 3, "逐层情感变化")
            lines.append("| 层级 | 节点数 | 平均极性 | 平均唤起度 | 主导情感 |")
            lines.append("|------|--------|----------|------------|----------|")
            for evo in evolution:
                dom_str = ", ".join(f"{k}({v:.0%})" for k, v in evo.get("dominant_emotions", {}).items())
                lines.append(f"| L{evo['level']} | {evo['node_count']} | {evo['avg_polarity']:+.3f} | {evo['avg_arousal']:.3f} | {dom_str} |")
            lines.append("")

        # 转折点
        turning = sentiment_result.get("turning_points", [])
        if turning:
            self._section(lines, 3, "情感转折点")
            for tp in turning:
                arrow = "↗" if tp["direction"] == "正向" else "↘"
                lines.append(f"- L{tp['from_level']}→L{tp['to_level']}: {arrow} {tp['direction']} Δ={tp['magnitude']:.3f}")
            lines.append("")

        # 4. 跨平台情感
        comparison = sentiment_result.get("cross_platform", {})
        if comparison:
            self._section(lines, 2, "跨平台情感对比")
            lines.append("| 平台 | 帖子数 | 平均极性 | 极性标准差 | 平均唤起度 | 主导情感 |")
            lines.append("|------|--------|----------|------------|------------|----------|")
            for plat, stats in comparison.items():
                lines.append(f"| {plat} | {stats['count']} | {stats['avg_polarity']:+.3f} | {stats.get('polarity_std', 0):.3f} | {stats['avg_arousal']:.3f} | {stats.get('dominant_emotion', '?')} |")
            lines.append("")

        # 5. 图表索引
        if figures:
            self._section(lines, 2, "可视化图表")
            for name in figures:
                lines.append(f"- `{name}` → `data/figures/{name}.html`")
            lines.append("")

        # 6. 页脚
        lines.append("---")
        lines.append(f"*报告由 BDMA News Trace 系统自动生成*\n")

        report = "\n".join(lines)
        return report

    def save(self, content: str, event_id: str) -> str:
        path = os.path.join(self.output_dir, f"{event_id}_report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Report] 已保存: {path}")
        return path

    @staticmethod
    def _section(lines: list, level: int, title: str):
        prefix = "#" * level
        lines.append(f"{prefix} {title}")
