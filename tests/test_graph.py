"""传播图构建测试"""

import networkx as nx
import pytest
from src.analysis.graph import PropagationGraph, PropagationGraphBuilder


class TestPropagationGraph:
    """PropagationGraph 数据结构"""

    def test_empty_graph(self, pg_empty):
        assert pg_empty.node_count == 0
        assert pg_empty.edge_count == 0
        assert pg_empty.event_id == "empty_event"

    def test_add_node(self, pg_empty):
        pg_empty.add_post_node({
            "id": "post_1", "platform": "weibo",
            "text": "测试内容", "timestamp": "2026-05-29T10:00:00",
            "author_name": "测试用户", "engagement_count": 100,
        })
        assert pg_empty.node_count == 1
        G = pg_empty.graph
        assert G.nodes["post_1"]["platform"] == "weibo"
        assert G.nodes["post_1"]["author"] == "测试用户"

    def test_add_edge(self, pg_empty):
        pg_empty.add_post_node({"id": "a", "platform": "weibo", "text": "",
                                "timestamp": "2026-05-29T10:00:00"})
        pg_empty.add_post_node({"id": "b", "platform": "sina", "text": "",
                                "timestamp": "2026-05-29T10:01:00"})
        pg_empty.add_edge("a", "b", edge_type="cite", confidence=0.85)
        assert pg_empty.edge_count == 1
        edge_data = pg_empty.graph.edges["a", "b"]
        assert edge_data["type"] == "cite"
        assert edge_data["confidence"] == 0.85

    def test_root_candidates(self, pg_empty):
        assert pg_empty.root_candidates == []

    def test_node_count_property(self, pg_with_nodes):
        assert pg_with_nodes.node_count == 12

    def test_platform_distribution(self, pg_with_nodes):
        G = pg_with_nodes.graph
        plats = {}
        for n in G.nodes():
            p = G.nodes[n]["platform"]
            plats[p] = plats.get(p, 0) + 1
        assert plats == {"weibo": 4, "sina": 4, "netease": 2, "zhihu": 2}


class TestGraphBuilder:
    """PropagationGraphBuilder 图构建逻辑"""

    def test_text_similarity_identical(self):
        """完全相同文本 → 高相似度"""
        sim = PropagationGraphBuilder._text_similarity(
            "人工智能取得重大突破", "人工智能取得重大突破")
        assert sim > 0.9

    def test_text_similarity_different(self):
        """完全不同文本 → 低相似度"""
        sim = PropagationGraphBuilder._text_similarity(
            "人工智能技术突破", "健康饮食指南今天")
        assert sim < 0.15

    def test_text_similarity_empty(self):
        """空文本 → 0"""
        assert PropagationGraphBuilder._text_similarity("", "test") == 0.0
        assert PropagationGraphBuilder._text_similarity("test", "") == 0.0
        assert PropagationGraphBuilder._text_similarity("", "") == 0.0

    def test_text_similarity_near_match(self):
        """相近文本 → 适中相似度"""
        sim = PropagationGraphBuilder._text_similarity(
            "人工智能技术突破引发全球关注",
            "人工智能技术取得重大突破 引发全球科技界热议")
        assert 0.2 < sim < 0.8

    def test_builder_with_db_data(self, db_with_data, sample_event_id):
        """从 DB 数据完整构建传播图"""
        builder = PropagationGraphBuilder(db_path=db_with_data.db_path)
        pg = builder.build(sample_event_id, load_existing=False)
        assert pg.node_count == 12
        assert pg.edge_count > 0  # 至少有一些文本相似边

    def test_repost_edges_present(self, pg_with_edges):
        """微博转发链应包含在图中"""
        G = pg_with_edges.graph
        # wb_001 → wb_002 (repost, parent_id)
        assert G.has_edge("wb_001", "wb_002")
        # wb_001 → wb_003 (repost, parent_id)
        assert G.has_edge("wb_001", "wb_003")

    def test_temporal_consistency(self, pg_with_edges):
        """所有边应遵守时间顺序 (source ≤ target)"""
        G = pg_with_edges.graph
        for u, v in G.edges():
            t_u = G.nodes[u].get("timestamp")
            t_v = G.nodes[v].get("timestamp")
            if t_u and t_v:
                assert t_u <= t_v, \
                    f"Edge {u}→{v} violates temporal order: {t_u} > {t_v}"


class TestEdgePersistence:
    """边持久化到数据库"""

    def test_edges_saved_to_db(self, db_with_data, sample_event_id):
        """构建后边应写入 propagation_edges 表"""
        import sqlite3
        builder = PropagationGraphBuilder(db_path=db_with_data.db_path)
        builder.build(sample_event_id, load_existing=False)

        conn = sqlite3.connect(db_with_data.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM propagation_edges").fetchone()[0]
        conn.close()
        assert count > 0

    def test_load_existing_no_duplicates(self, db_with_data, sample_event_id):
        """load_existing=True 不产生重复边"""
        import sqlite3
        builder = PropagationGraphBuilder(db_path=db_with_data.db_path)

        # 首次构建
        pg1 = builder.build(sample_event_id, load_existing=False)
        conn = sqlite3.connect(db_with_data.db_path)
        count1 = conn.execute(
            "SELECT COUNT(*) FROM propagation_edges").fetchone()[0]
        conn.close()

        # 二次构建 (缓存模式)
        pg2 = builder.build(sample_event_id, load_existing=True)
        conn = sqlite3.connect(db_with_data.db_path)
        count2 = conn.execute(
            "SELECT COUNT(*) FROM propagation_edges").fetchone()[0]
        conn.close()

        assert count1 == count2, \
            f"Edge count changed: {count1} → {count2}"

    def test_edge_types_valid(self, db_with_data, sample_event_id):
        """边类型应在合法值范围内"""
        import sqlite3
        builder = PropagationGraphBuilder(db_path=db_with_data.db_path)
        builder.build(sample_event_id, load_existing=False)

        conn = sqlite3.connect(db_with_data.db_path)
        types = [r[0] for r in conn.execute(
            "SELECT DISTINCT edge_type FROM propagation_edges").fetchall()]
        conn.close()
        valid = {"repost", "cite", "cross_platform", "image_match"}
        for t in types:
            assert t in valid, f"Invalid edge type: {t}"
