"""传播图构建器

基于 NetworkX 有向图对新闻事件的跨平台传播路径进行建模，
支持平台内转发边 + 跨平台内容匹配边 + 时序一致性校验。

依赖:
  networkx, sqlite3, numpy
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import networkx as nx
import numpy as np


@dataclass
class PropagationGraph:
    """新闻事件传播图"""
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    event_id: str = ""
    root_candidates: list[str] = field(default_factory=list)

    def add_post_node(self, post: dict):
        self.graph.add_node(
            post.get("post_id", post.get("id", "")),
            platform=post.get("platform", "unknown"),
            text=(post.get("text") or "")[:200],
            timestamp=self._normalize_time(post.get("timestamp")),
            sentiment=post.get("sentiment"),
            author=post.get("author_name", ""),
            engagement=post.get("engagement_count", 0),
            parent_id=post.get("parent_id"),
        )

    def add_edge(self, source_id: str, target_id: str,
                 edge_type: str, confidence: float = 1.0):
        self.graph.add_edge(source_id, target_id,
                            type=edge_type, confidence=confidence)

    @staticmethod
    def _normalize_time(ts) -> Optional[datetime]:
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()


class PropagationGraphBuilder:
    """传播图构建器 — 从数据库加载帖子并构建有向传播图"""

    def __init__(self, db_path: str = "data/news_trace.db"):
        self.db_path = db_path

    def build(self, event_id: str) -> PropagationGraph:
        pg = PropagationGraph(event_id=event_id)

        posts = self._load_event_posts(event_id)
        if not posts:
            print(f"[GraphBuilder] 未找到事件 {event_id} 的帖子")
            return pg

        for post in posts:
            pg.add_post_node(post)

        self._add_intra_platform_edges(pg, posts)
        self._add_cross_platform_edges(pg, posts)
        self._validate_temporal_consistency(pg)

        print(f"[GraphBuilder] 事件 {event_id}: "
              f"{pg.node_count} 节点, {pg.edge_count} 边")
        return pg

    def _load_event_posts(self, event_id: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM posts WHERE event_id=? ORDER BY timestamp",
            (event_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _add_intra_platform_edges(self, pg: PropagationGraph, posts: list[dict]):
        """平台内传播边: 微博转发链 + 同平台文本引用"""
        post_map = {p.get("post_id") or p.get("id", ""): p for p in posts}
        posts_by_platform: dict[str, list[dict]] = {}
        for p in posts:
            plat = p.get("platform", "unknown")
            posts_by_platform.setdefault(plat, []).append(p)

        for post in posts:
            pid = post.get("post_id") or post.get("id", "")
            # 微博转发边
            parent_id = post.get("parent_id")
            if parent_id and parent_id in post_map:
                pg.add_edge(parent_id, pid, edge_type="repost")

        # 同平台文本相似引用
        for plat, plat_posts in posts_by_platform.items():
            if len(plat_posts) < 2:
                continue
            for i, post_a in enumerate(plat_posts):
                for post_b in plat_posts[i + 1:]:
                    sim = self._text_similarity(
                        post_a.get("text", ""), post_b.get("text", ""))
                    if sim > 0.3:
                        t_a = pg._normalize_time(post_a.get("timestamp"))
                        t_b = pg._normalize_time(post_b.get("timestamp"))
                        if t_a and t_b:
                            src, tgt = (post_a, post_b) if t_a <= t_b else (post_b, post_a)
                            sid = src.get("post_id") or src.get("id", "")
                            tid = tgt.get("post_id") or tgt.get("id", "")
                            pg.add_edge(sid, tid, edge_type="cite", confidence=sim)

    def _add_cross_platform_edges(self, pg: PropagationGraph, posts: list[dict]):
        """跨平台边: 基于文本语义 + 时间窗口的跨平台匹配"""
        posts_by_platform: dict[str, list[dict]] = {}
        for p in posts:
            plat = p.get("platform", "unknown")
            posts_by_platform.setdefault(plat, []).append(p)

        platforms = list(posts_by_platform.keys())
        for i in range(len(platforms)):
            for j in range(i + 1, len(platforms)):
                for pa in posts_by_platform[platforms[i]]:
                    for pb in posts_by_platform[platforms[j]]:
                        sim = self._text_similarity(
                            pa.get("text", ""), pb.get("text", ""))
                        if sim < 0.4:
                            continue
                        t_a = pg._normalize_time(pa.get("timestamp"))
                        t_b = pg._normalize_time(pb.get("timestamp"))
                        if t_a and t_b:
                            src, tgt = (pa, pb) if t_a <= t_b else (pb, pa)
                            sid = src.get("post_id") or src.get("id", "")
                            tid = tgt.get("post_id") or tgt.get("id", "")
                            pg.add_edge(sid, tid, edge_type="cross_platform",
                                        confidence=sim)

    def _validate_temporal_consistency(self, pg: PropagationGraph):
        to_remove = []
        for u, v in pg.graph.edges():
            t_u = pg.graph.nodes[u].get("timestamp")
            t_v = pg.graph.nodes[v].get("timestamp")
            if t_u and t_v and t_u > t_v:
                to_remove.append((u, v))
        for u, v in to_remove:
            pg.graph.remove_edge(u, v)

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """简单 Jaccard 字符级相似度（不依赖 NLP 模型）"""
        if not text_a or not text_b:
            return 0.0
        set_a = set(text_a[:300])
        set_b = set(text_b[:300])
        union = len(set_a | set_b)
        return len(set_a & set_b) / union if union > 0 else 0.0
