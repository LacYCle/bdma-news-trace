"""传播图构建器

基于 NetworkX 有向图对新闻事件的跨平台传播路径进行建模，
支持平台内转发边 + 跨平台内容匹配边 + 时序一致性校验。
构建完成后自动持久化边到数据库，支持增量更新和缓存加载。

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
    """传播图构建器 — 从数据库加载帖子并构建有向传播图。

    支持两种模式:
      - 完整构建 (load_existing=False): 重新计算所有边并持久化
      - 缓存加载 (load_existing=True): 从 DB 加载已有边, 仅计算新增帖子的边
    """

    def __init__(self, db_path: str = "data/news_trace.db"):
        self.db_path = db_path

    def build(self, event_id: str, load_existing: bool = True) -> PropagationGraph:
        """构建传播图。

        Parameters
        ----------
        event_id: 事件 ID
        load_existing: True=优先从 DB 加载已有边 (增量模式),
                       False=强制重建所有边

        Returns
        -------
        PropagationGraph
        """
        pg = PropagationGraph(event_id=event_id)

        posts = self._load_event_posts(event_id)
        if not posts:
            print(f"[GraphBuilder] 未找到事件 {event_id} 的帖子")
            return pg

        for post in posts:
            pg.add_post_node(post)

        # 尝试从 DB 加载已有边
        existing_pairs = set()
        if load_existing:
            existing_pairs = self._load_existing_edges(event_id, pg)
            if existing_pairs:
                print(f"[GraphBuilder] 从 DB 加载 {len(existing_pairs)} 条已有边")

        # 计算新边
        new_edge_count = 0
        if load_existing and existing_pairs:
            # 增量模式: 只对新增帖子对计算边
            existing_post_ids = self._get_existing_source_ids(event_id)
            new_posts = [p for p in posts
                         if (p.get("post_id") or p.get("id", "")) not in existing_post_ids]
            if new_posts:
                print(f"[GraphBuilder] 增量模式: {len(new_posts)} 条新帖子, "
                      f"计算增量边...")
                new_edge_count += self._add_intra_platform_edges(pg, posts, existing_pairs)
                new_edge_count += self._add_cross_platform_edges(pg, posts, existing_pairs)
                new_edge_count += self._add_image_match_edges(pg, event_id, existing_pairs)
                self._validate_temporal_consistency(pg)
            else:
                print(f"[GraphBuilder] 无新帖子, 跳过边计算")
        else:
            # 完整构建
            new_edge_count += self._add_intra_platform_edges(pg, posts)
            new_edge_count += self._add_cross_platform_edges(pg, posts)
            new_edge_count += self._add_image_match_edges(pg, event_id)
            self._validate_temporal_consistency(pg)

        # 自动持久化新边
        if new_edge_count > 0:
            self._save_edges_to_db(event_id, pg, existing_pairs)
        else:
            print(f"[GraphBuilder] 无边需要持久化")

        print(f"[GraphBuilder] 事件 {event_id}: "
              f"{pg.node_count} 节点, {pg.edge_count} 边 "
              f"(新增 {new_edge_count} 条)")
        return pg

    def _get_existing_source_ids(self, event_id: str) -> set[str]:
        """获取已在 propagation_edges 中作为 source 或 target 的帖子 ID"""
        conn = sqlite3.connect(self.db_path)
        ids = set()
        for row in conn.execute(
            "SELECT DISTINCT source_id FROM propagation_edges WHERE "
            "source_id IN (SELECT id FROM posts WHERE event_id=?)", (event_id,)):
            ids.add(row[0])
        for row in conn.execute(
            "SELECT DISTINCT target_id FROM propagation_edges WHERE "
            "target_id IN (SELECT id FROM posts WHERE event_id=?)", (event_id,)):
            ids.add(row[0])
        conn.close()
        return ids

    def _load_existing_edges(self, event_id: str,
                             pg: PropagationGraph) -> set[tuple]:
        """从 DB 加载已有边到图中, 返回 (source_id, target_id) 集合"""
        conn = sqlite3.connect(self.db_path)
        event_post_ids = set()
        for row in conn.execute(
            "SELECT id FROM posts WHERE event_id=?", (event_id,)):
            event_post_ids.add(row[0])

        pairs = set()
        for row in conn.execute(
            "SELECT source_id, target_id, edge_type, confidence FROM "
            "propagation_edges WHERE source_id IN ("
            "SELECT id FROM posts WHERE event_id=?)", (event_id,)):
            sid, tid, etype, conf = row[0], row[1], row[2], row[3]
            # 仅当两端节点都在图中时加载
            if sid in pg.graph and tid in pg.graph:
                pg.graph.add_edge(sid, tid, type=etype, confidence=conf)
                pairs.add((sid, tid))
        conn.close()
        return pairs

    def _save_edges_to_db(self, event_id: str, pg: PropagationGraph,
                          skip_pairs: set[tuple] = None):
        """将图中所有边持久化到 propagation_edges 表, 跳过已存在的"""
        skip_pairs = skip_pairs or set()
        conn = sqlite3.connect(self.db_path)
        saved = 0
        for u, v, data in pg.graph.edges(data=True):
            if (u, v) in skip_pairs:
                continue
            t_u = pg.graph.nodes[u].get("timestamp")
            t_v = pg.graph.nodes[v].get("timestamp")
            diff = None
            if t_u and t_v:
                try:
                    diff = int(abs((t_v - t_u).total_seconds()))
                except (TypeError, AttributeError):
                    pass
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO propagation_edges
                    (source_id, target_id, edge_type, confidence, timestamp_diff)
                    VALUES (?, ?, ?, ?, ?)
                """, (u, v, data.get("type", "cite"),
                      data.get("confidence", 1.0), diff))
                if conn.total_changes > 0:
                    saved += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        if saved > 0:
            print(f"[GraphBuilder] 持久化 {saved} 条新边到数据库")

    def _add_image_match_edges(self, pg: PropagationGraph, event_id: str,
                                skip_pairs: set[tuple] = None) -> int:
        """图片匹配边: 基于 pHash 汉明距离检测跨帖子同图传播。
        从 images 表读取已提取的感知哈希, 查找近似匹配。
        返回新增边数量。"""
        skip_pairs = skip_pairs or set()
        added = 0

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT i.post_id, i.phash, p.platform, p.timestamp
            FROM images i JOIN posts p ON i.post_id = p.id
            WHERE p.event_id = ? AND i.phash IS NOT NULL AND i.phash != ''
        """, (event_id,)).fetchall()
        conn.close()

        if len(rows) < 2:
            return 0

        # 两两比较 pHash 汉明距离
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                pid_a, pid_b = rows[i]["post_id"], rows[j]["post_id"]
                if pid_a == pid_b:
                    continue
                pair = (pid_a, pid_b)
                if pair in skip_pairs or (pid_b, pid_a) in skip_pairs:
                    continue

                h1, h2 = rows[i]["phash"], rows[j]["phash"]
                dist = sum(c1 != c2 for c1, c2 in zip(h1, h2))
                if dist <= 10:  # 汉明距离 ≤ 10 → 同一/近似图片
                    confidence = max(0.3, 1.0 - dist / 64.0)
                    t_a = pg._normalize_time(rows[i]["timestamp"])
                    t_b = pg._normalize_time(rows[j]["timestamp"])
                    if t_a and t_b:
                        src, tgt = (pid_a, pid_b) if t_a <= t_b else (pid_b, pid_a)
                        pg.add_edge(src, tgt, edge_type="image_match",
                                    confidence=round(confidence, 3))
                        added += 1

        return added

    def _load_event_posts(self, event_id: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM posts WHERE event_id=? ORDER BY timestamp",
            (event_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _add_intra_platform_edges(self, pg: PropagationGraph, posts: list[dict],
                                    skip_pairs: set[tuple] = None) -> int:
        """平台内传播边: 微博转发链 + 同平台文本引用。
        返回新增边数量。"""
        skip_pairs = skip_pairs or set()
        added = 0
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
                if (parent_id, pid) not in skip_pairs:
                    pg.add_edge(parent_id, pid, edge_type="repost")
                    added += 1

        # 同平台文本相似引用
        for plat, plat_posts in posts_by_platform.items():
            if len(plat_posts) < 2:
                continue
            for i, post_a in enumerate(plat_posts):
                for post_b in plat_posts[i + 1:]:
                    sid_a = post_a.get("post_id") or post_a.get("id", "")
                    sid_b = post_b.get("post_id") or post_b.get("id", "")
                    if (sid_a, sid_b) in skip_pairs or (sid_b, sid_a) in skip_pairs:
                        continue
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
                            added += 1
        return added

    def _add_cross_platform_edges(self, pg: PropagationGraph, posts: list[dict],
                                   skip_pairs: set[tuple] = None) -> int:
        """跨平台边: 基于文本语义 + 时间窗口的跨平台匹配。
        返回新增边数量。"""
        skip_pairs = skip_pairs or set()
        added = 0
        posts_by_platform: dict[str, list[dict]] = {}
        for p in posts:
            plat = p.get("platform", "unknown")
            posts_by_platform.setdefault(plat, []).append(p)

        platforms = list(posts_by_platform.keys())
        for i in range(len(platforms)):
            for j in range(i + 1, len(platforms)):
                for pa in posts_by_platform[platforms[i]]:
                    for pb in posts_by_platform[platforms[j]]:
                        sid_a = pa.get("post_id") or pa.get("id", "")
                        sid_b = pb.get("post_id") or pb.get("id", "")
                        if (sid_a, sid_b) in skip_pairs or (sid_b, sid_a) in skip_pairs:
                            continue
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
                            added += 1
        return added

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
