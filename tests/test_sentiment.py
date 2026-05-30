"""情感演化分析测试"""

import pytest
import networkx as nx
from src.analysis.graph import PropagationGraph
from src.analysis.sentiment import SentimentEvolutionAnalyzer


class TestBFSLevels:
    """BFS 层级划分"""

    def test_single_node(self):
        """单节点: 仅 level 0"""
        G = nx.DiGraph()
        G.add_node("a")
        levels = SentimentEvolutionAnalyzer._bfs_levels(G, "a")
        assert levels == {0: ["a"]}

    def test_chain(self):
        """链状传播: a→b→c → levels 0,1,2"""
        G = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("b", "c")
        levels = SentimentEvolutionAnalyzer._bfs_levels(G, "a")
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]
        assert len(levels) == 3

    def test_branching(self):
        """分支传播: a→b, a→c → levels 0: [a], 1: [b,c]"""
        G = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_edge("a", "c")
        levels = SentimentEvolutionAnalyzer._bfs_levels(G, "a")
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert len(levels) == 2

    def test_disconnected_node(self):
        """不连通的节点不应出现在 BFS 中"""
        G = nx.DiGraph()
        G.add_edge("a", "b")
        G.add_node("orphan")  # 无入边无出边
        levels = SentimentEvolutionAnalyzer._bfs_levels(G, "a")
        all_nodes = set()
        for nodes in levels.values():
            all_nodes.update(nodes)
        assert "orphan" not in all_nodes


class TestSentimentAggregation:
    """情感聚合统计"""

    def test_aggregate_dominant(self):
        sentiments = [
            {"dominant": "正面", "polarity": 0.8},
            {"dominant": "正面", "polarity": 0.6},
            {"dominant": "负面", "polarity": -0.4},
            {"dominant": "中性", "polarity": 0.0},
        ]
        result = SentimentEvolutionAnalyzer._aggregate_dominant(sentiments)
        assert result["正面"] == pytest.approx(0.5, abs=0.01)  # 2/4
        assert result["负面"] == pytest.approx(0.25, abs=0.01)  # 1/4

    def test_aggregate_single(self):
        sentiments = [{"dominant": "正面", "polarity": 0.9}]
        result = SentimentEvolutionAnalyzer._aggregate_dominant(sentiments)
        assert result["正面"] == 1.0


class TestTurningPoints:
    """情感转折点检测"""

    def test_no_turning_points_stable(self):
        """稳定情感 → 无转折点"""
        evolution = [
            {"level": 0, "avg_polarity": 0.5},
            {"level": 1, "avg_polarity": 0.55},
            {"level": 2, "avg_polarity": 0.48},
        ]
        tp = SentimentEvolutionAnalyzer._detect_turning_points(evolution)
        assert len(tp) == 0

    def test_turning_point_detected(self):
        """极性突变 > 0.3 → 检测到转折点"""
        evolution = [
            {"level": 0, "avg_polarity": 0.8},
            {"level": 1, "avg_polarity": -0.2},  # Δ = 1.0
        ]
        tp = SentimentEvolutionAnalyzer._detect_turning_points(evolution)
        assert len(tp) == 1
        assert tp[0]["from_level"] == 0
        assert tp[0]["to_level"] == 1
        assert tp[0]["direction"] == "负向"

    def test_positive_turning_point(self):
        """正向转折: -0.5 → 0.3 (Δ = 0.8)"""
        evolution = [
            {"level": 0, "avg_polarity": -0.5},
            {"level": 1, "avg_polarity": 0.3},
        ]
        tp = SentimentEvolutionAnalyzer._detect_turning_points(evolution)
        assert len(tp) == 1
        assert tp[0]["direction"] == "正向"


class TestTrendComputation:
    """整体趋势判定"""

    def test_positive_shift(self):
        evolution = [
            {"level": 0, "avg_polarity": -0.3},
            {"level": 1, "avg_polarity": 0.0},
            {"level": 2, "avg_polarity": 0.4},
        ]
        trend = SentimentEvolutionAnalyzer._compute_trend(evolution)
        assert "正向" in trend

    def test_negative_shift(self):
        evolution = [
            {"level": 0, "avg_polarity": 0.5},
            {"level": 1, "avg_polarity": -0.1},
        ]
        trend = SentimentEvolutionAnalyzer._compute_trend(evolution)
        assert "负向" in trend

    def test_stable(self):
        evolution = [
            {"level": 0, "avg_polarity": 0.3},
            {"level": 1, "avg_polarity": 0.4},
        ]
        trend = SentimentEvolutionAnalyzer._compute_trend(evolution)
        assert "稳定" in trend

    def test_insufficient_data(self):
        """数据不足 (1 层)"""
        evolution = [{"level": 0, "avg_polarity": 0.5}]
        trend = SentimentEvolutionAnalyzer._compute_trend(evolution)
        assert "数据不足" == trend

    def test_empty_evolution(self):
        """空序列"""
        trend = SentimentEvolutionAnalyzer._compute_trend([])
        assert "数据不足" == trend
