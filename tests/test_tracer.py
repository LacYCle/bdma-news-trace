"""源头溯源测试"""

import pytest
import networkx as nx
from src.analysis.graph import PropagationGraph


class TestSourceTracer:
    """SourceTracer 溯源算法"""

    def test_candidates_returned(self, tracer, pg_with_edges, candidates):
        """应返回 top_k 个候选"""
        assert 1 <= len(candidates) <= 5

    def test_top_candidate_has_confidence(self, candidates):
        """第一个候选应有最高置信度"""
        assert candidates[0]["confidence"] > 0
        for i in range(1, len(candidates)):
            assert candidates[i - 1]["confidence"] >= candidates[i]["confidence"]

    def test_candidate_fields(self, candidates):
        """每个候选应包含必要字段"""
        for c in candidates:
            assert "post_id" in c
            assert "platform" in c
            assert "author" in c
            assert "confidence" in c
            assert "evidence" in c

    def test_evidence_fields(self, candidates):
        """证据链字段完整"""
        for c in candidates:
            ev = c["evidence"]
            assert "direct_reposts" in ev
            assert "cross_platform_spread" in ev
            assert "total_out_degree" in ev

    def test_empty_graph_returns_empty(self, tracer, pg_empty):
        """空图应返回空列表"""
        result = tracer.trace(pg_empty, top_k=5)
        assert result == []

    def test_single_node_graph(self, tracer):
        """单节点图: 返回唯一节点, 置信度 = 0.85 (base 0.5 + root 0.25 + text 0.10)"""
        pg = PropagationGraph(event_id="single")
        pg.add_post_node({
            "id": "only", "platform": "weibo", "text": "唯一帖子",
            "timestamp": "2026-05-29T10:00:00",
        })
        result = tracer.trace(pg, top_k=5)
        assert len(result) == 1
        assert result[0]["post_id"] == "only"
        assert result[0]["confidence"] == pytest.approx(0.85, abs=0.01)

    def test_root_node_preference(self, tracer):
        """入度为 0 的根节点应优先于子节点"""
        pg = PropagationGraph(event_id="test")
        pg.add_post_node({"id": "root", "platform": "weibo", "text": "源头",
                          "timestamp": "2026-05-29T09:00:00"})
        pg.add_post_node({"id": "child", "platform": "weibo", "text": "转发",
                          "timestamp": "2026-05-29T10:00:00",
                          "parent_id": "root"})
        pg.add_edge("root", "child", edge_type="repost")

        result = tracer.trace(pg, top_k=5)
        # root 入度=0 应排名靠前
        assert result[0]["post_id"] == "root"

    def test_multi_root_graph(self, tracer):
        """多根节点图中, 较早发布的根节点通常排名靠前"""
        pg = PropagationGraph(event_id="multi_root")
        pg.add_post_node({"id": "late_root", "platform": "sina", "text": "晚",
                          "timestamp": "2026-05-29T11:00:00",
                          "author_name": "晚发者"})
        pg.add_post_node({"id": "early_root", "platform": "weibo", "text": "早",
                          "timestamp": "2026-05-29T09:00:00",
                          "author_name": "早发者"})
        pg.add_post_node({"id": "child_a", "platform": "weibo", "text": "fwd",
                          "timestamp": "2026-05-29T11:30:00",
                          "parent_id": "late_root"})
        pg.add_post_node({"id": "child_b", "platform": "sina", "text": "fwd",
                          "timestamp": "2026-05-29T09:30:00",
                          "parent_id": "early_root"})
        pg.add_edge("late_root", "child_a", edge_type="repost")
        pg.add_edge("early_root", "child_b", edge_type="repost")

        result = tracer.trace(pg, top_k=5)
        # 两个根节点都应出现在结果中
        root_ids = {c["post_id"] for c in result}
        assert "early_root" in root_ids
        assert "late_root" in root_ids


class TestSourceTracingEvaluator:
    """SourceTracingEvaluator 评估"""

    def test_evaluator_import(self):
        from src.analysis.tracer import SourceTracingEvaluator
        evaluator = SourceTracingEvaluator()
        assert evaluator is not None

    def test_evaluate_perfect_hit(self, tracer):
        """完美命中: Hits@1 = Hits@3 = 1.0"""
        from src.analysis.tracer import SourceTracingEvaluator

        pg = PropagationGraph(event_id="perf")
        pg.add_post_node({"id": "src", "platform": "weibo", "text": "源",
                          "timestamp": "2026-05-29T09:00:00"})

        evaluator = SourceTracingEvaluator()
        metrics = evaluator.evaluate(tracer, [
            {"pg": pg, "true_source_id": "src"},
        ])
        assert metrics["hits@1"] == 1.0
        assert metrics["hits@3"] == 1.0

    def test_evaluate_miss(self, tracer):
        """完全未命中: Hits@1 = Hits@3 = 0.0"""
        from src.analysis.tracer import SourceTracingEvaluator

        pg = PropagationGraph(event_id="miss")
        pg.add_post_node({"id": "real_source", "platform": "weibo",
                          "text": "真实源", "timestamp": "2026-05-29T09:00:00"})
        pg.add_post_node({"id": "child_1", "platform": "sina",
                          "text": "转发1", "timestamp": "2026-05-29T09:30:00"})
        pg.add_edge("real_source", "child_1", edge_type="cross_platform")

        evaluator = SourceTracingEvaluator()
        metrics = evaluator.evaluate(tracer, [
            {"pg": pg, "true_source_id": "nonexistent_id"},
        ])
        assert metrics["hits@1"] == 0.0
        assert metrics["hits@3"] == 0.0

    def test_evaluate_mrr(self, tracer):
        """MRR 计算: rank=2 → RR=0.5"""
        from src.analysis.tracer import SourceTracingEvaluator

        pg = PropagationGraph(event_id="mrr_test")
        pg.add_post_node({"id": "first", "platform": "weibo", "text": "第一",
                          "timestamp": "2026-05-29T09:00:00"})
        pg.add_post_node({"id": "second", "platform": "sina", "text": "第二",
                          "timestamp": "2026-05-29T09:15:00"})

        evaluator = SourceTracingEvaluator()
        # "second" is the truth, but "first" ranks higher (earlier + root)
        metrics = evaluator.evaluate(tracer, [
            {"pg": pg, "true_source_id": "second"},
        ])
        # second should be at rank 2 → RR = 0.5
        assert metrics["mrr"] == 0.5

    def test_evaluate_empty(self, tracer):
        """空事件列表 → 全 0"""
        from src.analysis.tracer import SourceTracingEvaluator
        evaluator = SourceTracingEvaluator()
        metrics = evaluator.evaluate(tracer, [])
        assert metrics["hits@1"] == 0.0
        assert metrics["hits@3"] == 0.0
        assert metrics["total"] == 0
