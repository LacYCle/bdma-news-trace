"""情感演化分析器

沿传播路径的 BFS 层级情感追踪 + 情感转折点检测 + 跨平台情感差异对比。

依赖:
  networkx, numpy, src.features.text
"""

import numpy as np
import networkx as nx
from collections import Counter

from .graph import PropagationGraph


class SentimentEvolutionAnalyzer:
    """情感沿传播路径的演化分析"""

    def __init__(self):
        self._sentiment_analyzer = None

    @property
    def sa(self):
        if self._sentiment_analyzer is None:
            from ..features.text import ChineseSentimentAnalyzer
            self._sentiment_analyzer = ChineseSentimentAnalyzer()
        return self._sentiment_analyzer

    def analyze_path(self, pg: PropagationGraph, source_id: str) -> dict:
        """从 source_id 出发，BFS 分层追踪情感演化"""
        G = pg.graph
        levels = self._bfs_levels(G, source_id)

        evolution = []
        for level, nodes in levels.items():
            sentiments = []
            for node_id in nodes:
                text = G.nodes[node_id].get("text", "")
                if text:
                    result = self.sa.analyze(text)
                    sentiments.append(result)

            if sentiments:
                avg_polarity = float(np.mean([s["polarity"] for s in sentiments]))
                avg_arousal = float(np.mean([s["arousal"] for s in sentiments]))
                dominants = self._aggregate_dominant(sentiments)
                evolution.append({
                    "level": level,
                    "node_count": len(nodes),
                    "avg_polarity": round(avg_polarity, 4),
                    "avg_arousal": round(avg_arousal, 4),
                    "dominant_emotions": dominants,
                })

        turning_points = self._detect_turning_points(evolution)

        return {
            "source_id": source_id,
            "evolution": evolution,
            "turning_points": turning_points,
            "overall_trend": self._compute_trend(evolution),
        }

    def cross_platform_sentiment(self, pg: PropagationGraph) -> dict:
        """跨平台情感差异对比"""
        G = pg.graph
        platform_sentiments: dict[str, list[dict]] = {}

        for node_id in G.nodes():
            platform = G.nodes[node_id].get("platform", "unknown")
            text = G.nodes[node_id].get("text", "")
            if text:
                result = self.sa.analyze(text)
                platform_sentiments.setdefault(platform, []).append(result)

        comparison = {}
        for plat, sentiments in platform_sentiments.items():
            polarities = [s["polarity"] for s in sentiments]
            dominants = [s["dominant"] for s in sentiments]
            comparison[plat] = {
                "count": len(sentiments),
                "avg_polarity": round(float(np.mean(polarities)), 4),
                "avg_arousal": round(float(np.mean([s["arousal"] for s in sentiments])), 4),
                "polarity_std": round(float(np.std(polarities)), 4),
                "dominant_emotion": Counter(dominants).most_common(1)[0][0]
                if dominants else "未知",
            }

        return comparison

    @staticmethod
    def _bfs_levels(G: nx.DiGraph, source: str) -> dict[int, list]:
        levels = {0: [source]}
        visited = {source}
        current_level = [source]
        depth = 0
        while current_level:
            next_level = []
            for node in current_level:
                for _, child in G.out_edges(node):
                    if child not in visited:
                        visited.add(child)
                        next_level.append(child)
            if next_level:
                depth += 1
                levels[depth] = next_level
                current_level = next_level
            else:
                break
        return levels

    @staticmethod
    def _aggregate_dominant(sentiments: list[dict]) -> dict:
        counts = Counter(s["dominant"] for s in sentiments)
        total = len(sentiments)
        return {k: round(v / total, 3) for k, v in counts.most_common(3)}

    @staticmethod
    def _detect_turning_points(evolution: list[dict]) -> list[dict]:
        turning_points = []
        for i in range(1, len(evolution)):
            prev_pol = evolution[i - 1]["avg_polarity"]
            curr_pol = evolution[i]["avg_polarity"]
            delta = abs(curr_pol - prev_pol)
            if delta > 0.3:
                turning_points.append({
                    "from_level": i - 1,
                    "to_level": i,
                    "polarity_shift": round(float(curr_pol - prev_pol), 4),
                    "direction": "正向" if curr_pol > prev_pol else "负向",
                    "magnitude": round(float(delta), 4),
                })
        return turning_points

    @staticmethod
    def _compute_trend(evolution: list[dict]) -> str:
        if len(evolution) < 2:
            return "数据不足"
        diff = evolution[-1]["avg_polarity"] - evolution[0]["avg_polarity"]
        if diff > 0.2:
            return "情感正向偏移"
        elif diff < -0.2:
            return "情感负向偏移"
        return "情感基本稳定"
