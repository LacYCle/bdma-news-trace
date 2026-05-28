"""源头溯源器

在传播图中定位新闻事件的可能源头 —— 入度为 0 的根节点，
按时间最早 + 出度最大 + 跨平台传播等多维证据打分排序。

依赖:
  networkx, numpy
"""

import numpy as np
import networkx as nx
from typing import Optional

from .graph import PropagationGraph


class SourceTracer:
    """新闻源头溯源器"""

    def trace(self, pg: PropagationGraph, top_k: int = 5) -> list[dict]:
        """推断事件的可能源头列表"""
        G = pg.graph
        if G.number_of_nodes() == 0:
            return []

        roots = [n for n in G.nodes() if G.in_degree(n) == 0]

        if not roots:
            nodes_with_time = []
            for n in G.nodes():
                ts = G.nodes[n].get("timestamp")
                if ts is not None:
                    nodes_with_time.append((n, ts))
            nodes_with_time.sort(key=lambda x: x[1])
            roots = [n for n, _ in nodes_with_time[:min(5, len(nodes_with_time))]]

        candidates = []
        for root in roots:
            score = self._score_candidate(G, root)
            node = G.nodes[root]
            candidates.append({
                "post_id": root,
                "platform": node.get("platform", "unknown"),
                "author": node.get("author", "unknown"),
                "timestamp": node.get("timestamp"),
                "text_preview": (node.get("text", "") or "")[:120],
                "confidence": round(score, 3),
                "evidence": self._gather_evidence(G, root),
            })

        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[:top_k]

    def _score_candidate(self, G: nx.DiGraph, node_id: str) -> float:
        node = G.nodes[node_id]
        score = 0.5
        if G.in_degree(node_id) == 0:
            score += 0.25
        out_deg = G.out_degree(node_id)
        score += min(0.15, out_deg * 0.005)
        if node.get("text"):
            score += 0.10
        return min(1.0, score)

    def _gather_evidence(self, G: nx.DiGraph, root: str) -> dict:
        out_edges = list(G.out_edges(root, data=True))
        platforms = set()
        for _, tgt, _ in out_edges:
            plat = G.nodes[tgt].get("platform", "?")
            platforms.add(plat)
        return {
            "direct_reposts": sum(1 for _, _, d in out_edges
                                  if d.get("type") == "repost"),
            "cross_platform_spread": sum(1 for _, _, d in out_edges
                                         if d.get("type") == "cross_platform"),
            "total_out_degree": len(out_edges),
            "first_level_platforms": list(platforms),
        }


class SourceTracingEvaluator:
    """溯源准确性评估 — Hits@K + MRR"""

    def evaluate(self, tracer: SourceTracer,
                 events: list[dict]) -> dict:
        """对标注了 ground truth 源头的事件进行评估

        events: [{"pg": PropagationGraph, "true_source_id": str}, ...]
        """
        if not events:
            return {"hits@1": 0, "hits@3": 0, "mrr": 0.0, "total": 0}

        hits_1, hits_3, mrr_sum = 0, 0, 0.0
        for event in events:
            pg = event.get("pg")
            true_id = event.get("true_source_id", "")
            if pg is None:
                continue
            candidates = tracer.trace(pg, top_k=10)
            for rank, cand in enumerate(candidates):
                if cand["post_id"] == true_id:
                    if rank == 0:
                        hits_1 += 1
                    if rank < 3:
                        hits_3 += 1
                    mrr_sum += 1.0 / (rank + 1)
                    break

        total = len(events)
        return {
            "hits@1": hits_1 / total,
            "hits@3": hits_3 / total,
            "mrr": mrr_sum / total,
            "total": total,
        }
